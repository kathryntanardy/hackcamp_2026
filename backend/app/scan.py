"""On-demand Gemini security scan. Every scan reviews the riskiest-looking source files for
unreported vulnerabilities (with patches for contributors). If the repo also has published GitHub
security advisories, a second Gemini call runs in parallel and explains how to fix or work around
each one. mode = "advisories+code" when there were advisories, else "code". (Rows stored
before the code review ran on every scan have mode "advisories".)"""

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
import functools
import json
import os
import re
import time

import httpx

GITHUB_API = "https://api.github.com"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.6-flash"

MAX_FILES = 40  # code review
MAX_ADVISORY_FILES = 15  # advisory call: the advisory-hinted files rank first
MAX_CODE_SEARCHES = 4  # GitHub code search allows 10 requests/minute per token
MAX_ADVISORIES = 10
MAX_ADVISORY_DESC = 3000
MAX_OUTPUT_TOKENS = 16384
MAX_FILE_BYTES = 60_000
MAX_TOTAL_CHARS = 800_000
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
    r"(^|/)(tests?|__tests__|spec|specs|testdata|fixtures?|examples?|docs?|docs_src|scripts|benches?|"
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


def contribute_fix(f: dict) -> str | None:
    """Only offer a patch when it's useful and grounded: no released fix yet, and Gemini located
    the vulnerable code in a file it was shown."""
    fix = (f.get("code_fix") or "").strip()
    if not fix or f.get("patched_versions") or not f.get("file") or "@@" not in fix:
        return None
    return fix


def enrich(findings: list[dict], repo_id: str, commit_sha: str) -> list[dict]:
    """Fields added after Gemini answers, so they cost no tokens."""
    return [{**f, "vuln_bucket": bucket_for_cwe(f.get("cwe")),
             "code_url": code_url(repo_id, commit_sha, f["file"], f.get("line")) if f.get("file") else None,
             # Trimmed on read so older stored scans get short workarounds too.
             "workaround": first_sentence(f.get("workaround") or ""),
             "code_fix": contribute_fix(f),
             # Security fixes go through a private report, never a public PR. Older scans lack
             # report_url, so fall back to the repo's Security tab.
             "report_url": f.get("report_url") or f"https://github.com/{repo_id}/security"}
            for f in findings]


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
                    "code_fix": {"type": "STRING"},
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
  a CWE id like "CWE-79" if one fits, what's wrong, and a recommendation: 1-2 plain-English
  sentences on how to fix it (no code there).
- code_fix: for contributors who want to fix this upstream. A unified diff ("--- a/<path>",
  "+++ b/<path>", "@@" hunks with real context lines copied from the file shown) that fixes the
  vulnerable code. Only include it when the vulnerable code is in the files shown; otherwise use
  an empty string. Never invent code you were not shown.
- Prefer one of these CWE ids when it fits: {preferred_cwes}.
- If nothing real stands out, return an empty findings list and say so in the summary.
- Summary: one short sentence on the overall security posture of these files.

{files}"""

# Same finding shape as the code scan plus the advisory it answers; file/line are optional
# because the vulnerable code may not be among the files shown.
_ADVISORY_ITEM = RESPONSE_SCHEMA["properties"]["findings"]["items"]
ADVISORY_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "findings": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"ghsa_id": {"type": "STRING"},
                           "workaround": {"type": "STRING"},
                           **_ADVISORY_ITEM["properties"]},
            "required": ["ghsa_id", "severity", "title", "description", "recommendation"],
        }},
    },
    "required": ["summary", "findings"],
}

ADVISORY_PROMPT = """You are a senior application-security engineer. The GitHub repository {repo_id}
has the published security advisories below. For EACH advisory, tell a developer who depends on
this project exactly how to fix or mitigate it.

Rules:
- Return exactly one finding per advisory, with its ghsa_id.
- description: 1-2 sentences on what an attacker can do, in plain English.
- recommendation: for users of the library, 1-2 plain-English sentences, no code. If a patched
  version exists, say which version to upgrade to. If none exists, say there is no fixed release
  yet and what to do instead.
