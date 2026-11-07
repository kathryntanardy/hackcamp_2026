# Databricks notebook source
# MAGIC %md
# MAGIC # Live GitHub fetch tools (read-only) with Delta `tool_cache`
# MAGIC Plain Python tools (not UC functions) so we can read `hackcamp/github_token` via dbutils.
# MAGIC Hour-1 confirmed UC can do HTTP, but secrets belong in the agent/job runtime.

# COMMAND ----------

import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# COMMAND ----------

SECRET_SCOPE = "hackcamp"
SECRET_KEY = "github_token"
TOOL_CACHE_TABLE = "hackcamp.agent.tool_cache"
MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
README_PATTERNS = {
    "deprecated": re.compile(r"\bdeprecated\b", re.I),
    "unmaintained": re.compile(r"\bunmaintained\b|\bno longer maintained\b", re.I),
    "archived": re.compile(r"\barchived\b|\bthis repo(sitory)? is archived\b", re.I),
    "use_instead": re.compile(
        r"(?:use|switch to|replaced by|moved to)\s+[`]?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)[`]?",
        re.I,
    ),
}


def _safe_repo(repo_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_id):
        raise ValueError(f"invalid repo_id: {repo_id}")
    return repo_id


def args_hash(tool: str, args: dict[str, Any]) -> str:
    payload = json.dumps({"tool": tool, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _github_token() -> str:
    token = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)
    if not token:
        raise RuntimeError(f"empty secret {SECRET_SCOPE}/{SECRET_KEY}")
    return token


def cache_get(tool: str, h: str) -> str | None:
    rows = spark.sql(
        f"""
        SELECT response
        FROM {TOOL_CACHE_TABLE}
        WHERE tool = '{tool}' AND args_hash = '{h}'
        ORDER BY fetched_at DESC
        LIMIT 1
        """
    ).collect()
    if not rows:
        return None
    return rows[0]["response"]


def cache_put(tool: str, h: str, response: str) -> None:
    # Escape for SQL string literal
    safe = response.replace("\\", "\\\\").replace("'", "''")
    spark.sql(
        f"""
        INSERT INTO {TOOL_CACHE_TABLE} (tool, args_hash, response, fetched_at)
        VALUES ('{tool}', '{h}', '{safe}', current_timestamp())
        """
    )


def _http_get_json(url: str, token: str, accept: str = "application/vnd.github+json") -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "User-Agent": "hackcamp-live-fetch",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code in (403, 429):
            # brief backoff once
            time.sleep(2)
            raise RuntimeError(f"GitHub rate limited/forbidden ({e.code}): {body[:300]}") from e
        raise RuntimeError(f"GitHub HTTP {e.code}: {body[:300]}") from e


def _issue_maintainer_replied(owner: str, name: str, issue_number: int, token: str) -> bool:
    url = (
        f"https://api.github.com/repos/{owner}/{name}/issues/{issue_number}/comments"
        f"?per_page=30"
    )
    comments = _http_get_json(url, token) or []
    if not isinstance(comments, list):
        return False
    for c in comments:
        assoc = (c.get("author_association") or "").upper()
        if assoc in MAINTAINER_ASSOCIATIONS:
            return True
    return False


def fetch_recent_issues(repo: str, n: int = 5, *, force_refresh: bool = False) -> dict[str, Any]:
    """Last n issue titles and whether a maintainer replied. Read-only."""
    repo = _safe_repo(repo)
    n = max(1, min(int(n), 20))
    tool = "fetch_recent_issues"
    args = {"repo": repo, "n": n}
    h = args_hash(tool, args)

    if not force_refresh:
        hit = cache_get(tool, h)
        if hit is not None:
            parsed = json.loads(hit)
            parsed["cache_hit"] = True
            return parsed

    token = _github_token()
    owner, name = repo.split("/", 1)
    q = urllib.parse.urlencode({"state": "all", "per_page": n, "sort": "updated"})
    url = f"https://api.github.com/repos/{owner}/{name}/issues?{q}"
    issues = _http_get_json(url, token) or []
    # GitHub returns PRs in the issues list — skip pull_request entries
    issues = [i for i in issues if isinstance(i, dict) and "pull_request" not in i][:n]

    items = []
    for issue in issues:
        number = int(issue["number"])
        title = issue.get("title") or ""
        maintainer_replied = _issue_maintainer_replied(owner, name, number, token)
        items.append(
            {
                "number": number,
                "title": title,
                "state": issue.get("state"),
                "author_association": issue.get("author_association"),
                "maintainer_replied": maintainer_replied,
                "html_url": issue.get("html_url"),
            }
        )

    result = {
        "repo_id": repo,
        "n": n,
        "issues": items,
        "unanswered_count": sum(1 for i in items if not i["maintainer_replied"]),
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cache_hit": False,
        "source": "github_rest",
    }
    cache_put(tool, h, json.dumps(result))
    return result


def fetch_readme_signals(repo: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Flags for deprecated / unmaintained / archived / use X instead. Read-only."""
    repo = _safe_repo(repo)
    tool = "fetch_readme_signals"
    args = {"repo": repo}
    h = args_hash(tool, args)

    if not force_refresh:
        hit = cache_get(tool, h)
        if hit is not None:
            parsed = json.loads(hit)
            parsed["cache_hit"] = True
            return parsed

    token = _github_token()
    owner, name = repo.split("/", 1)

    # Repo metadata (archived flag)
    meta = _http_get_json(f"https://api.github.com/repos/{owner}/{name}", token) or {}
    archived = bool(meta.get("archived"))

    readme_text = ""
    readme_path = None
    try:
        readme = _http_get_json(
            f"https://api.github.com/repos/{owner}/{name}/readme",
            token,
            accept="application/vnd.github+json",
        )
        if isinstance(readme, dict) and readme.get("content"):
            readme_path = readme.get("path")
            encoding = readme.get("encoding") or "base64"
            if encoding == "base64":
                readme_text = base64.b64decode(readme["content"]).decode(
                    "utf-8", errors="replace"
                )
            else:
                readme_text = str(readme.get("content") or "")
    except Exception as e:
        readme_text = ""
        readme_error = str(e)
    else:
        readme_error = None

    flags = {
        "deprecated": bool(README_PATTERNS["deprecated"].search(readme_text)),
        "unmaintained": bool(README_PATTERNS["unmaintained"].search(readme_text)),
        "archived": archived
        or bool(README_PATTERNS["archived"].search(readme_text)),
    }
    alts = []
    for m in README_PATTERNS["use_instead"].finditer(readme_text):
        cand = m.group(1)
        if cand and cand.lower() != repo.lower() and cand not in alts:
            alts.append(cand)
        if len(alts) >= 3:
            break

    result = {
        "repo_id": repo,
        "flags": flags,
        "use_instead": alts,
        "readme_path": readme_path,
        "readme_chars": len(readme_text),
        "readme_error": readme_error,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cache_hit": False,
        "source": "github_rest",
    }
    cache_put(tool, h, json.dumps(result))
    return result


print("live_fetch_tools loaded")
