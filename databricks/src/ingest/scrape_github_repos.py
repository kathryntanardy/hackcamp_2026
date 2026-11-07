# Databricks notebook source
# MAGIC %md
# MAGIC # Ticket #3: freeze a small, real GitHub corpus
# MAGIC Run `github_scrape` with the existing bundle. No pip installs are needed.
# MAGIC For a smoke run: `repo_limit=5`, `minimum_repos=5`, `publish=false`.
# MAGIC Only a validated 50+ repo snapshot may replace the pipeline's active input.

# COMMAND ----------

import json
import socket
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


# IDs only: none of the generated metrics from seed_sample_repos.py are used.
# Interleave languages so a five-repo smoke test exercises every cluster.
REPOS_BY_LANGUAGE = {
    "Python": [
        "psf/requests", "pallets/flask", "encode/httpx", "fastapi/fastapi",
        "python-poetry/poetry", "aio-libs/aiohttp", "kennethreitz/records",
        "joke2k/faker", "pydata/xarray", "scrapy/scrapy", "pandas-dev/pandas",
        "numpy/numpy", "scipy/scipy", "django/django", "pallets/werkzeug",
        "pytest-dev/pytest", "pydantic/pydantic", "sphinx-doc/sphinx",
        "celery/celery", "matplotlib/matplotlib",
    ],
    "JavaScript": [
        "facebook/react", "vuejs/vue", "vercel/next.js", "expressjs/express",
        "lodash/lodash", "axios/axios", "mrdoob/three.js", "jquery/jquery",
        "moment/moment", "request/request", "webpack/webpack", "babel/babel",
        "eslint/eslint", "prettier/prettier", "nodejs/node", "sveltejs/svelte",
        "rollup/rollup", "socketio/socket.io", "chartjs/Chart.js", "jashkenas/underscore",
    ],
    "Go": [
        "golang/go", "gin-gonic/gin", "spf13/cobra", "sirupsen/logrus",
        "urfave/cli", "labstack/echo", "go-chi/chi", "gorilla/mux",
        "dgrijalva/jwt-go", "hashicorp/terraform", "prometheus/prometheus",
        "etcd-io/etcd", "kubernetes/kubernetes", "moby/moby", "gohugoio/hugo",
        "caddyserver/caddy", "gofiber/fiber", "go-gorm/gorm", "stretchr/testify",
        "uber-go/zap",
    ],
    "Rust": [
        "rust-lang/rust", "tokio-rs/tokio", "serde-rs/serde", "clap-rs/clap",
        "BurntSushi/ripgrep", "sharkdp/fd", "actix/actix-web", "hyperium/hyper",
        "rust-lang/cargo", "diesel-rs/diesel", "rayon-rs/rayon", "rust-lang/regex",
        "rust-lang/rustfmt", "rust-lang/rust-clippy", "dtolnay/anyhow",
        "dtolnay/thiserror", "seanmonstar/reqwest", "tokio-rs/axum",
        "crossbeam-rs/crossbeam", "rustls/rustls",
    ],
    "Java": [
        "spring-projects/spring-boot", "apache/kafka", "elastic/elasticsearch",
        "google/guava", "junit-team/junit5", "FasterXML/jackson-databind",
        "netty/netty", "hibernate/hibernate-orm", "codehaus/jackson", "square/okhttp",
        "apache/maven", "apache/dubbo", "apache/lucene", "apache/hadoop",
        "spring-projects/spring-framework", "mockito/mockito", "junit-team/junit4",
        "apache/commons-lang", "apache/commons-io", "google/gson",
    ],
}
CURATED_REPOS = [
    repos[i] for i in range(20) for repos in REPOS_BY_LANGUAGE.values()
]


class CollectionError(RuntimeError):
    """Safe to log: never include request headers, tokens or raw error bodies."""


class AuthenticationError(CollectionError):
    pass