- code_fix: for contributors who want to fix this upstream. A unified diff ("--- a/<path>",
  "+++ b/<path>", "@@" hunks with real context lines copied from the file shown) that fixes the
  vulnerable code. Only include it when the vulnerable code is in the files shown; otherwise use
  an empty string. Never invent code you were not shown.
  Only give a code_fix for advisories with NO patched version; patched ones are already fixed.
- workaround: how to stay safe without changing the library, written as a terse checklist item
  with a single action, e.g. "Reject inputs over 1,000 characters before calling parse()."
  Empty string if there is no sensible workaround.
- If you can locate the vulnerable code in the files shown, give its file path and line number
  (from the line prefixes). Otherwise leave file and line out. Never invent a location.
- severity: reuse the advisory's severity. cwe: the advisory's CWE id like "CWE-79" if it has one.
- Summary: one short sentence on how urgent these advisories are and what to do first.

ADVISORIES:
{advisories}

SOURCE FILES:
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


def score_path(path: str, size: int, hints: tuple[str, ...] = ()) -> float:
    """Higher = more worth scanning. 0 = skip. Hints (from advisories) outrank keywords."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SOURCE_EXT or SKIP_PARTS.search(path) or size > MAX_FILE_BYTES or size < 200:
        return 0
    lower = path.lower()
    score = sum(w for k, w in RISKY_KEYWORDS.items() if k in lower)
    score += sum(20 for h in hints if h in lower)
    return score + 0.5 if score else 0.1  # plain source files only fill leftover slots


def pick_files(tree: list[dict], limit: int = MAX_FILES, hints: tuple[str, ...] = (),
               priority: list[str] = ()) -> list[str]:
    """Priority paths (code-search hits for advisory identifiers) first, then by path score."""
    scored = [(score_path(t["path"], t.get("size", 0), hints), t["path"])
              for t in tree if t.get("type") == "blob"]
    scored = [s for s in scored if s[0] > 0]
    eligible = {p for _, p in scored}
    first = [p for p in dict.fromkeys(priority) if p in eligible]
    scored.sort(key=lambda s: (-s[0], len(s[1])))
    rest = [p for _, p in scored if p not in first]
    return (first + rest)[:limit]


def fetch_files(repo_id: str, client: httpx.Client, hints: tuple[str, ...] = (),
                priority: list[str] = ()) -> tuple[str, dict[str, str]]:
    """Return (commit_sha, {path: content}) for the chosen files on the default branch."""
    repo = client.get(f"{GITHUB_API}/repos/{repo_id}")
    repo.raise_for_status()
    branch = repo.json()["default_branch"]
    tree = client.get(f"{GITHUB_API}/repos/{repo_id}/git/trees/{branch}", params={"recursive": "1"})
    tree.raise_for_status()
    body = tree.json()
    files, total = {}, 0
    for path in pick_files(body["tree"], hints=hints, priority=priority):
        raw = client.get(f"https://raw.githubusercontent.com/{repo_id}/{body['sha']}/{path}")
        if raw.status_code != 200:
            continue
        text = raw.text
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        files[path] = text
        total += len(text)
    return body["sha"], files


def normalize_advisory(raw: dict) -> dict:
    cwes = [c["cwe_id"] for c in raw.get("cwes") or [] if isinstance(c, dict) and c.get("cwe_id")]
    cwes += [c for c in raw.get("cwe_ids") or [] if c and c not in cwes]
    return {
        "ghsa_id": raw["ghsa_id"], "cve_id": raw.get("cve_id"), "severity": raw.get("severity"),
        "cwes": cwes, "summary": raw.get("summary") or "",
        "description": (raw.get("description") or "")[:MAX_ADVISORY_DESC],
        "html_url": raw.get("html_url") or f"https://github.com/advisories/{raw['ghsa_id']}",
        "published_at": raw.get("published_at"),
        "packages": [{"ecosystem": (v.get("package") or {}).get("ecosystem"),
                      "name": (v.get("package") or {}).get("name"),
                      "vulnerable_versions": v.get("vulnerable_version_range"),
                      "patched_versions": v.get("patched_versions"),
                      "vulnerable_functions": v.get("vulnerable_functions") or []}
                     for v in raw.get("vulnerabilities") or []],
    }


def fetch_advisories(repo_id: str, client: httpx.Client) -> list[dict]:
    """Published repository security advisories, full detail (patched versions, functions)."""
    resp = client.get(f"{GITHUB_API}/repos/{repo_id}/security-advisories", params={"per_page": 100})
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    items = [a for a in resp.json() if a.get("ghsa_id") and a.get("state", "published") == "published"]
    advisories = [normalize_advisory(a) for a in items]
    # Unpatched first: they're the ones a code fix can help with, so they must survive the cap.
    advisories.sort(key=lambda a: not is_unpatched(a))
    return advisories[:MAX_ADVISORIES]


def report_url(repo_id: str, client: httpx.Client) -> str:
    """Where a contributor should send a security fix: the private vulnerability report form if
    the repo has it enabled, else the security policy page (which links SECURITY.md contacts)."""
    try:
        resp = client.get(f"{GITHUB_API}/repos/{repo_id}/private-vulnerability-reporting")
        enabled = resp.status_code == 200 and resp.json().get("enabled") is True
    except (httpx.HTTPError, ValueError):
        enabled = False
    path = "security/advisories/new" if enabled else "security/policy"
    return f"https://github.com/{repo_id}/{path}"


def advisory_hints(advisories: list[dict]) -> tuple[str, ...]:
    """Lowercase name fragments of vulnerable functions, used to pull matching files first."""
    hints = set()
    for a in advisories:
        for pkg in a["packages"]:
            for fn in pkg["vulnerable_functions"]:
                hints.update(w.lower() for w in re.split(r"[^A-Za-z0-9]+", fn) if len(w) >= 4)
    return tuple(sorted(hints))


_NOT_IDENTS = re.compile(r"^(GHSA|CVE|CWE)\b|^v?\d", re.IGNORECASE)
_BRANDS = {"github", "gitlab", "javascript", "typescript", "openai", "postgresql", "mysql", "mongodb",
           "graphql", "fastapi", "nodejs", "macos", "iphone", "ipados", "youtube", "webassembly"}
_IDENT = re.compile(
    r"\b([A-Za-z]\w*_\w+)\b"                          # snake_case
    r"|\b([a-z]+[A-Z]\w*|[A-Z][a-z0-9]+[A-Z][a-z]\w*)\b"  # camelCase / CamelCase
    r"|\b([\w-]+\.(?:py|go|js|ts|tsx|jsx|java|kt|rs|rb|php|c|cc|cpp|h|cs|swift))\b")  # file.ext


def is_unpatched(advisory: dict) -> bool:
    return not any(p["patched_versions"] for p in advisory["packages"])


def advisory_identifiers(advisories: list[dict], limit: int = MAX_CODE_SEARCHES) -> list[str]:
    """Code names to search for, from unpatched advisories only (they're the ones that get a
    code fix): vulnerable functions first, then names mentioned in the summary/description."""
    found = []
    for a in filter(is_unpatched, advisories):
        found += [fn for p in a["packages"] for fn in p["vulnerable_functions"]]
    for field in ("summary", "description"):
        for a in filter(is_unpatched, advisories):
            # Backticked text only counts if it is itself an identifier (not `pattern`, `--pre=x`).
            text = re.sub(r"`([^`]*)`", r" \1 ", a[field] or "")
            for m in _IDENT.finditer(text):
                found.append(next(g for g in m.groups() if g))
    out = []
    for name in found:
        name = re.split(r"\.|::|#", name.strip("()"))[-1] if not re.search(r"\.\w{1,4}$", name) else name
        name = name.strip("()")
        if (4 <= len(name) <= 40 and not _NOT_IDENTS.search(name) and name.lower() not in _BRANDS
                and name not in out):
            out.append(name)
    return out[:limit]


def locate_files(repo_id: str, identifiers: list[str], client: httpx.Client) -> list[str]:
    """Paths whose code mentions the identifiers, via GitHub code search (needs a token).
    Best effort: stops quietly on auth or rate-limit errors."""
    paths = []
    for ident in identifiers:
        try:
            resp = client.get(f"{GITHUB_API}/search/code", params={"q": f'"{ident}" repo:{repo_id}'})
        except httpx.HTTPError:
            break
        if resp.status_code != 200:
            break
        paths += [item["path"] for item in resp.json().get("items", [])[:3]]
    return list(dict.fromkeys(paths))


def _file_blocks(files: dict[str, str]) -> str:
    blocks = []
    for path, text in files.items():
        numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))
        blocks.append(f"=== FILE: {path} ===\n{numbered}")
    return "\n\n".join(blocks)


def build_prompt(repo_id: str, files: dict[str, str]) -> str:
    preferred = ", ".join(f"CWE-{c}" for c in CWE_TO_BUCKET)
    return PROMPT.format(repo_id=repo_id, preferred_cwes=preferred, files=_file_blocks(files))


def build_advisory_prompt(repo_id: str, advisories: list[dict], files: dict[str, str]) -> str:
    adv = json.dumps([{k: v for k, v in a.items() if k != "html_url"} for a in advisories], indent=1)
    return ADVISORY_PROMPT.format(repo_id=repo_id, advisories=adv,
                                  files=_file_blocks(files) or "(no source files available)")


def ask_gemini(prompt: str, client: httpx.Client, model: str, schema: dict = RESPONSE_SCHEMA) -> dict:
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
                    "maxOutputTokens": MAX_OUTPUT_TOKENS,  # stops runaway repeat loops early
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                },
            },
            timeout=180,
        )
        if resp.status_code not in (429, 503):
            break
        time.sleep(RETRY_DELAY * (attempt + 1))
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(text)
    result["findings"] = [{k: _strip_echo(v) for k, v in f.items()} for f in result.get("findings", [])]
    return result


def quota_message(resp: httpx.Response) -> str:
    """Short, readable reason for a Gemini 429: which quota ran out and when to retry."""
    try:
        details = resp.json()["error"].get("details", [])
    except (ValueError, KeyError, AttributeError):
        details = []
    quotas = [v.get("quotaId") for d in details for v in d.get("violations", []) if v.get("quotaId")]
    retry = next((d.get("retryDelay") for d in details if d.get("retryDelay")), None)
    msg = "Gemini quota exceeded" + (f" ({', '.join(dict.fromkeys(quotas))})" if quotas else "")
    return msg + (f". Retry in about {retry}." if retry else ". Try again later.")


def _strip_echo(value):
    """Gemini sometimes repeats its whole JSON answer inside a string field; cut that tail off."""
    if not isinstance(value, str):
        return value
    i = value.find("```json")
    return value[:i].rstrip() if i >= 0 and '"findings"' in value[i:] else value


def first_sentences(text: str, n: int) -> str:
    """The first n sentences of text (keeps the scan summary short)."""
    ends = list(re.finditer(r"(?<!e\.g)(?<!i\.e)[.!?](?=\s|$)", text.strip()))
    return text.strip()[:ends[n - 1].end()] if len(ends) >= n else text.strip()


def first_sentence(text: str) -> str:
    """Workarounds as one short action. Keeps the first sentence, drops ", or <alternative>" tails,
    and drops junk Gemini sometimes glues on (e.g. "settings.functionality.word.count.check:11...")."""
    junk = re.search(r"\S{40,}", text)
    if junk:
        text = text[:junk.start()] + junk.group().split(".")[0] + "."
    end = re.search(r"(?<!e\.g)(?<!i\.e)[.!?](?=\s|$|[^\x00-\x7F])", text)
    text = text[:end.start()] if end else text
    text = re.split(r", or |; ", text.strip(), maxsplit=1)[0].rstrip(" ,;")
    if len(text.split()) > 15:  # long run-on: keep the first alternative ("A or B" -> "A")
        text = re.split(r" or ", text, maxsplit=1)[0]
    return f"{text}." if text else ""


def attach_advisories(findings: list[dict], advisories: list[dict]) -> list[dict]:
    """Add the advisory's link and versions from GitHub data rather than trusting the model."""
    by_id = {a["ghsa_id"]: a for a in advisories}
    out, seen = [], set()
    for f in findings:
        if f.get("ghsa_id") in seen:  # Gemini occasionally answers the same advisory twice
            continue
        seen.add(f.get("ghsa_id"))
        a = by_id.get(f.get("ghsa_id"))
        if a:
            f = {**f, "advisory_url": a["html_url"], "cve_id": a["cve_id"],
                 "patched_versions": ", ".join(p["patched_versions"] for p in a["packages"]
                                               if p["patched_versions"]) or None,
                 "cwe": f.get("cwe") or (a["cwes"][0] if a["cwes"] else None)}
        out.append(f)
    return out


