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
        if "/security-advisories" in url:
            return httpx.Response(200, json=[])
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
    assert out["mode"] == "code" and out["advisory_ids"] == []


def test_scan_repo_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        scan.ask_gemini("p", httpx.Client(), "m")


@pytest.fixture
def db(monkeypatch):
    rows, log = [], []

    def fake_query(statement, params=None):
        log.append(statement)
        if "FROM eligible_gold WHERE" in statement:
            return [] if params["repo_id"] == "missing/repo" else [{"repo_id": params["repo_id"]}]
        if statement.startswith("INSERT"):
            rows.append({**params, "scanned_at": "2026-11-07T20:00:00"})
            return []
        if "FROM hackcamp.agent.security_scans" in statement:
            return [r for r in rows if r["repo_id"] == params["repo_id"]][-1:]
        return []

    monkeypatch.setattr(main, "query", fake_query)
    return log


def test_post_scan_stores_and_get_returns_it(db, monkeypatch):
    monkeypatch.setattr(scan, "scan_repo", lambda rid: {
        "repo_id": rid, "commit_sha": "abc", "model": "m", "files": ["f.py"],
        "mode": "code", "advisory_ids": [],
        "summary": "ok", "findings": [{"file": "f.py", "severity": "low", "title": "t",
                                       "description": "d", "recommendation": "r"}]})
    assert client.get("/api/scans/a/b").status_code == 404
    r = client.post("/api/scans/a/b")
    assert r.status_code == 200
    assert r.json()["files"] == ["f.py"] and r.json()["findings"][0]["title"] == "t"
    assert any("CREATE TABLE IF NOT EXISTS hackcamp.agent.security_scans" in s for s in db)
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
        "mode": "code", "advisory_ids": [],
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


ADVISORY = {
    "ghsa_id": "GHSA-aaaa-bbbb-cccc", "cve_id": "CVE-2022-1", "severity": "high", "state": "published",
    "summary": "ReDoS in date parsing", "description": "Long strings hang preprocessRFC2822.",
    "html_url": "https://github.com/a/b/security/advisories/GHSA-aaaa-bbbb-cccc",
    "cwes": [{"cwe_id": "CWE-1333", "name": "ReDoS"}],
    "vulnerabilities": [{"package": {"ecosystem": "npm", "name": "b"},
                         "vulnerable_version_range": "< 2.29.4", "patched_versions": "2.29.4",
                         "vulnerable_functions": ["preprocessRFC2822"]}],
}


def test_normalize_advisory_and_hints():
    a = scan.normalize_advisory(ADVISORY)
    assert a["cwes"] == ["CWE-1333"]
    assert a["packages"][0]["patched_versions"] == "2.29.4"
    assert scan.advisory_hints([a]) == ("preprocessrfc2822",)


def test_pick_files_hints_outrank_keywords():
    tree = [{"type": "blob", "path": "src/auth/jwt.js", "size": 5000},
            {"type": "blob", "path": "src/lib/create/from-string.js", "size": 5000}]
    assert scan.pick_files(tree, limit=1) == ["src/auth/jwt.js"]
    assert scan.pick_files(tree, limit=1, hints=("from",)) == ["src/lib/create/from-string.js"]


DIFF = "--- a/x.go\n+++ b/x.go\n@@ -1,2 +1,3 @@\n m := re.Find(s)\n+if m == nil { return }\n use(m[1])"


def _two_call_handler(adv_out, code_out, seen, code_status=200):
    """Fake GitHub + Gemini. Tells the two Gemini calls apart by their response schema."""
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "/security-advisories" in url:
            return httpx.Response(200, json=[ADVISORY, {**ADVISORY, "ghsa_id": "GHSA-x", "state": "draft"}])
        if url.endswith("/repos/a/b"):
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/trees/main" in url:
            return httpx.Response(200, json={"sha": "abc", "tree": [
                {"type": "blob", "path": "src/auth.js", "size": 300},
                {"type": "blob", "path": "src/preprocessRFC2822.js", "size": 300}]})
        if "raw.githubusercontent.com" in url:
            return httpx.Response(200, text="x\n" * 200)
        if "generativelanguage" in url:
            body = json.loads(req.content)
            schema = body["generationConfig"]["responseSchema"]
            kind = "adv" if "ghsa_id" in schema["properties"]["findings"]["items"]["required"] else "code"
            seen[kind] = body["contents"][0]["parts"][0]["text"]
            if kind == "code" and code_status != 200:
                return httpx.Response(code_status)
            out = adv_out if kind == "adv" else code_out
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": json.dumps(out)}]}}]})
        return httpx.Response(404)
    return handler


ADV_OUT = {"summary": "Upgrade.", "findings": [
    {"ghsa_id": "GHSA-aaaa-bbbb-cccc", "severity": "high", "title": "ReDoS",
     "description": "d", "recommendation": "Upgrade to 2.29.4", "workaround": "limit input length",
     "file": "src/preprocessRFC2822.js", "line": 3}]}
