"""HTTP API for the Open-Source Corpus Explorer."""

import ast
import json
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import scan
from app.db import query

# Nearest .env walking up from backend/app (backend/.env, then repo root). Real env vars win.
load_dotenv(find_dotenv())

app = FastAPI(title="Open-Source Corpus Explorer API", version="0.1.0")

# Vite build output copied here before Databricks Apps deploy (`frontend/dist` → `static`).
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

GOLD = """gold AS (
  SELECT * FROM hackcamp.gold.repo_health
  QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY scored_at DESC) = 1
)"""
# Live UC schema: risk_level includes legacy 'ignored' rows; product surfaces exclude them.
LATEST_FINDING = """latest_finding AS (
  SELECT * FROM hackcamp.agent.findings
  WHERE coalesce(risk_level, '') <> 'ignored'
  QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY investigated_at DESC) = 1
)"""
LATEST_RUN = """latest_run AS (
  SELECT run_id FROM hackcamp.agent.runs ORDER BY started_at DESC LIMIT 1
)"""
FINDING_COLS = """f.run_id, f.risk_level, f.confidence, f.headline, f.explanation,
  to_json(f.evidence) AS evidence, f.changed_since_last, f.alternatives,
  f.tool_calls, f.trace_id, f.investigated_at"""
SEVERITY = """CASE f.risk_level WHEN 'at_risk' THEN 0 WHEN 'watchlist' THEN 1
  WHEN 'inconclusive' THEN 2 WHEN 'healthy' THEN 3 ELSE 4 END"""


def _parse_str_list_text(text: str) -> list[str] | None:
    """Parse JSON or Python-repr array text into a string list."""
    text = text.strip()
    if not text.startswith("["):
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (json.JSONDecodeError, SyntaxError, ValueError):
            continue
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    return None


def _as_str_list(value) -> list[str]:
    """Normalize UC array / JSON-string / Python-repr / broken char-list values."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parsed = _parse_str_list_text(text)
        if parsed is not None:
            return parsed
        # Unwrap a single mangled bucket like "['Code execution']".
        if text.startswith("[") and text.endswith("]"):
            return []
        return [text]
    if isinstance(value, (list, tuple)):
        # Databricks sometimes yields a JSON/Python array stringified then list()'d
        # into characters: ['[', "'", 'C', ...]. Recover those.
        if value and all(isinstance(x, str) and len(x) <= 1 for x in value):
            joined = "".join(value)
            parsed = _parse_str_list_text(joined)
            if parsed is not None:
                return parsed
            return []
        # Flatten one level if an element is itself a serialized list.
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip().startswith("["):
                nested = _parse_str_list_text(item)
                if nested is not None:
                    out.extend(nested)
                    continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return [str(value)]


def _finding(row: dict) -> dict:
    row = dict(row)
    row["evidence"] = json.loads(row["evidence"]) if row.get("evidence") else []
    row["alternatives"] = _as_str_list(row.get("alternatives"))
    return row


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/repos")
def list_repos() -> list[dict]:
    rows = query(f"""
WITH {GOLD}, {LATEST_FINDING}, {LATEST_RUN}
SELECT g.repo_id, g.name, g.owner, g.language, g.health_score, g.status,
  g.importance, g.x, g.y, g.cat_x, g.cat_y, g.stars, g.is_archived,
  g.category, to_json(g.vuln_buckets) AS vuln_buckets, g.advisory_count, g.max_severity, g.max_cvss,
  f.risk_level, f.changed_since_last,
  f.repo_id IS NOT NULL AS investigated,
  coalesce(f.run_id = (SELECT run_id FROM latest_run), false) AS investigated_in_latest_run,
  sm.summary
FROM gold g LEFT JOIN latest_finding f ON f.repo_id = g.repo_id
LEFT JOIN hackcamp.gold.repo_summaries sm ON sm.repo_id = g.repo_id
ORDER BY g.importance DESC""")
    for row in rows:
        row["vuln_buckets"] = _as_str_list(row.get("vuln_buckets"))
    return rows


@app.get("/api/repos/{repo_id:path}")
def get_repo(repo_id: str) -> dict:
    rows = query(f"""
WITH {GOLD}
SELECT g.repo_id, g.name, g.owner, g.language, g.stars, g.dependents, g.is_archived,
  g.health_score, g.status, g.importance, g.x, g.y, g.cat_x, g.cat_y, g.scored_at,
  g.category, to_json(g.vuln_buckets) AS vuln_buckets, g.advisory_count, g.max_severity, g.max_cvss,
  g.days_since_release, g.commit_trend_pct,
  s.pushed_at, s.last_release_at, s.commits_90d, s.commits_prev_90d,
  s.open_issues, s.open_prs, s.contributors,
  s.maintainer_reply_rate, s.top_contributor_share, s.advisory_fetch_status,
  s.description, to_json(s.topics) AS topics, sm.summary
FROM gold g LEFT JOIN hackcamp.silver.repos s ON s.repo_id = g.repo_id
LEFT JOIN hackcamp.gold.repo_summaries sm ON sm.repo_id = g.repo_id
WHERE g.repo_id = :repo_id""", {"repo_id": repo_id})
    if not rows:
        raise HTTPException(404, f"repo {repo_id} not found")
    r = rows[0]
    verdicts = [_finding(v) for v in query(f"""
SELECT {FINDING_COLS} FROM hackcamp.agent.findings f
WHERE f.repo_id = :repo_id AND coalesce(f.risk_level, '') <> 'ignored'
ORDER BY f.investigated_at DESC LIMIT 2""", {"repo_id": repo_id})]
    advisories = query("""