log = logging.getLogger(__name__)


def _gemini(prompt: str, model: str, schema: dict = RESPONSE_SCHEMA) -> dict:
    with httpx.Client() as client:  # one client per thread
        return ask_gemini(prompt, client, model, schema)


def scan_repo(repo_id: str) -> dict:
    """Code review of the riskiest files, plus advisory fixes (in parallel) if the repo has any.
    Advisory findings carry a ghsa_id; code-review findings don't."""
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    with httpx.Client(headers=_github_headers(), timeout=30, follow_redirects=True) as gh:
        advisories = fetch_advisories(repo_id, gh)
        located = locate_files(repo_id, advisory_identifiers(advisories), gh)
        sha, files = fetch_files(repo_id, gh, advisory_hints(advisories), located)
        report = report_url(repo_id, gh)
    base = {"repo_id": repo_id, "commit_sha": sha, "model": model, "files": list(files),
            "mode": "advisories+code" if advisories else "code",
            "advisory_ids": [a["ghsa_id"] for a in advisories]}
    if not advisories and not files:
        return {**base, "summary": "No security-relevant source files found to scan.", "findings": []}

    with ThreadPoolExecutor(max_workers=2) as pool:
        code_job = pool.submit(_gemini, build_prompt(repo_id, files), model) if files else None
        adv_files = dict(list(files.items())[:MAX_ADVISORY_FILES])  # keeps token use (and 429s) down
        adv_job = (pool.submit(_gemini, build_advisory_prompt(repo_id, advisories, adv_files), model,
                               ADVISORY_RESPONSE_SCHEMA) if advisories else None)
        adv = adv_job.result() if adv_job else None
        try:
            code = code_job.result() if code_job else None
        except Exception as e:
            if not adv:
                raise
            # Advisory fixes are the main answer here; don't lose them to a flaky second call.
            log.warning("code review failed for %s: %s", repo_id, e)
            code = {"summary": "The code review part of this scan failed; rescan to retry.",
                    "findings": []}

    findings, summaries = [], []
    if adv:
        findings += attach_advisories(adv.get("findings", []), advisories)
        summaries.append(adv.get("summary", ""))
    if code:
        # A code finding can't claim an advisory id; that would hide it in the advisory list.
        findings += [{k: v for k, v in f.items() if k != "ghsa_id"} for f in code.get("findings", [])]
        summaries.append(code.get("summary", ""))
    return {**base, "summary": " ".join(first_sentences(x, 1) for x in summaries if x and x.strip()),
            "findings": [{**f, "report_url": report} for f in findings]}
