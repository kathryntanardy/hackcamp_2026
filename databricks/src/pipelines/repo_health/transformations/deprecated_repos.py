"""Repos that should be parked as `ignored` (no future PR-review attention).

Officially deprecated or superseded lines stay in the corpus for map context, but
gold marks them ignored and the agent skips them on later triage runs.
"""

from __future__ import annotations

# Non-archived (or ambiguous) repos with an official deprecation / legacy notice.
# Archived repos are ignored via `is_archived` even if absent from this set.
KNOWN_DEPRECATED_REPOS: frozenset[str] = frozenset(
    {
        "request/request",
        "moment/moment",
        "dgrijalva/jwt-go",
        "gorilla/mux",
        "codehaus/jackson",
    }
)


def is_ignored(repo_id: str, is_archived: bool) -> bool:
    """True when gold/agent should park the repo instead of living triage."""
    if is_archived:
        return True
    return (repo_id or "").strip() in KNOWN_DEPRECATED_REPOS
