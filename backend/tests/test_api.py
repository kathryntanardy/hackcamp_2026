import json

import pytest
from fastapi.testclient import TestClient

import app.main as main

FINDING = {
    "run_id": "r2", "risk_level": "at_risk", "confidence": 0.9, "headline": "h",
    "explanation": "e", "evidence": '[{"signal":"s","tool":"get_release_history","value":"420"}]',
    "changed_since_last": "unchanged", "alternatives": None, "tool_calls": 4,
    "trace_id": "tr-1", "investigated_at": "2026-11-07T20:00:00",
}


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake_query(statement, params=None):
        log.append((statement, params))
        if "hackcamp.agent.runs ORDER BY" in statement and "WITH" not in statement:
            return [{"run_id": "r2", "eval_score": None}]
        if "hackcamp.silver.repo_advisories" in statement:
            return [{"ghsa_id": "GHSA-x", "cve_id": "CVE-1", "severity": "high",
                     "cvss_score": 8.1, "cwes": ["CWE-94"], "vuln_bucket": "Code execution",
                     "summary": "code injection", "published_at": "2026-01-01"}]
        if "hackcamp.silver.repos" in statement:
            if params["repo_id"] == "missing/repo":
                return []
            return [{"repo_id": params["repo_id"], "name": "x", "days_since_release": 420,
                     "commit_trend_pct": -98.0, "pushed_at": None, "last_release_at": None,
                     "commits_90d": 1, "commits_prev_90d": 50, "open_issues": 40, "open_prs": 22,
                     "contributors": 35, "maintainer_reply_rate": 0.05,
                     "top_contributor_share": 0.8, "advisory_fetch_status": "ok",
                     "description": "A utility lib", "topics": ["javascript"],
                     "category": "Back-end", "vuln_buckets": ["Code execution"],
                     "advisory_count": 1, "max_severity": "high", "max_cvss": 8.1,
                     "cat_x": 1.0, "cat_y": 2.0, "x": 0.0, "y": 0.0,
                     "health_score": 10.0, "status": "at_risk", "importance": 3.0,
                     "stars": 100, "dependents": 0, "is_archived": False,
                     "language": "JavaScript", "owner": "moment", "scored_at": "2026-11-07",
                     "summary": "Stale but stable."}]
        if "DESC LIMIT 2" in statement:
            return [FINDING, {**FINDING, "run_id": "r1", "evidence": None}]
        if "trace_steps" in statement:
            payload = {"trace_id": "tr-1", "steps": [{"order": 1, "tool_name": "t"}]}
            return {"missing/repo": [],
                    "old/repo": [{"repo_id": "old/repo", "run_id": "r1", "trace_id": "tr-0", "payload": None}],
                    }.get(params["repo_id"], [{"repo_id": params["repo_id"], "run_id": "r2",
                                               "trace_id": "tr-1", "payload": json.dumps(payload)}])
        return [{"repo_id": "a/b", "category": "other", "vuln_buckets": [],
                 "total_count": 1, **FINDING}]

    monkeypatch.setattr(main, "query", fake_query)
    return log


client = TestClient(main.app)


def test_repos(calls):
    assert client.get("/api/repos").status_code == 200


def test_repos_expose_change_badge(calls):
    client.get("/api/repos")
    assert "f.changed_since_last" in calls[-1][0]


def test_repo_detail_splits_metrics_and_verdicts(calls):
    body = client.get("/api/repos/moment/moment").json()
    assert body["repo_id"] == "moment/moment"
    assert body["github_url"] == "https://github.com/moment/moment"
    assert body["metrics"]["commits_prev_90d"] == 50
    assert body["verdict"]["evidence"][0]["tool"] == "get_release_history"
    assert body["previous_verdict"]["run_id"] == "r1"
    assert body["previous_verdict"]["evidence"] == []
    assert body["advisories"][0]["vuln_bucket"] == "Code execution"
    assert body["category"] == "Back-end"
    assert body["vuln_buckets"] == ["Code execution"]
    assert body["advisories"][0]["cwes"] == ["CWE-94"]


def test_as_str_list_recovers_json_string_and_char_lists():
    from app.main import _as_str_list

    assert _as_str_list('["Code execution","Prototype pollution"]') == [
        "Code execution",
        "Prototype pollution",
    ]
    assert _as_str_list("['Other / unclassified', 'Injection']") == [
        "Other / unclassified",
        "Injection",
    ]
    assert _as_str_list(list('["Injection"]')) == ["Injection"]
    assert _as_str_list(list("['Code execution']")) == ["Code execution"]
    assert _as_str_list(["['Path traversal & file access']"]) == [
        "Path traversal & file access",
    ]
    assert _as_str_list(["Auth & access control"]) == ["Auth & access control"]
    assert _as_str_list(None) == []


def test_repos_expose_summary(calls):
    client.get("/api/repos")
    assert "gold.repo_summaries" in calls[-1][0] and "sm.summary" in calls[-1][0]


def test_repo_detail_has_summary_outside_metrics(calls):
    body = client.get("/api/repos/moment/moment").json()
    assert body["summary"] == "Stale but stable."
    assert "summary" not in body["metrics"]


def test_repo_detail_404(calls):
    assert client.get("/api/repos/missing/repo").status_code == 404


def test_findings_passes_filters_as_params(calls):
    body = client.get("/api/findings?language=Go&risk=at_risk").json()
    assert body["items"][0]["alternatives"] == []
    assert "total_count" not in body["items"][0]
    assert body["total"] == 1 and body["limit"] == 50 and body["offset"] == 0
    assert calls[-1][1] == {"language": "Go", "risk": "at_risk"}
    assert "LIMIT 50 OFFSET 0" in calls[-1][0]
    assert "COUNT(*) OVER()" in calls[-1][0]


def test_findings_no_filters(calls):
    client.get("/api/findings")
    assert calls[-1][1] == {"language": None, "risk": None}


def test_findings_pagination(calls):
    body = client.get("/api/findings?limit=25&offset=50").json()
    assert body["limit"] == 25 and body["offset"] == 50
    assert "LIMIT 25 OFFSET 50" in calls[-1][0]


def test_findings_pagination_clamped(calls):
    body = client.get("/api/findings?limit=999&offset=-3").json()
    assert body["limit"] == 100 and body["offset"] == 0
    assert "LIMIT 100 OFFSET 0" in calls[-1][0]


def test_trace(calls):
    body = client.get("/api/findings/moment/moment/trace").json()
    assert body["trace_id"] == "tr-1" and body["steps"][0]["tool_name"] == "t"


def test_trace_not_ready_for_old_findings(calls):
    body = client.get("/api/findings/old/repo/trace").json()
    assert body["status"] == "not_ready" and body["steps"] == [] and body["trace_id"] == "tr-0"


def test_trace_404(calls):
    assert client.get("/api/findings/missing/repo/trace").status_code == 404


def test_runs_latest(calls):
    assert client.get("/api/runs/latest").json()["run_id"] == "r2"

