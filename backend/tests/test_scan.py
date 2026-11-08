import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import scan

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def no_databricks_secret(monkeypatch):
    monkeypatch.setattr(scan, "_databricks_github_token", lambda: None)


def test_pick_files_prefers_risky_source_and_skips_tests():
    tree = [
        {"type": "blob", "path": "src/auth/jwt.py", "size": 5000},
        {"type": "blob", "path": "src/utils/strings.py", "size": 5000},  # no keyword: filler
        {"type": "blob", "path": "tests/test_auth.py", "size": 5000},  # test dir
        {"type": "blob", "path": "src/http/request.py", "size": 5000},
        {"type": "blob", "path": "docs/auth.md", "size": 5000},  # not source
        {"type": "blob", "path": "src/sql/query_huge.py", "size": 10_000_000},  # too big
        {"type": "tree", "path": "src/auth", "size": 0},
    ]
    assert scan.pick_files(tree) == ["src/auth/jwt.py", "src/http/request.py", "src/utils/strings.py"]
    assert scan.pick_files(tree, limit=2) == ["src/auth/jwt.py", "src/http/request.py"]


def test_build_prompt_numbers_lines():
    prompt = scan.build_prompt("a/b", {"x.py": "import os\nos.system(cmd)"})
    assert "=== FILE: x.py ===" in prompt and "2: os.system(cmd)" in prompt and "a/b" in prompt


def test_scan_repo_end_to_end(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gemini_out = {"summary": "One issue.", "findings": [
        {"file": "src/exec_cmd.py", "line": 2, "severity": "high", "cwe": "CWE-78",
         "title": "Command injection", "description": "d", "recommendation": "use subprocess list args"}]}

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.endswith("/repos/a/b"):
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/trees/main" in url:
            return httpx.Response(200, json={"sha": "abc", "tree": [
                {"type": "blob", "path": "src/exec_cmd.py", "size": 300}]})
        if "raw.githubusercontent.com/a/b/abc/src/exec_cmd.py" in url:
            return httpx.Response(200, text="import os\nos.system(user_input)\n" + "#" * 300)
        if "generativelanguage" in url:
            assert req.headers["x-goog-api-key"] == "test-key"
            assert "os.system(user_input)" in json.loads(req.content)["contents"][0]["parts"][0]["text"]
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": json.dumps(gemini_out)}]}}]})
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(scan.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    out = scan.scan_repo("a/b")
    assert out["files"] == ["src/exec_cmd.py"] and out["commit_sha"] == "abc"
    assert out["findings"][0]["cwe"] == "CWE-78"


def test_scan_repo_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        scan.ask_gemini("p", httpx.Client(), "m")


@pytest.fixture
def db(monkeypatch):
    rows, log = [], []

    def fake_query(statement, params=None):
        log.append(statement)
        if "FROM gold WHERE" in statement:
            return [] if params["repo_id"] == "missing/repo" else [{"repo_id": params["repo_id"]}]
        if statement.startswith("INSERT"):
            rows.append({**params, "scanned_at": "2026-11-07T20:00:00"})
            return []
        if "FROM hackcamp.agent.code_scans" in statement:
            return [r for r in rows if r["repo_id"] == params["repo_id"]][-1:]
        return []

    monkeypatch.setattr(main, "query", fake_query)
    return log


def test_post_scan_stores_and_get_returns_it(db, monkeypatch):
    monkeypatch.setattr(scan, "scan_repo", lambda rid: {
        "repo_id": rid, "commit_sha": "abc", "model": "m", "files": ["f.py"],
        "summary": "ok", "findings": [{"file": "f.py", "severity": "low", "title": "t",
                                       "description": "d", "recommendation": "r"}]})
    assert client.get("/api/scans/a/b").status_code == 404
    r = client.post("/api/scans/a/b")
    assert r.status_code == 200
    assert r.json()["files"] == ["f.py"] and r.json()["findings"][0]["title"] == "t"
    assert any("CREATE TABLE IF NOT EXISTS hackcamp.agent.code_scans" in s for s in db)
    assert client.get("/api/scans/a/b").json()["summary"] == "ok"


def test_post_scan_unknown_repo_404(db):
    assert client.post("/api/scans/missing/repo").status_code == 404


def test_post_scan_upstream_failure_502(db, monkeypatch):
    def boom(rid):
        raise RuntimeError("GEMINI_API_KEY is not set")
    monkeypatch.setattr(scan, "scan_repo", boom)
    r = client.post("/api/scans/a/b")
    assert r.status_code == 502 and "GEMINI_API_KEY" in r.json()["detail"]


def test_ask_gemini_retries_on_503(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(scan, "RETRY_DELAY", 0)
    replies = iter([httpx.Response(503), httpx.Response(200, json={"candidates": [{"content": {
        "parts": [{"text": '{"summary": "s", "findings": []}'}]}}]})])
    c = httpx.Client(transport=httpx.MockTransport(lambda req: next(replies)))
    assert scan.ask_gemini("p", c, "m") == {"summary": "s", "findings": []}


def test_bucket_for_cwe():
    assert scan.bucket_for_cwe("CWE-78") == "Code execution"
    assert scan.bucket_for_cwe("cwe-79") == "Injection"
    assert scan.bucket_for_cwe("CWE-327") == "Other / unclassified"
    assert scan.bucket_for_cwe(None) == "Other / unclassified"


def test_cwe_map_matches_pipeline():
    import importlib.util
    from pathlib import Path
    src = (Path(__file__).parents[2] / "databricks/src/pipelines/repo_health/transformations/vuln_buckets.py")
    spec = importlib.util.spec_from_file_location("pipeline_vuln_buckets", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert scan.CWE_TO_BUCKET == mod.CWE_TO_BUCKET
    assert scan.BUCKET_OTHER == mod.BUCKET_OTHER


def test_get_scan_adds_bucket_names(db, monkeypatch):
    monkeypatch.setattr(scan, "scan_repo", lambda rid: {
        "repo_id": rid, "commit_sha": "abc", "model": "m", "files": ["f.py"], "summary": "ok",
        "findings": [{"file": "f.py", "line": 7, "cwe": "CWE-78", "severity": "low", "title": "t",
                      "description": "d", "recommendation": "r"},
                     {"file": "g.py", "severity": "low", "title": "t2",
                      "description": "d", "recommendation": "r"}]})
    client.post("/api/scans/a/b")
    findings = client.get("/api/scans/a/b").json()["findings"]
    assert [f["vuln_bucket"] for f in findings] == ["Code execution", "Other / unclassified"]
    assert [f["code_url"] for f in findings] == ["https://github.com/a/b/blob/abc/f.py#L7",
                                                 "https://github.com/a/b/blob/abc/g.py"]


def test_code_url():
    assert scan.code_url("a/b", "abc", "src/x.py", 41) == "https://github.com/a/b/blob/abc/src/x.py#L41"
    assert scan.code_url("a/b", "abc", "src/x.py", None) == "https://github.com/a/b/blob/abc/src/x.py"
