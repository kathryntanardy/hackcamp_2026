# Databricks notebook source
"""F12: find up to 3 similar healthy repos via the shared Vector Search index (#30)."""

import json
import os
import re
from typing import Any

SEARCH_INDEX = os.environ.get("SEARCH_INDEX", "hackcamp.gold.repo_search_index")
SEARCH_MIN_SCORE = float(os.environ.get("SEARCH_MIN_SCORE", "0.56"))
SEARCH_SCORE_WINDOW = float(os.environ.get("SEARCH_SCORE_WINDOW", "0.06"))
# Pull extras so we can drop self / non-healthy after ranking.
SEARCH_CANDIDATE_POOL = 12


def _safe_repo(repo_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_id):
        raise ValueError(f"invalid repo_id: {repo_id}")
    return repo_id


def _query_text_for(repo_id: str) -> str | None:
    """Prefer the indexed search_text; fall back to gold name + silver description."""
    safe = repo_id.replace("'", "''")
    rows = spark.sql(
        f"SELECT search_text FROM hackcamp.gold.repo_search_docs WHERE repo_id = '{safe}' LIMIT 1"
    ).collect()
    if rows and rows[0].search_text:
        return str(rows[0].search_text)
    rows = spark.sql(
        f"""
        SELECT g.name, g.category, s.description, to_json(s.topics) AS topics
        FROM hackcamp.gold.repo_health g
        LEFT JOIN hackcamp.silver.repos s ON s.repo_id = g.repo_id
        WHERE g.repo_id = '{safe}' LIMIT 1
        """
    ).collect()
    if not rows:
        return None
    r = rows[0]
    parts = [r.name or repo_id, r.category or "", r.description or "", r.topics or ""]
    text = " ".join(p for p in parts if p).strip()
    return text or None


def find_alternatives(repo: str, k: int = 3) -> dict[str, Any]:
    """Return up to k similar *healthy* repos for remediation (excludes the query repo)."""
    repo = _safe_repo(repo)
    k = max(1, min(int(k), 3))
    query_text = _query_text_for(repo)
    if not query_text:
        return {
            "repo": repo,
            "alternatives": [],
            "error": "no searchable text for repo",
        }

    try:
        from databricks.sdk import WorkspaceClient

        res = WorkspaceClient().vector_search_indexes.query_index(
            SEARCH_INDEX,
            columns=["repo_id", "status"],
            query_text=query_text,
            num_results=max(SEARCH_CANDIDATE_POOL, k + 5),
            filters_json=json.dumps({"status": "healthy"}),
        )
    except Exception as e:  # SDK raises many types
        return {
            "repo": repo,
            "alternatives": [],
            "error": f"{type(e).__name__}: {e}",
        }

    rows = list(res.result.data_array or [])
    scored: list[tuple[str, float]] = []
    for row in rows:
        rid = str(row[0])
        score = float(row[-1])
        if rid.lower() == repo.lower():
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", rid):
            continue
        scored.append((rid, score))

    if not scored:
        return {"repo": repo, "alternatives": [], "scores": []}

    cutoff = max(SEARCH_MIN_SCORE, scored[0][1] - SEARCH_SCORE_WINDOW)
    alts = [rid for rid, score in scored if score >= cutoff][:k]
    return {
        "repo": repo,
        "alternatives": alts,
        "scores": [
            {"repo_id": rid, "score": score}
            for rid, score in scored
            if rid in alts
        ],
    }


def sanitize_alternatives(values: Any) -> list[str]:
    """Keep only org/repo ids; drop mangled empties like '[]'."""
    if values is None:
        return []
    if isinstance(values, str):
        text = values.strip()
        if not text or text in {"[]", "null", "None"}:
            return []
        try:
            values = json.loads(text)
        except json.JSONDecodeError:
            values = [text]
    if not isinstance(values, (list, tuple)):
        values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= 3:
            break
    return out