SELECT ghsa_id, cve_id, severity, cvss_score, cwes, vuln_bucket, summary, published_at
FROM hackcamp.silver.repo_advisories
WHERE repo_id = :repo_id
ORDER BY published_at DESC NULLS LAST""", {"repo_id": repo_id})
    metric_keys = ["days_since_release", "commit_trend_pct", "pushed_at", "last_release_at",
                   "commits_90d", "commits_prev_90d", "open_issues", "open_prs", "contributors",
                   "maintainer_reply_rate", "top_contributor_share"]
    repo = {k: v for k, v in r.items() if k not in metric_keys}
    repo["vuln_buckets"] = _as_str_list(repo.get("vuln_buckets"))
    repo["topics"] = _as_str_list(repo.get("topics"))
    repo["github_url"] = f"https://github.com/{repo_id}"
    repo["metrics"] = {k: r[k] for k in metric_keys}
    repo["verdict"] = verdicts[0] if verdicts else None
    repo["previous_verdict"] = verdicts[1] if len(verdicts) > 1 else None
    repo["advisories"] = [
        {**a, "cwes": _as_str_list(a.get("cwes"))}
        for a in advisories
    ]
    return repo


@app.get("/api/findings")
def list_findings(language: str | None = None, risk: str | None = None) -> list[dict]:
    rows = query(f"""
WITH {GOLD}, {LATEST_FINDING}, {LATEST_RUN}
SELECT f.repo_id, g.name, g.language, g.importance, g.health_score,
  g.category, to_json(g.vuln_buckets) AS vuln_buckets, {FINDING_COLS},
  f.run_id = (SELECT run_id FROM latest_run) AS in_latest_run
FROM latest_finding f LEFT JOIN gold g ON g.repo_id = f.repo_id
WHERE coalesce(f.risk_level, '') <> 'ignored'
  AND (:language IS NULL OR g.language = :language)
  AND (:risk IS NULL OR f.risk_level = :risk)
ORDER BY {SEVERITY}, g.importance DESC""", {"language": language, "risk": risk})
    out = []
    for r in rows:
        row = _finding(r)
        row["vuln_buckets"] = _as_str_list(row.get("vuln_buckets"))
        out.append(row)
    return out


@app.get("/api/findings/{repo_id:path}/trace")
def get_trace(repo_id: str) -> dict:
    """Steps come from agent.trace_steps, which the agent writes alongside each finding (#11)."""
    rows = query(f"""
WITH {LATEST_FINDING}
SELECT f.repo_id, f.run_id, f.trace_id, t.payload
FROM latest_finding f
LEFT JOIN hackcamp.agent.trace_steps t
  ON t.trace_id = f.trace_id AND t.repo_id = f.repo_id AND t.run_id = f.run_id
WHERE f.repo_id = :repo_id""", {"repo_id": repo_id})
    if not rows:
        raise HTTPException(404, f"no finding for {repo_id}")
    r = rows[0]
    if not r["payload"]:
        # Finding predates trace export; rerun the agent to populate it.
        return {"repo_id": r["repo_id"], "run_id": r["run_id"], "trace_id": r["trace_id"],
                "status": "not_ready", "steps": []}
    return json.loads(r["payload"])


@app.get("/api/runs/latest")
def latest_run() -> dict:
    rows = query("""
SELECT run_id, started_at, repos_triaged, repos_investigated, tool_calls_total, model, eval_score
FROM hackcamp.agent.runs ORDER BY started_at DESC LIMIT 1""")
    if not rows:
        raise HTTPException(404, "no agent runs yet")
    return rows[0]


SCANS_DDL = """CREATE TABLE IF NOT EXISTS hackcamp.agent.code_scans (
  repo_id STRING NOT NULL, commit_sha STRING, model STRING, files STRING,
  summary STRING, findings STRING, scanned_at TIMESTAMP)"""


def _scan_row(r: dict) -> dict:
    return {**r, "files": json.loads(r["files"] or "[]"),
            "findings": scan.enrich(json.loads(r["findings"] or "[]"), r["repo_id"], r["commit_sha"])}


@app.get("/api/scans/{repo_id:path}")
def get_scan(repo_id: str) -> dict:
    """Latest stored Gemini code scan for a repo."""
    rows = query("""
SELECT repo_id, commit_sha, model, files, summary, findings, scanned_at
FROM hackcamp.agent.code_scans WHERE repo_id = :repo_id
ORDER BY scanned_at DESC LIMIT 1""", {"repo_id": repo_id})
    if not rows:
        raise HTTPException(404, f"no scan for {repo_id}")
    return _scan_row(rows[0])


@app.post("/api/scans/{repo_id:path}")
def run_scan(repo_id: str) -> dict:
    """Run a fresh Gemini scan of the repo's riskiest files and store it."""
    if not query(f"WITH {GOLD} SELECT repo_id FROM gold WHERE repo_id = :repo_id", {"repo_id": repo_id}):
        raise HTTPException(404, f"repo {repo_id} not found")
    try:
        result = scan.scan_repo(repo_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"upstream error {e.response.status_code} from {e.request.url.host}: "
                                 f"{e.response.text[:300]}")
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
        raise HTTPException(502, f"scan failed: {e}")
    query(SCANS_DDL)
    row = {"repo_id": repo_id, "commit_sha": result["commit_sha"], "model": result["model"],
           "files": json.dumps(result["files"]), "summary": result["summary"],
           "findings": json.dumps(result["findings"])}
    query("""INSERT INTO hackcamp.agent.code_scans
VALUES (:repo_id, :commit_sha, :model, :files, :summary, :findings, current_timestamp())""", row)
    return get_scan(repo_id)


# Serve the React build from the same origin as /api (required on Databricks Apps).
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