def iso_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_query(repo_ids):
    fields = []
    for i, repo in enumerate(repo_ids):
        owner, name = repo.split("/", 1)
        fields.append(
            f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
            " nameWithOwner name owner { login } primaryLanguage { name }"
            " stargazerCount isArchived pushedAt latestRelease { publishedAt }"
            " issues(states: OPEN) { totalCount }"
            " pullRequests(states: OPEN) { totalCount }"
            " defaultBranchRef { target { ... on Commit {"
            " recent: history(since: $since90, until: $asOf) { totalCount }"
            " total: history(since: $since180, until: $asOf) { totalCount }"
            " } } } }"
        )
    return (
        "query($since90: GitTimestamp!, $since180: GitTimestamp!, $asOf: GitTimestamp!) {"
        + " ".join(fields) + " }"
    )


def retry_delay(headers, attempt, now=None):
    """Honour GitHub's delay, but never block the hackathon on a long reset."""
    now = time.time() if now is None else now
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = parsedate_to_datetime(retry_after).timestamp() - now
    elif headers.get("X-RateLimit-Remaining") == "0":
        delay = float(headers.get("X-RateLimit-Reset", now + 61)) - now + 1
    else:
        delay = 2 ** attempt
    if delay > 30:
        raise CollectionError("Rate limit requires a long wait; keep the summary and rerun later.")
    return max(0, delay)


def fetch_batch(repo_ids, token, as_of, *, opener=urllib.request.urlopen, sleep=time.sleep):
    variables = {
        "since90": iso_utc(as_of - timedelta(days=90)),
        "since180": iso_utc(as_of - timedelta(days=180)),
        "asOf": iso_utc(as_of),
    }
    body = json.dumps({"query": build_query(repo_ids), "variables": variables}).encode()
    for attempt in range(3):
        request = urllib.request.Request(
            "https://api.github.com/graphql", data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept": "application/vnd.github+json", "User-Agent": "hackcamp-corpus-explorer"},
            method="POST",
        )
        headers = {}
        try:
            with opener(request, timeout=30) as response:
                headers = response.headers
                result = json.load(response)
            errors = result.get("errors", [])
            types = {error.get("type") for error in errors}
            if types & {"UNAUTHORIZED", "FORBIDDEN"}:
                raise AuthenticationError("GitHub token lacks permission to read the requested data.")
            if "RATE_LIMITED" not in types:
                if not isinstance(result.get("data"), dict):
                    raise CollectionError("GitHub returned no repository data; check the GraphQL query.")
                return result
        except urllib.error.HTTPError as exc:
            headers = exc.headers
            status = exc.code
            exc.close()
            if status == 401:
                raise AuthenticationError("GitHub authentication failed; replace hackcamp/github_token.") from None
            if status == 403 and not (
                headers.get("Retry-After") or headers.get("X-RateLimit-Remaining") == "0"
            ):
                raise AuthenticationError("GitHub denied access; check token permissions.") from None
            if status not in (403, 429, 500, 502, 503, 504):
                raise CollectionError(f"GitHub request failed with HTTP {status}.") from None
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            pass
        except (ValueError, TypeError):
            raise CollectionError("GitHub returned an invalid JSON response.") from None
        if attempt < 2:
            sleep(retry_delay(headers, attempt))
    raise CollectionError("GitHub request failed after 3 attempts.")


def normalize_repo(repo, pulled_at):
    branch = repo.get("defaultBranchRef") or {}
    history = branch.get("target") or {}
    recent = (history.get("recent") or {}).get("totalCount")
    total = (history.get("total") or {}).get("totalCount")
    previous = total - recent if recent is not None and total is not None else None
    if previous is not None and previous < 0:
        raise CollectionError("Inconsistent GitHub commit totals.")
    return {
        "repo_id": repo["nameWithOwner"], "pulled_at": pulled_at,
        "payload": {
            "name": repo["name"], "owner": repo["owner"]["login"],
            "language": (repo.get("primaryLanguage") or {}).get("name"),
            "stars": repo["stargazerCount"], "is_archived": repo["isArchived"],
            "pushed_at": repo.get("pushedAt"),
            "last_release_at": (repo.get("latestRelease") or {}).get("publishedAt"),
            "commits_90d": recent, "commits_prev_90d": previous,
            "open_issues": repo["issues"]["totalCount"],
            "open_prs": repo["pullRequests"]["totalCount"],
            "contributors": None, "dependents": None,
            "maintainer_reply_rate": None, "top_contributor_share": None,
            "source": "github_graphql",
        },
    }


