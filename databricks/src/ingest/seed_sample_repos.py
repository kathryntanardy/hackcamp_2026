# Databricks notebook source
# MAGIC %md
# MAGIC # Seed sample GitHub repos into UC Volume
# MAGIC Writes ~50 mock repo payloads under `/Volumes/hackcamp/raw/github/repos/` for the Lakeflow pipeline.

# COMMAND ----------

import hashlib
import json
from datetime import datetime, timedelta, timezone

dbutils.widgets.text("catalog", "hackcamp")
dbutils.widgets.text("volume_path", "/Volumes/hackcamp/raw/github")

catalog = dbutils.widgets.get("catalog")
volume_path = dbutils.widgets.get("volume_path").rstrip("/")
out_dir = f"{volume_path}/repos"

# COMMAND ----------

LANGUAGES = ["Python", "JavaScript", "Go", "Rust", "Java"]

# Curated seeds: (owner/name, language, stars, dependents, health_profile)
# health_profile: healthy | watchlist | at_risk | archived | mature_quiet
SEEDS = [
    ("psf/requests", "Python", 52000, 180000, "healthy"),
    ("pallets/flask", "Python", 68000, 90000, "healthy"),
    ("encode/httpx", "Python", 14000, 25000, "healthy"),
    ("tiangolo/fastapi", "Python", 82000, 70000, "healthy"),
    ("python-poetry/poetry", "Python", 32000, 15000, "watchlist"),
    ("aio-libs/aiohttp", "Python", 15000, 40000, "watchlist"),
    ("kennethreitz/records", "Python", 7200, 800, "at_risk"),
    ("joke2k/faker", "Python", 18000, 12000, "healthy"),
    ("pydata/xarray", "Python", 3700, 5000, "healthy"),
    ("scrapy/scrapy", "Python", 55000, 8000, "watchlist"),
    ("facebook/react", "JavaScript", 230000, 500000, "healthy"),
    ("vuejs/vue", "JavaScript", 208000, 200000, "mature_quiet"),
    ("vercel/next.js", "JavaScript", 130000, 180000, "healthy"),
    ("expressjs/express", "JavaScript", 66000, 300000, "mature_quiet"),
    ("lodash/lodash", "JavaScript", 60000, 400000, "mature_quiet"),
    ("axios/axios", "JavaScript", 106000, 250000, "healthy"),
    ("mrdoob/three.js", "JavaScript", 104000, 30000, "healthy"),
    ("jquery/jquery", "JavaScript", 59000, 200000, "mature_quiet"),
    ("moment/moment", "JavaScript", 48000, 150000, "at_risk"),
    ("request/request", "JavaScript", 25600, 80000, "archived"),
    ("golang/go", "Go", 126000, 0, "healthy"),
    ("gin-gonic/gin", "Go", 80000, 40000, "healthy"),
    ("spf13/cobra", "Go", 39000, 60000, "healthy"),
    ("sirupsen/logrus", "Go", 25000, 50000, "watchlist"),
    ("urfave/cli", "Go", 23000, 20000, "watchlist"),
    ("labstack/echo", "Go", 30000, 12000, "healthy"),
    ("go-chi/chi", "Go", 19000, 15000, "healthy"),
    ("gorilla/mux", "Go", 21000, 25000, "at_risk"),
    ("dgrijalva/jwt-go", "Go", 11000, 30000, "archived"),
    ("hashicorp/terraform", "Go", 44000, 0, "healthy"),
    ("rust-lang/rust", "Rust", 102000, 0, "healthy"),
    ("tokio-rs/tokio", "Rust", 28000, 40000, "healthy"),
    ("serde-rs/serde", "Rust", 9200, 80000, "healthy"),
    ("clap-rs/clap", "Rust", 15000, 35000, "healthy"),
    ("BurntSushi/ripgrep", "Rust", 50000, 0, "mature_quiet"),
    ("sharkdp/fd", "Rust", 37000, 0, "healthy"),
    ("actix/actix-web", "Rust", 22000, 8000, "watchlist"),
    ("hyperium/hyper", "Rust", 15000, 25000, "healthy"),
    ("rust-lang/cargo", "Rust", 13000, 0, "healthy"),
    ("diesel-rs/diesel", "Rust", 13000, 5000, "watchlist"),
    ("spring-projects/spring-boot", "Java", 76000, 100000, "healthy"),
    ("apache/kafka", "Java", 29000, 0, "healthy"),
    ("elastic/elasticsearch", "Java", 72000, 0, "healthy"),
    ("google/guava", "Java", 50000, 200000, "healthy"),
    ("junit-team/junit5", "Java", 6400, 150000, "healthy"),
    ("FasterXML/jackson-databind", "Java", 3600, 180000, "healthy"),
    ("netty/netty", "Java", 34000, 80000, "healthy"),
    ("hibernate/hibernate-orm", "Java", 6000, 40000, "watchlist"),
    ("codehaus/jackson", "Java", 1100, 5000, "archived"),
    ("square/okhttp", "Java", 46000, 90000, "healthy"),
]

NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _profile_metrics(profile: str, stars: int, dependents: int, seed: str):
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    jitter = (h % 20) - 10

    if profile == "healthy":
        days_release = 20 + (h % 40)
        days_push = 3 + (h % 20)
        commits_90d = 80 + (h % 120)
        commits_prev = max(40, commits_90d - 10 + (h % 30))
        reply_rate = 0.85 + (h % 10) / 100
        top_share = 0.25 + (h % 20) / 100
        archived = False
    elif profile == "watchlist":
        days_release = 180 + (h % 120)
        days_push = 45 + (h % 60)
        commits_90d = 15 + (h % 25)
        commits_prev = commits_90d * 2 + (h % 20)
        reply_rate = 0.35 + (h % 25) / 100
        top_share = 0.55 + (h % 25) / 100
        archived = False
    elif profile == "at_risk":
        days_release = 400 + (h % 200)
        days_push = 200 + (h % 150)
        commits_90d = 1 + (h % 5)
        commits_prev = 30 + (h % 40)
        reply_rate = 0.05 + (h % 15) / 100
        top_share = 0.8 + (h % 15) / 100
        archived = False
    elif profile == "archived":
        days_release = 700 + (h % 200)
        days_push = 600 + (h % 200)
        commits_90d = 0
        commits_prev = 5 + (h % 10)
        reply_rate = 0.0
        top_share = 0.95
        archived = True
    else:  # mature_quiet — quiet but fine
        days_release = 100 + (h % 50)
        days_push = 60 + (h % 40)
        commits_90d = 8 + (h % 12)
        commits_prev = 10 + (h % 10)
        reply_rate = 0.7 + (h % 20) / 100
        top_share = 0.3 + (h % 20) / 100
        archived = False

    last_release = NOW - timedelta(days=days_release)
    pushed_at = NOW - timedelta(days=days_push)
    open_issues = 10 + (h % 200) + abs(jitter)
    open_prs = 2 + (h % 40)
    contributors = max(1, 5 + (h % 80) - (30 if profile in ("at_risk", "archived") else 0))

    return {
        "stars": stars,
        "dependents": dependents,
        "is_archived": archived,
        "pushed_at": pushed_at.isoformat().replace("+00:00", "Z"),
        "last_release_at": last_release.isoformat().replace("+00:00", "Z"),
        "commits_90d": int(commits_90d),
        "commits_prev_90d": int(commits_prev),
        "open_issues": int(open_issues),
        "open_prs": int(open_prs),
        "contributors": int(contributors),
        "maintainer_reply_rate": round(_clamp01(reply_rate), 3),
        "top_contributor_share": round(_clamp01(top_share), 3),
    }


records = []
for repo_id, language, stars, dependents, profile in SEEDS:
    owner, name = repo_id.split("/", 1)
    metrics = _profile_metrics(profile, stars, dependents, repo_id)
    payload = {
        "name": name,
        "owner": owner,
        "language": language,
        **metrics,
    }
    records.append(
        {
            "repo_id": repo_id,
            "pulled_at": NOW.isoformat().replace("+00:00", "Z"),
            "payload": payload,
        }
    )

print(f"Prepared {len(records)} repos across {sorted(set(LANGUAGES))}")

# COMMAND ----------

dbutils.fs.mkdirs(out_dir)

# Clear prior seed files so re-runs are idempotent for demos
for f in dbutils.fs.ls(out_dir):
    if f.path.endswith(".json"):
        dbutils.fs.rm(f.path)

written = 0
for rec in records:
    safe_name = rec["repo_id"].replace("/", "__")
    path = f"{out_dir}/{safe_name}.json"
    dbutils.fs.put(path, json.dumps(rec), overwrite=True)
    written += 1

print(f"Wrote {written} JSON files to {out_dir}")
display(spark.createDataFrame([{"repo_id": r["repo_id"], "language": r["payload"]["language"]} for r in records]))