CODE_OUT = {"summary": "One bug.", "findings": [
    {"ghsa_id": "GHSA-made-up", "file": "src/auth.js", "line": 5, "severity": "medium", "title": "Weak check",
     "description": "d", "recommendation": "Compare in constant time.", "code_fix": DIFF}]}


def _mock(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(scan.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


def test_scan_repo_runs_advisory_fixes_and_code_review(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = {}
    _mock(monkeypatch, _two_call_handler(ADV_OUT, CODE_OUT, seen))
    out = scan.scan_repo("a/b")
    assert out["mode"] == "advisories+code" and out["advisory_ids"] == ["GHSA-aaaa-bbbb-cccc"]
    assert out["files"][0] == "src/preprocessRFC2822.js"  # hinted file first
    assert "GHSA-aaaa-bbbb-cccc" in seen["adv"] and "2.29.4" in seen["adv"]
    assert "src/auth.js" in seen["code"]  # code review got the files too
    adv, code = out["findings"]
    assert adv["patched_versions"] == "2.29.4" and adv["cwe"] == "CWE-1333"
    assert adv["advisory_url"].endswith("GHSA-aaaa-bbbb-cccc")
    assert "ghsa_id" not in code and code["code_fix"] == DIFF  # code findings never claim an advisory
    assert out["summary"] == "Upgrade. One bug."  # one sentence from each call


def test_scan_repo_keeps_advisory_fixes_if_code_review_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(scan, "RETRY_DELAY", 0)
    _mock(monkeypatch, _two_call_handler(ADV_OUT, CODE_OUT, {}, code_status=500))
    out = scan.scan_repo("a/b")
    assert [f.get("ghsa_id") for f in out["findings"]] == ["GHSA-aaaa-bbbb-cccc"]
    assert "code review part of this scan failed" in out["summary"]


def test_enrich_handles_findings_without_file():
    out = scan.enrich([{"ghsa_id": "G", "severity": "low", "title": "t", "description": "d",
                        "recommendation": "r"}], "a/b", "abc")
    assert out[0]["code_url"] is None and out[0]["vuln_bucket"] == "Other / unclassified"


def test_ask_gemini_strips_echoed_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    echoed = 'Check Content-Type.```json\n{"summary": "s", "findings": []}\n```'
    body = {"summary": "s", "findings": [{"workaround": echoed, "recommendation": "```python\nx()\n```"}]}
    c = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]})))
    f = scan.ask_gemini("p", c, "m")["findings"][0]
    assert f["workaround"] == "Check Content-Type."
    assert f["recommendation"] == "```python\nx()\n```"  # real code blocks kept


def test_pick_files_skips_docs_src_and_scripts():
    tree = [{"type": "blob", "path": "docs_src/sql_databases/tutorial001.py", "size": 5000},
            {"type": "blob", "path": "scripts/playwright/sql/image01.py", "size": 5000},
            {"type": "blob", "path": "fastapi/security/oauth2.py", "size": 5000}]
    assert scan.pick_files(tree) == ["fastapi/security/oauth2.py"]


def test_first_sentence():
    assert scan.first_sentence("Disable BodyDump on uploads. It buffers everything.") == "Disable BodyDump on uploads."
    assert scan.first_sentence("Pin to v4.16.1 or later") == "Pin to v4.16.1 or later."
    assert scan.first_sentence("Validate input, e.g. reject long strings. More.") == \
        "Validate input, e.g. reject long strings."
    junk = "Enforce auth before routing.functionality.text.word.count.check:11.words.ok.done"
    assert scan.first_sentence(junk) == "Enforce auth before routing."
    assert scan.first_sentence("Restrict static files.\u5de7\u5999,") == "Restrict static files."
    assert scan.first_sentence("Disable BodyDump on affected routes, or set the limit higher.") == \
        "Disable BodyDump on affected routes."
    assert scan.first_sentence("Reject requests before proxy routes or enforce auth upstream.") == \
        "Reject requests before proxy routes or enforce auth upstream."  # no comma: ambiguous, keep
    assert scan.first_sentence("Limit bodies; log failures.") == "Limit bodies."
    assert scan.first_sentence("Reject inputs of 1,000 or more characters.") == \
        "Reject inputs of 1,000 or more characters."
    assert scan.first_sentence("") == ""
    long = ("Keep protected files outside the static serving directory or enforce authorization "
            "before static route matching decisions occur switch to default routing configurations")
    assert scan.first_sentence(long) == "Keep protected files outside the static serving directory."


def test_dedupes_and_trims_workaround_on_read():
    a = scan.normalize_advisory(ADVISORY)
    out = scan.attach_advisories([{"ghsa_id": a["ghsa_id"], "workaround": "Limit input. Then log it."},
                                  {"ghsa_id": a["ghsa_id"], "workaround": "dupe"}], [a])
    assert len(out) == 1
    assert scan.enrich(out, "a/b", "abc")[0]["workaround"] == "Limit input."




def test_contribute_fix_only_when_unpatched_and_located():
    base = {"file": "x.go", "code_fix": DIFF}
    assert scan.contribute_fix(base) == DIFF
    assert scan.contribute_fix({**base, "patched_versions": "1.2.3"}) is None  # already fixed upstream
    assert scan.contribute_fix({**base, "file": None}) is None  # Gemini didn't see the code
    assert scan.contribute_fix({**base, "code_fix": "Add a nil check."}) is None  # not a diff
    assert scan.contribute_fix({"file": "x.go"}) is None


