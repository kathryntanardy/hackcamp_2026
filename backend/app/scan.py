"""On-demand Gemini code scan: pick the riskiest-looking files from a GitHub repo,
send them to Gemini, and get back vulnerabilities with fix recommendations."""

import base64
import functools
import json
import os
import re
import time

import httpx

GITHUB_API = "https://api.github.com"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.6-flash"

MAX_FILES = 15
MAX_FILE_BYTES = 60_000
MAX_TOTAL_CHARS = 400_000
RETRY_DELAY = 5  # seconds; grows per attempt

SOURCE_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".scala", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift",
}
# Path fragments that tend to hold security-relevant code; weight = how suspicious.
RISKY_KEYWORDS = {
    "auth": 5, "login": 5, "password": 5, "passwd": 5, "token": 4, "jwt": 5, "session": 4,
    "crypto": 5, "cipher": 4, "hash": 3, "secret": 4, "cookie": 4, "csrf": 5, "cors": 4,
    "sanitiz": 5, "escape": 4, "xss": 5, "template": 3, "render": 2, "sql": 5, "query": 3,
    "exec": 5, "shell": 5, "command": 4, "eval": 5, "spawn": 4, "subprocess": 5,
    "deserial": 5, "serial": 3, "pickle": 5, "yaml": 3, "xml": 3, "parse": 3, "decode": 3,
    "upload": 5, "download": 3, "file": 2, "path": 3, "redirect": 4, "url": 3,
    "http": 2, "request": 2, "proxy": 3, "socket": 3, "tls": 4, "ssl": 4, "cert": 4,
    "permission": 4, "acl": 4, "admin": 3, "unsafe": 4,
}
SKIP_PARTS = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testdata|fixtures?|examples?|docs?|benches?|"
    r"vendor|third_party|node_modules|dist|build|\.github)(/|$)|(_test|\.test|\.spec)\.",
    re.IGNORECASE,
)

# Copy of CWE_TO_BUCKET in databricks/.../repo_health/transformations/vuln_buckets.py so scan
# findings use the same 10 bucket labels as advisories (the backend deploys without that code).
# tests/test_scan.py fails if the two drift apart.
BUCKET_OTHER = "Other / unclassified"
CWE_TO_BUCKET = {
    "94": "Code execution", "77": "Code execution", "78": "Code execution",
    "502": "Unsafe deserialization",
    "787": "Memory safety", "125": "Memory safety", "416": "Memory safety", "119": "Memory safety",
    "89": "Injection", "79": "Injection", "91": "Injection",
    "22": "Path traversal & file access", "434": "Path traversal & file access",
    "59": "Path traversal & file access",
    "1321": "Prototype pollution",
    "1333": "Denial of service", "400": "Denial of service", "770": "Denial of service",
    "200": "Data exposure", "532": "Data exposure", "312": "Data exposure",
    "918": "Network & TLS", "295": "Network & TLS", "601": "Network & TLS",
    "287": "Auth & access control", "285": "Auth & access control",
    "862": "Auth & access control", "352": "Auth & access control",
}


def bucket_for_cwe(cwe: str | None) -> str:
    digits = "".join(ch for ch in str(cwe or "") if ch.isdigit())
    return CWE_TO_BUCKET.get(digits, BUCKET_OTHER)


def code_url(repo_id: str, commit_sha: str, file: str, line: int | None) -> str:
    """Permalink pinned to the scanned commit, so line numbers stay valid."""
    url = f"https://github.com/{repo_id}/blob/{commit_sha}/{file}"
    return f"{url}#L{line}" if line else url


def enrich(findings: list[dict], repo_id: str, commit_sha: str) -> list[dict]:
    """Fields added after Gemini answers, so they cost no tokens."""
    return [{**f, "vuln_bucket": bucket_for_cwe(f.get("cwe")),
             "code_url": code_url(repo_id, commit_sha, f["file"], f.get("line"))} for f in findings]


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "file": {"type": "STRING"},
                    "line": {"type": "INTEGER"},
                    "severity": {"type": "STRING", "enum": ["critical", "high", "medium", "low"]},
                    "cwe": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "recommendation": {"type": "STRING"},
                },
                "required": ["file", "severity", "title", "description", "recommendation"],
            },
        },
    },
    "required": ["summary", "findings"],
}

