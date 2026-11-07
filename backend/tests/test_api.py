from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.traces import spans_to_steps

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
        if "hackcamp.silver.repos" in statement:
            if params["repo_id"] == "missing/repo":
                return []
            return [{"repo_id": params["repo_id"], "name": "x", "days_since_release": 420,
                     "commit_trend_pct": -98.0, "pushed_at": None, "last_release_at": None,
                     "commits_90d": 1, "commits_prev_90d": 50, "open_issues": 40, "open_prs": 22,
                     "contributors": 35, "maintainer_reply_rate": 0.05,
                     "top_contributor_share": 0.8}]
        if "LIMIT 2" in statement:
            return [FINDING, {**FINDING, "run_id": "r1", "evidence": None}]
        if "SELECT run_id, trace_id" in statement:
            return [] if params["repo_id"] == "missing/repo" else [{"run_id": "r2", "trace_id": "tr-1"}]
        return [{"repo_id": "a/b", **FINDING}]

    monkeypatch.setattr(main, "query", fake_query)
    monkeypatch.setattr(main, "get_trace_steps", lambda tid: [{"step": 1, "tool": "t"}])
    return log


client = TestClient(main.app)


def test_repos(calls):
    assert client.get("/api/repos").status_code == 200


def test_repo_detail_splits_metrics_and_verdicts(calls):
    body = client.get("/api/repos/moment/moment").json()
    assert body["repo_id"] == "moment/moment"
    assert body["github_url"] == "https://github.com/moment/moment"
    assert body["metrics"]["commits_prev_90d"] == 50
    assert body["verdict"]["evidence"][0]["tool"] == "get_release_history"
    assert body["previous_verdict"]["run_id"] == "r1"
    assert body["previous_verdict"]["evidence"] == []


def test_repo_detail_404(calls):
    assert client.get("/api/repos/missing/repo").status_code == 404


def test_findings_passes_filters_as_params(calls):
    body = client.get("/api/findings?language=Go&risk=at_risk").json()
    assert body[0]["alternatives"] == []
    assert calls[-1][1] == {"language": "Go", "risk": "at_risk"}


def test_findings_no_filters(calls):
    client.get("/api/findings")
    assert calls[-1][1] == {"language": None, "risk": None}


def test_trace(calls):
    body = client.get("/api/findings/moment/moment/trace").json()
    assert body["trace_id"] == "tr-1" and body["steps"][0]["tool"] == "t"


def test_trace_404(calls):
    assert client.get("/api/findings/missing/repo/trace").status_code == 404


def test_runs_latest(calls):
    assert client.get("/api/runs/latest").json()["run_id"] == "r2"


def span(t, kind, name, inputs=None, outputs=None):
    return SimpleNamespace(start_time_ns=t, span_type=kind, name=name, inputs=inputs, outputs=outputs)


def test_spans_to_steps_orders_and_attaches_reasoning():
    spans = [
        span(4, "TOOL", "get_commit_trend", {"repo": "a/b"}, {"result": "not json"}),
        span(1, "AGENT", "investigate:a/b"),
        span(2, "CHAT_MODEL", "llm_decide", outputs={"content": "check releases first"}),
        span(3, "TOOL", "get_release_history", {"repo": "a/b"}, {"result": '{"days": 420}'}),
    ]
    steps = spans_to_steps(spans)
    assert [s["tool"] for s in steps] == ["get_release_history", "get_commit_trend"]
    assert steps[0]["result"] == {"days": 420} and steps[0]["reasoning"] == "check releases first"
    assert steps[1]["result"] == "not json" and steps[1]["reasoning"] is None
