"""Execute the API's SQL against historical fixtures, without a live warehouse.

SQLite supports the window functions used for eligibility. Only table names and
Databricks JSON functions need adapting; the ranking, joins and filters run as-is.
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)
ELIGIBLE = {"test/active", "test/restored", "test/uninvestigated", "test/archived"}
EXCLUDED = {"test/gold-ignored", "test/finding-ignored", "test/both-ignored", "test/orphan"}


@pytest.fixture
def history(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("to_json", 1, lambda value: value)
    conn.create_function("from_json", 2, lambda value, schema: value)
    conn.create_function("array_contains", 2, lambda values, item: item in json.loads(values or "[]"))

    def table(name, rows):
        columns = list(rows[0])
        conn.execute(f"CREATE TABLE {name} ({', '.join(columns)})")
        conn.executemany(
            f"INSERT INTO {name} VALUES ({', '.join('?' for _ in columns)})",
            [[row[column] for column in columns] for row in rows],
        )

    def gold(repo_id, status, date):
        return dict(
            repo_id=repo_id, run_id=date, scored_at=date, name=repo_id.split("/")[1],
            owner="test", language="Python", health_score=80, status=status,
            importance=3, x=0, y=0, cat_x=0, cat_y=0, stars=100, dependents=0,
            is_archived=repo_id == "test/archived", category="Back-end",
            vuln_buckets='["Injection"]', advisory_count=1, max_severity="high",
            max_cvss=8.1, days_since_release=20, commit_trend_pct=10,
        )

    # Old eligible rows must not replace the latest exclusion. Conversely, old
    # ignored rows must not hide a repo whose latest records are eligible.
    gold_rows = [gold(rid, "healthy", "2026-11-07") for rid in ELIGIBLE | (EXCLUDED - {"test/orphan"})]
    gold_rows += [gold(rid, "ignored", "2026-11-08")
                  for rid in ["test/gold-ignored", "test/both-ignored"]]
    gold_rows += [gold("test/restored", "ignored", "2026-11-06")]
    table("repo_health", gold_rows)

    def finding(repo_id, risk, date):
        return dict(
            repo_id=repo_id, run_id=date, risk_level=risk, confidence=0.9,
            headline=risk, explanation="Evidence", evidence="[]", alternatives="[]",
            changed_since_last="unchanged", tool_calls=2, trace_id=repo_id + date,
            investigated_at=date,
        )

    findings = [finding(rid, "at_risk", "2026-11-07")
                for rid in (ELIGIBLE | EXCLUDED) - {"test/uninvestigated"}]
    findings += [finding(rid, "ignored", "2026-11-08")
                 for rid in ["test/finding-ignored", "test/both-ignored"]]
    findings += [finding("test/restored", "ignored", "2026-11-06")]
    table("findings", findings)
    table("runs", [dict(run_id="2026-11-08", started_at="2026-11-08")])
    table("repo_summaries", [dict(repo_id=rid, summary="Summary") for rid in ELIGIBLE | EXCLUDED])
    table("repos", [dict(
        repo_id=rid, pushed_at="2026-11-07", last_release_at="2026-11-01",
        commits_90d=11, commits_prev_90d=10, open_issues=2, open_prs=1,
        contributors=5, maintainer_reply_rate=None, top_contributor_share=None,
        advisory_fetch_status="ok", description="Description", topics='["python"]',
    ) for rid in ELIGIBLE | EXCLUDED])
    table("repo_advisories", [dict(
        repo_id=rid, ghsa_id="GHSA-test", cve_id="CVE-test", severity="high",
        cvss_score=8.1, cwes='["CWE-89"]', vuln_bucket="Injection",
        summary="Advisory", published_at="2026-01-01",
    ) for rid in ELIGIBLE | EXCLUDED])
    table("trace_steps", [dict(
        repo_id=f["repo_id"], run_id=f["run_id"], trace_id=f["trace_id"],
        payload=json.dumps({"trace_id": f["trace_id"], "steps": []}),
    ) for f in findings])
    table("security_scans", [dict(
        repo_id=rid, mode="code", commit_sha="abc", model="test", files='["src/auth.py"]',
        advisory_ids="[]", summary="Stored scan", findings="[]", scanned_at="2026-11-07",
    ) for rid in ELIGIBLE | EXCLUDED])

    statements = []

    def query(statement, params=None):
        statements.append(statement)
        for schema, names in {
            "gold": ["repo_health", "repo_summaries"],
            "agent": ["findings", "runs", "trace_steps", "security_scans"],
            "silver": ["repos", "repo_advisories"],
        }.items():
            for name in names:
                statement = statement.replace(f"hackcamp.{schema}.{name}", name)
        return [dict(row) for row in conn.execute(statement, params or {}).fetchall()]

    monkeypatch.setattr(main, "query", query)
    monkeypatch.setattr(main, "vector_search", lambda *args: [
        (rid, 0.9) for rid in sorted(ELIGIBLE | EXCLUDED)
    ])
    yield conn, statements
    conn.close()


def test_repo_list_and_search_use_the_same_latest_eligibility(history):
    repos = client.get("/api/repos")
    assert repos.status_code == 200
    assert {row["repo_id"] for row in repos.json()} == ELIGIBLE
    search = client.get("/api/search", params={"q": "http clients"})
    assert search.status_code == 200
    assert set(search.json()["repo_ids"]) == ELIGIBLE


def test_findings_count_and_filters_do_not_resurrect_older_verdicts(history):
    body = client.get("/api/findings", params={"risk": "at_risk", "limit": 1}).json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    all_findings = client.get("/api/findings").json()["items"]
    assert {row["repo_id"] for row in all_findings} == ELIGIBLE - {"test/uninvestigated"}
    assert client.get("/api/findings", params={"risk": "ignored"}).json()["items"] == []


@pytest.mark.parametrize("repo_id", sorted(EXCLUDED | {"test/missing"}))
@pytest.mark.parametrize("route", ["/api/repos/{repo_id}", "/api/findings/{repo_id}/trace", "/api/scans/{repo_id}"])
def test_direct_urls_cannot_reveal_excluded_or_absent_repos(history, route, repo_id):
    assert client.get(route.format(repo_id=repo_id)).status_code == 404


@pytest.mark.parametrize("repo_id", sorted(EXCLUDED | {"test/missing"}))
def test_excluded_scans_are_rejected_before_work_or_writes(history, monkeypatch, repo_id):
    def unexpected_scan(*args):
        pytest.fail("Excluded repository must not trigger a scan")

    monkeypatch.setattr(main.scan, "scan_repo", unexpected_scan)
    assert client.post(f"/api/scans/{repo_id}").status_code == 404
    assert len(history[1]) == 1  # Eligibility read only; no scan storage mutation.


@pytest.mark.parametrize("repo_id", sorted(ELIGIBLE))
def test_eligible_details_and_stored_scans_still_work(history, repo_id):
    detail = client.get(f"/api/repos/{repo_id}")
    assert detail.status_code == 200
    assert detail.json()["repo_id"] == repo_id
    assert client.get(f"/api/scans/{repo_id}").status_code == 200
    if repo_id == "test/uninvestigated":
        assert detail.json()["verdict"] is None
        assert client.get(f"/api/findings/{repo_id}/trace").status_code == 404
    else:
        assert detail.json()["verdict"]["risk_level"] == "at_risk"
        assert client.get(f"/api/findings/{repo_id}/trace").status_code == 200


def test_exclusions_preserve_internal_history(history):
    before = history[0].execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    client.get("/api/repos")
    client.get("/api/findings")
    client.get("/api/repos/test/finding-ignored")
    assert history[0].execute("SELECT COUNT(*) FROM findings").fetchone()[0] == before
    assert history[0].execute("SELECT COUNT(*) FROM findings WHERE risk_level = 'ignored'").fetchone()[0] == 3