def collect_repos(repo_ids, token, as_of, batch_size=5, *, fetch=fetch_batch):
    records, failures, seen = [], [], set()
    fatal = None
    for start in range(0, len(repo_ids), batch_size):
        batch = repo_ids[start:start + batch_size]
        try:
            result = fetch(batch, token, as_of)
        except CollectionError as exc:
            fatal = {"reason": str(exc), "authentication_failed": isinstance(exc, AuthenticationError)}
            failures.extend({"repo_id": repo, "reason": str(exc)} for repo in repo_ids[start:])
            break
        errors = result.get("errors", [])
        for i, requested in enumerate(batch):
            alias = f"r{i}"
            # Any errored field makes this repo incomplete; keep good siblings.
            errored = any(not e.get("path") or e["path"][0] == alias for e in errors)
            repo = result["data"].get(alias)
            if errored or repo is None:
                failures.append({"repo_id": requested, "reason": "Repository unavailable or incomplete GraphQL result."})
                continue
            try:
                record = normalize_repo(repo, iso_utc(as_of))
                canonical = record["repo_id"].lower()
                if canonical in seen:
                    raise CollectionError("Duplicate canonical repository after a rename/redirect.")
                seen.add(canonical)
                records.append(record)
            except (KeyError, TypeError, CollectionError):
                failures.append({"repo_id": requested, "reason": "Invalid or duplicate repository payload."})
    return records, failures, fatal


def list_or_empty(fs, path):
    try:
        return fs.ls(path)
    except Exception as exc:
        if any(marker in str(exc) for marker in ("FileNotFoundException", "does not exist", "PATH_NOT_FOUND")):
            return []
        raise


def publish_snapshot(fs, root, snapshot, expected_count):
    """Archive the previous input (including seeds) rather than mixing it in."""
    active = f"{root}/repos"
    previous = f"{snapshot}/previous_repos"
    had_previous = bool(list_or_empty(fs, active))
    if had_previous and not fs.mv(active, previous, True):
        raise CollectionError("Could not archive the previous input; snapshot was not published.")
    active_created = False
    try:
        fs.mkdirs(active)
        active_created = True
        # Copy explicit filenames; directory-copy nesting differs across filesystems.
        for entry in fs.ls(f"{snapshot}/repos"):
            if not fs.cp(f"{snapshot}/repos/{entry.name}", f"{active}/{entry.name}"):
                raise CollectionError("Could not publish the collected snapshot.")
        if len(fs.ls(active)) != expected_count:
            raise CollectionError("Published file count does not match the snapshot.")
    except Exception:
        # Keep failed copies for diagnosis, then restore the old pipeline input.
        if active_created and not fs.mv(active, f"{snapshot}/failed_publish", True):
            raise CollectionError("Publish failed; restore previous_repos before running the pipeline.") from None
        if had_previous and not fs.mv(previous, active, True):
            raise CollectionError("Publish failed; restore previous_repos before running the pipeline.") from None
        raise


