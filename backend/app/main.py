"""HTTP API for the Open-Source Corpus Explorer."""

import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.db import query

app = FastAPI(title="Open-Source Corpus Explorer API", version="0.1.0")

GOLD = """gold AS (
  SELECT * FROM hackcamp.gold.repo_health
  QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY scored_at DESC) = 1
)"""
LATEST_FINDING = """latest_finding AS (
  SELECT * FROM hackcamp.agent.findings
  QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY investigated_at DESC) = 1
)"""
LATEST_RUN = """latest_run AS (
  SELECT run_id FROM hackcamp.agent.runs ORDER BY started_at DESC LIMIT 1
)"""
FINDING_COLS = """f.run_id, f.risk_level, f.confidence, f.headline, f.explanation,
  to_json(f.evidence) AS evidence, f.changed_since_last, f.alternatives,
  f.tool_calls, f.trace_id, f.investigated_at"""
SEVERITY = """CASE f.risk_level WHEN 'at_risk' THEN 0 WHEN 'watchlist' THEN 1
  WHEN 'inconclusive' THEN 2 ELSE 3 END"""


def _finding(row: dict) -> dict:
    row = dict(row)
    row["evidence"] = json.loads(row["evidence"]) if row.get("evidence") else []
    row["alternatives"] = list(row["alternatives"]) if row.get("alternatives") is not None else []
    return row


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/repos")
def list_repos() -> list[dict]:
    return query(f"""
WITH {GOLD}, {LATEST_FINDING}, {LATEST_RUN}
SELECT g.repo_id, g.name, g.owner, g.language, g.health_score, g.status,
  g.importance, g.x, g.y, g.stars, g.is_archived,
  f.risk_level,
  f.repo_id IS NOT NULL AS investigated,
  coalesce(f.run_id = (SELECT run_id FROM latest_run), false) AS investigated_in_latest_run
FROM gold g LEFT JOIN latest_finding f ON f.repo_id = g.repo_id
ORDER BY g.importance DESC""")


@app.get("/api/repos/{repo_id:path}")
def get_repo(repo_id: str) -> dict:
    rows = query(f"""
WITH {GOLD}
SELECT g.repo_id, g.name, g.owner, g.language, g.stars, g.dependents, g.is_archived,
  g.health_score, g.status, g.importance, g.x, g.y, g.scored_at,
  g.days_since_release, g.commit_trend_pct,
  s.pushed_at, s.last_release_at, s.commits_90d, s.commits_prev_90d,
  s.open_issues, s.open_prs, s.contributors,
  s.maintainer_reply_rate, s.top_contributor_share
FROM gold g LEFT JOIN hackcamp.silver.repos s ON s.repo_id = g.repo_id
WHERE g.repo_id = :repo_id""", {"repo_id": repo_id})
    if not rows:
        raise HTTPException(404, f"repo {repo_id} not found")
    r = rows[0]
    verdicts = [_finding(v) for v in query(f"""
SELECT {FINDING_COLS} FROM hackcamp.agent.findings f
WHERE f.repo_id = :repo_id ORDER BY f.investigated_at DESC LIMIT 2""", {"repo_id": repo_id})]
    metric_keys = ["days_since_release", "commit_trend_pct", "pushed_at", "last_release_at",
                   "commits_90d", "commits_prev_90d", "open_issues", "open_prs", "contributors",
                   "maintainer_reply_rate", "top_contributor_share"]
    repo = {k: v for k, v in r.items() if k not in metric_keys}
    repo["github_url"] = f"https://github.com/{repo_id}"
    repo["metrics"] = {k: r[k] for k in metric_keys}
    repo["verdict"] = verdicts[0] if verdicts else None
    repo["previous_verdict"] = verdicts[1] if len(verdicts) > 1 else None
    return repo


@app.get("/api/findings")
def list_findings(language: str | None = None, risk: str | None = None) -> list[dict]:
    rows = query(f"""
WITH {GOLD}, {LATEST_FINDING}, {LATEST_RUN}
SELECT f.repo_id, g.name, g.language, g.importance, g.health_score, {FINDING_COLS},
  f.run_id = (SELECT run_id FROM latest_run) AS in_latest_run
FROM latest_finding f LEFT JOIN gold g ON g.repo_id = f.repo_id
WHERE (:language IS NULL OR g.language = :language)
  AND (:risk IS NULL OR f.risk_level = :risk)
ORDER BY {SEVERITY}, g.importance DESC""", {"language": language, "risk": risk})
    return [_finding(r) for r in rows]


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
