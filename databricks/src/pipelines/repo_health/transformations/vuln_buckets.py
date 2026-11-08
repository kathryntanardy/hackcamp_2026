"""CWE → vulnerability-bucket mapping (F15 / PRD Pages and UX)."""

from __future__ import annotations

# Exact bucket labels from the PRD. Order is stable for tests / UI chips.
BUCKET_CODE_EXECUTION = "Code execution"
BUCKET_UNSAFE_DESER = "Unsafe deserialization"
BUCKET_MEMORY_SAFETY = "Memory safety"
BUCKET_INJECTION = "Injection"
BUCKET_PATH_TRAVERSAL = "Path traversal & file access"
BUCKET_PROTOTYPE_POLLUTION = "Prototype pollution"
BUCKET_DOS = "Denial of service"
BUCKET_DATA_EXPOSURE = "Data exposure"
BUCKET_NETWORK_TLS = "Network & TLS"
BUCKET_AUTH = "Auth & access control"
BUCKET_OTHER = "Other / unclassified"
BUCKET_NONE = "No GitHub advisories"

# First matching CWE wins when an advisory lists several.
CWE_TO_BUCKET: dict[str, str] = {
    "94": BUCKET_CODE_EXECUTION,
    "77": BUCKET_CODE_EXECUTION,
    "78": BUCKET_CODE_EXECUTION,
    "502": BUCKET_UNSAFE_DESER,
    "787": BUCKET_MEMORY_SAFETY,
    "125": BUCKET_MEMORY_SAFETY,
    "416": BUCKET_MEMORY_SAFETY,
    "119": BUCKET_MEMORY_SAFETY,
    "89": BUCKET_INJECTION,
    "79": BUCKET_INJECTION,
    "91": BUCKET_INJECTION,
    "22": BUCKET_PATH_TRAVERSAL,
    "434": BUCKET_PATH_TRAVERSAL,
    "59": BUCKET_PATH_TRAVERSAL,
    "1321": BUCKET_PROTOTYPE_POLLUTION,
    "1333": BUCKET_DOS,
    "400": BUCKET_DOS,
    "770": BUCKET_DOS,
    "200": BUCKET_DATA_EXPOSURE,
    "532": BUCKET_DATA_EXPOSURE,
    "312": BUCKET_DATA_EXPOSURE,
    "918": BUCKET_NETWORK_TLS,
    "295": BUCKET_NETWORK_TLS,
    "601": BUCKET_NETWORK_TLS,
    "287": BUCKET_AUTH,
    "285": BUCKET_AUTH,
    "862": BUCKET_AUTH,
    "352": BUCKET_AUTH,
}

SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "moderate": 3,
    "low": 2,
    "unknown": 1,
}


def normalize_cwe_id(raw: str | None) -> str | None:
    """Accept 'CWE-94', 'cwe-94', or '94' → digits only."""
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text:
        return None
    if text.startswith("CWE-"):
        text = text[4:]
    elif text.startswith("CWE"):
        text = text[3:].lstrip("-")
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or None


def bucket_for_cwes(cwes: list[str] | None) -> str:
    """Map an advisory's CWE list to exactly one bucket (first hit, else Other)."""
    for raw in cwes or []:
        cwe = normalize_cwe_id(raw)
        if cwe and cwe in CWE_TO_BUCKET:
            return CWE_TO_BUCKET[cwe]
    return BUCKET_OTHER


def repo_vuln_buckets(
    advisory_buckets: list[str] | None,
    *,
    advisory_fetch_status: str | None,
    advisory_count: int,
) -> list[str]:
    """Union of advisory buckets; distinguish no-advisories from Other / failed fetch."""
    status = (advisory_fetch_status or "not_fetched").lower()
    if status == "ok" and advisory_count == 0:
        return [BUCKET_NONE]
    if advisory_count <= 0:
        # failed / not_fetched / empty — never claim "No GitHub advisories"
        return []
    seen: list[str] = []
    for b in advisory_buckets or []:
        if b and b not in seen and b != BUCKET_NONE:
            seen.append(b)
    return seen or [BUCKET_OTHER]


def severity_rank(severity: str | None) -> int:
    if not severity:
        return 0
    return SEVERITY_RANK.get(str(severity).strip().lower(), 0)


CATEGORIES = (
    "Front-end",
    "Back-end",
    "Machine learning",
    "Database",
    "Hardware/embedded",
    "DevOps & infra",
    "other",
)

# Keyword hints when ai_query is unavailable or returns an unknown label.
_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Front-end",
        (
            "react",
            "vue",
            "angular",
            "frontend",
            "front-end",
            "css",
            "ui",
            "browser",
            "dom",
            "webpack",
            "svelte",
        ),
    ),
    (
        "Machine learning",
        (
            "machine-learning",
            "machine learning",
            "deep-learning",
            "neural",
            "pytorch",
            "tensorflow",
            "llm",
            "nlp",
            "ml ",
            "ai ",
        ),
    ),
    (
        "Database",
        (
            "database",
            "sql",
            "postgres",
            "mysql",
            "mongodb",
            "redis",
            "orm",
            "sqlite",
            "cassandra",
        ),
    ),
    (
        "Hardware/embedded",
        (
            "embedded",
            "firmware",
            "iot",
            "arduino",
            "raspberry",
            "fpga",
            "hardware",
            "mcu",
        ),
    ),
    (
        "DevOps & infra",
        (
            "kubernetes",
            "docker",
            "devops",
            "terraform",
            "ci/cd",
            "infra",
            "ansible",
            "helm",
            "observability",
            "prometheus",
        ),
    ),
    (
        "Back-end",
        (
            "backend",
            "back-end",
            "server",
            "api",
            "http",
            "grpc",
            "microservice",
            "framework",
        ),
    ),
)


def normalize_category(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    lower = text.lower()
    for label in CATEGORIES:
        if lower == label.lower():
            return label
    # Model sometimes returns close variants
    aliases = {
        "frontend": "Front-end",
        "front end": "Front-end",
        "backend": "Back-end",
        "back end": "Back-end",
        "ml": "Machine learning",
        "machine-learning": "Machine learning",
        "devops": "DevOps & infra",
        "devops & infra": "DevOps & infra",
        "hardware": "Hardware/embedded",
        "embedded": "Hardware/embedded",
    }
    return aliases.get(lower)


def heuristic_category(description: str | None, topics: list[str] | None) -> str:
    """Cheap fallback when ai_query fails or has not run yet."""
    blob = f"{description or ''} {' '.join(topics or [])}".lower()
    for label, hints in _CATEGORY_HINTS:
        if any(h in blob for h in hints):
            return label
    return "other"