def run_notebook(dbutils):
    defaults = {"volume_path": "/Volumes/hackcamp/raw/github", "repo_limit": "100",
                "minimum_repos": "50", "batch_size": "5", "publish": "true"}
    for name, default in defaults.items():
        dbutils.widgets.text(name, default)
    root = dbutils.widgets.get("volume_path").rstrip("/")
    limit = int(dbutils.widgets.get("repo_limit"))
    minimum = int(dbutils.widgets.get("minimum_repos"))
    batch_size = int(dbutils.widgets.get("batch_size"))
    publish_value = dbutils.widgets.get("publish").lower()
    if not root.startswith("/Volumes/") or len(root.split("/")) < 5:
        raise ValueError("volume_path must be a Unity Catalog Volume path.")
    if not 1 <= minimum <= limit <= len(CURATED_REPOS) or not 1 <= batch_size <= 10:
        raise ValueError("Require 1 <= minimum_repos <= repo_limit <= 100 and batch_size <= 10.")
    if publish_value not in ("true", "false"):
        raise ValueError("publish must be true or false.")
    publish = publish_value == "true"
    if publish and minimum < 50:
        raise ValueError("Smoke runs must use publish=false; publishing requires minimum_repos >= 50.")

    as_of = datetime.now(timezone.utc)
    run_id = as_of.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    snapshot = f"{root}/snapshots/{run_id}"
    summary_path = f"{snapshot}/summary.json"
    try:
        dbutils.fs.mkdirs(snapshot)
    except Exception:
        raise CollectionError(
            f"Cannot create a snapshot under {root}. Confirm the Volume exists and the job's "
            "run-as account has USE CATALOG, USE SCHEMA, READ VOLUME and WRITE VOLUME. "
            "No GitHub requests or active-input changes were made; a summary cannot be saved "
            "until Volume access works."
        ) from None
    requested = CURATED_REPOS[:limit]
    summary = {"run_id": run_id, "source": "github_graphql", "pulled_at": iso_utc(as_of),
               "requested_repos": requested, "requested_count": limit,
               "minimum_repos": minimum, "published": False, "meets_f1": False,
               "snapshot_path": snapshot, "summary_path": summary_path}
    records, failures, fatal = [], [], None
    try:
        try:
            token = dbutils.secrets.get("hackcamp", "github_token")
        except Exception:
            raise AuthenticationError("Set the Databricks secret hackcamp/github_token before scraping.") from None
        if not token.strip():
            raise AuthenticationError("The Databricks GitHub secret is empty.")
        records, failures, fatal = collect_repos(requested, token, as_of, batch_size)
        dbutils.fs.mkdirs(f"{snapshot}/repos")
        for record in records:
            filename = record["repo_id"].replace("/", "__") + ".json"
            dbutils.fs.put(f"{snapshot}/repos/{filename}", json.dumps(record), overwrite=False)
        languages = sorted({r["payload"]["language"] for r in records if r["payload"]["language"]})
        summary["languages"] = languages
        auth_failed = fatal and fatal["authentication_failed"]
        if auth_failed or len(records) < minimum:
            raise CollectionError(f"Collected {len(records)}/{limit} repos; minimum is {minimum}. " + (fatal["reason"] if fatal else "See failures."))
        meets_f1 = len(records) >= 50 and set(REPOS_BY_LANGUAGE).issubset(languages)
        if publish and not meets_f1:
            raise CollectionError("Publishing requires at least 50 real repos covering all five intended languages.")
        if publish:
            publish_snapshot(dbutils.fs, root, snapshot, len(records))
            summary["published"] = True
        summary["meets_f1"] = meets_f1
        summary["status"] = "published" if publish else "smoke_passed"
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc) if isinstance(exc, CollectionError) else "Snapshot storage or unexpected collection failure; see the job run."
        if not records and not failures:
            failures = [{"repo_id": repo, "reason": summary["error"]} for repo in requested]
        raise
    finally:
        summary.update(successful_count=len(records), successful_repos=[r["repo_id"] for r in records],
                       failed_count=len(failures), failures=failures,
                       finished_at=iso_utc(datetime.now(timezone.utc)))
        dbutils.fs.put(summary_path, json.dumps(summary, indent=2), overwrite=True)
        print(json.dumps(summary, indent=2))
    dbutils.jobs.taskValues.set(key="summary_path", value=summary_path)
    dbutils.jobs.taskValues.set(key="successful_count", value=len(records))
    return summary


# COMMAND ----------

if "dbutils" in globals():
    run_notebook(dbutils)