PROMPT = """You are a senior application-security reviewer. Review the source files below from the
GitHub repository {repo_id} for security vulnerabilities (injection, unsafe deserialization,
path traversal, SSRF, auth/session flaws, weak crypto, memory-safety issues, ReDoS, etc.).

Rules:
- Only report issues you can point to in the code shown. No generic advice.
- For each issue give the file path, the line number (from the line prefixes), severity,
  a CWE id like "CWE-79" if one fits, what's wrong, and a concrete fix (code if helpful).
- Prefer one of these CWE ids when it fits: {preferred_cwes}.
- If nothing real stands out, return an empty findings list and say so in the summary.
- Summary: 2-3 sentences on the overall security posture of these files.

{files}"""


@functools.cache
def _databricks_github_token() -> str | None:
    """Same PAT the scraper uses (hackcamp/github_token). None if unreachable."""
    try:
        from databricks.sdk import WorkspaceClient
        value = WorkspaceClient().secrets.get_secret("hackcamp", "github_token").value
        return base64.b64decode(value).decode().strip() or None
    except Exception:
        return None


def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hackcamp-corpus-explorer"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or _databricks_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def score_path(path: str, size: int) -> float:
    """Higher = more worth scanning. 0 = skip."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SOURCE_EXT or SKIP_PARTS.search(path) or size > MAX_FILE_BYTES or size < 200:
        return 0
    lower = path.lower()
    score = sum(w for k, w in RISKY_KEYWORDS.items() if k in lower)
    return score + 0.5 if score else 0.1  # plain source files only fill leftover slots


def pick_files(tree: list[dict], limit: int = MAX_FILES) -> list[str]:
    scored = [(score_path(t["path"], t.get("size", 0)), t["path"])
              for t in tree if t.get("type") == "blob"]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: (-s[0], len(s[1])))
    return [p for _, p in scored[:limit]]


def fetch_files(repo_id: str, client: httpx.Client) -> tuple[str, dict[str, str]]:
    """Return (commit_sha, {path: content}) for the chosen files on the default branch."""
    repo = client.get(f"{GITHUB_API}/repos/{repo_id}")
    repo.raise_for_status()
    branch = repo.json()["default_branch"]
    tree = client.get(f"{GITHUB_API}/repos/{repo_id}/git/trees/{branch}", params={"recursive": "1"})
    tree.raise_for_status()
    body = tree.json()
    files, total = {}, 0
    for path in pick_files(body["tree"]):
        raw = client.get(f"https://raw.githubusercontent.com/{repo_id}/{body['sha']}/{path}")
        if raw.status_code != 200:
            continue
        text = raw.text
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        files[path] = text
        total += len(text)
    return body["sha"], files


def build_prompt(repo_id: str, files: dict[str, str]) -> str:
    blocks = []
    for path, text in files.items():
        numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))
        blocks.append(f"=== FILE: {path} ===\n{numbered}")
    preferred = ", ".join(f"CWE-{c}" for c in CWE_TO_BUCKET)
    return PROMPT.format(repo_id=repo_id, preferred_cwes=preferred, files="\n\n".join(blocks))


def ask_gemini(prompt: str, client: httpx.Client, model: str) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    for attempt in range(3):  # Gemini throws 429/503 under load; usually clears in seconds
        resp = client.post(
            f"{GEMINI_API}/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                    "responseSchema": RESPONSE_SCHEMA,
                },
            },
            timeout=180,
        )
        if resp.status_code not in (429, 503):
            break
        time.sleep(RETRY_DELAY * (attempt + 1))
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def scan_repo(repo_id: str) -> dict:
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    with httpx.Client(headers=_github_headers(), timeout=30, follow_redirects=True) as gh:
        sha, files = fetch_files(repo_id, gh)
    if not files:
        return {"repo_id": repo_id, "commit_sha": sha, "model": model, "files": [],
                "summary": "No security-relevant source files found to scan.", "findings": []}
    with httpx.Client() as client:
        result = ask_gemini(build_prompt(repo_id, files), client, model)
    return {"repo_id": repo_id, "commit_sha": sha, "model": model, "files": list(files),
            "summary": result.get("summary", ""), "findings": result.get("findings", [])}