def test_enrich_adds_code_fix_and_report_url():
    out = scan.enrich([{"file": "x.go", "line": 2, "severity": "low", "title": "t", "description": "d",
                        "recommendation": "r", "code_fix": DIFF,
                        "report_url": "https://github.com/a/b/security/advisories/new"}], "a/b", "abc")[0]
    assert out["code_fix"] == DIFF and out["report_url"].endswith("/security/advisories/new")
    old = scan.enrich([{"file": "x.go", "severity": "low", "title": "t", "description": "d",
                        "recommendation": "r"}], "a/b", "abc")[0]
    assert old["code_fix"] is None and old["report_url"] == "https://github.com/a/b/security"


def test_report_url_prefers_private_reporting():
    def client(enabled_status, body):
        return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(enabled_status, json=body)))
    assert scan.report_url("a/b", client(200, {"enabled": True})) == "https://github.com/a/b/security/advisories/new"
    assert scan.report_url("a/b", client(200, {"enabled": False})) == "https://github.com/a/b/security/policy"
    assert scan.report_url("a/b", client(404, {})) == "https://github.com/a/b/security/policy"


def _adv(ghsa, summary, patched=None, description="", functions=()):
    return scan.normalize_advisory({"ghsa_id": ghsa, "summary": summary, "description": description,
                                    "vulnerabilities": [{"package": {"name": "p"}, "patched_versions": patched,
                                                         "vulnerable_functions": list(functions)}]})


def test_advisory_identifiers_from_unpatched_only():
    advs = [_adv("G1", "safe_join can produce unsafe paths", description="Uses `os.path.isabs` and `pattern`."),
            _adv("G2", "AiragMcpController saveAndSync command injection in mcp.go"),
            _adv("G3", "fixed_already in parse_x", patched="1.2"),
            _adv("G4", "OpenAI token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xxxxxxxx leak", functions=["pkg.LoadModel"])]
    assert scan.advisory_identifiers(advs, limit=10) == [
        "LoadModel", "safe_join", "AiragMcpController", "saveAndSync", "mcp.go"]  # plain `isabs`/`pattern` skipped
    assert len(scan.advisory_identifiers(advs)) == scan.MAX_CODE_SEARCHES


def test_locate_files_uses_code_search_and_stops_on_rate_limit():
    calls = []

    def handler(req):
        calls.append(req.url.params["q"])
        if len(calls) == 1:
            return httpx.Response(200, json={"items": [{"path": "src/security.py"}, {"path": "src/utils.py"}]})
        return httpx.Response(403)
    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert scan.locate_files("a/b", ["safe_join", "other", "third"], c) == ["src/security.py", "src/utils.py"]
    assert calls == ['"safe_join" repo:a/b', '"other" repo:a/b']  # stopped after the 403


def test_pick_files_puts_located_files_first():
    tree = [{"type": "blob", "path": "src/auth/jwt.py", "size": 5000},
            {"type": "blob", "path": "src/werkzeug/security.py", "size": 5000},
            {"type": "blob", "path": "CHANGES.rst", "size": 5000}]
    picked = scan.pick_files(tree, limit=2, priority=["CHANGES.rst", "src/werkzeug/security.py"])
    assert picked == ["src/werkzeug/security.py", "src/auth/jwt.py"]  # non-source priority path ignored


def test_fetch_advisories_keeps_unpatched_within_cap(monkeypatch):
    monkeypatch.setattr(scan, "MAX_ADVISORIES", 2)
    raw = [{**ADVISORY, "ghsa_id": f"P{i}"} for i in range(3)]
    raw.append({**ADVISORY, "ghsa_id": "U1", "vulnerabilities": [{"package": {"name": "b"}, "patched_versions": None}]})
    c = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=raw)))
    assert [a["ghsa_id"] for a in scan.fetch_advisories("a/b", c)] == ["U1", "P0"]


def test_quota_message():
    body = {"error": {"code": 429, "message": "You exceeded your current quota...", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateContentInputTokensPerModelPerMinute-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]}}
    assert scan.quota_message(httpx.Response(429, json=body)) == (
        "Gemini quota exceeded (GenerateContentInputTokensPerModelPerMinute-FreeTier). Retry in about 41s.")
    assert scan.quota_message(httpx.Response(429, text="nope")) == "Gemini quota exceeded. Try again later."


def test_first_sentences():
    text = "Upgrade Echo to v4.16.1 now. Proxy bypass is critical. The code looks sound. No issues found."
    assert scan.first_sentences(text, 2) == "Upgrade Echo to v4.16.1 now. Proxy bypass is critical."
    assert scan.first_sentences(text, 1) == "Upgrade Echo to v4.16.1 now."
    assert scan.first_sentences("Use e.g. a limit. Then more.", 1) == "Use e.g. a limit."
    assert scan.first_sentences("No period here", 2) == "No period here"
    assert scan.first_sentences("", 2) == ""
