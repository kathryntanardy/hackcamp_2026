"""Gold: baseline health score, status, importance, F15 category/buckets, map coords."""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from deprecated_repos import KNOWN_DEPRECATED_REPOS
from vuln_buckets import BUCKET_NONE, BUCKET_OTHER, SEVERITY_RANK


def _clamp01_or_null(raw, value):
    """Clamp to [0,1], but keep NULL when the input is missing.

    Spark's greatest/least skip NULLs, so greatest(0, NULL) is 0 — that silently
    turned every missing signal into a worst-case score.
    """
    return F.when(value.isNull(), F.lit(None).cast("double")).otherwise(
        F.greatest(F.lit(0.0), F.least(F.lit(1.0), raw))
    )


def _linear_score(value, good, bad):
    """Map value onto [0,1] where `good` → 1 and `bad` → 0 (linear between)."""
    return _clamp01_or_null((F.lit(bad) - value) / F.lit(float(bad - good)), value)


def _linear_score_high_good(value, good, bad):
    """Map value onto [0,1] where higher is better (`good` → 1, `bad` → 0)."""
    return _clamp01_or_null((value - F.lit(bad)) / F.lit(float(good - bad)), value)


# PRD MVP formula: only the three signals we actually collect. Issue-reply and
# bus-factor terms are deferred until measured data exists.
WEIGHTS = {"release": 30, "commits": 25, "activity": 10}


def _renormalized_score(subscores):
    """100 * sum(w*s) / sum(w) over the sub-scores that are present; NULL if none."""
    num = sum(
        F.coalesce(F.lit(w) * s, F.lit(0.0)) for w, s in subscores
    )
    den = sum(F.when(s.isNotNull(), F.lit(float(w))).otherwise(F.lit(0.0)) for w, s in subscores)
    return F.when(den > 0, F.lit(100.0) * num / den)


def _severity_rank_col(col):
    expr = F.lit(0)
    for label, rank in SEVERITY_RANK.items():
        expr = F.when(F.lower(col) == label, F.lit(rank)).otherwise(expr)
    return expr


def _heuristic_category_col():
    """Keyword fallback when ai_query has not classified the repo yet."""
    blob = F.lower(
        F.concat_ws(
            " ",
            F.coalesce(F.col("description"), F.lit("")),
            F.concat_ws(" ", F.coalesce(F.col("topics"), F.array().cast("array<string>"))),
        )
    )
    return (
        F.when(
            blob.rlike(
                r"(react|vue|angular|frontend|front-end|\bcss\b|\bui\b|browser|\bdom\b|webpack|svelte)"
            ),
            F.lit("Front-end"),
        )
        .when(
            blob.rlike(
                r"(machine[- ]learning|deep[- ]learning|neural|pytorch|tensorflow|\bllm\b|\bnlp\b)"
            ),
            F.lit("Machine learning"),
        )
        .when(
            blob.rlike(
                r"(database|\bsql\b|postgres|mysql|mongodb|redis|\borm\b|sqlite|cassandra)"
            ),
            F.lit("Database"),
        )
        .when(
            blob.rlike(r"(embedded|firmware|\biot\b|arduino|raspberry|fpga|hardware|\bmcu\b)"),
            F.lit("Hardware/embedded"),
        )
        .when(
            blob.rlike(
                r"(kubernetes|docker|devops|terraform|ci/cd|infra|ansible|helm|observability|prometheus)"
            ),
            F.lit("DevOps & infra"),
        )
        .when(
            blob.rlike(r"(backend|back-end|\bserver\b|\bapi\b|\bhttp\b|grpc|microservice|framework)"),
            F.lit("Back-end"),
        )
        .otherwise(F.lit("other"))
    )


def _normalize_ai_category(col):
    return (
        F.when(F.lower(F.trim(col)).isin("front-end", "frontend", "front end"), F.lit("Front-end"))
        .when(F.lower(F.trim(col)).isin("back-end", "backend", "back end"), F.lit("Back-end"))
        .when(
            F.lower(F.trim(col)).isin("machine learning", "machine-learning", "ml"),
            F.lit("Machine learning"),
        )
        .when(F.lower(F.trim(col)) == "database", F.lit("Database"))
        .when(
            F.lower(F.trim(col)).isin("hardware/embedded", "hardware", "embedded"),
            F.lit("Hardware/embedded"),
        )
        .when(
            F.lower(F.trim(col)).isin("devops & infra", "devops"),
            F.lit("DevOps & infra"),
        )
        .when(F.lower(F.trim(col)) == "other", F.lit("other"))
        .otherwise(F.lit(None).cast("string"))
    )


def _read_ai_categories():
    """Table filled by classify_repo_categories (ai_query). Always LEFT JOINed."""
    return spark.read.table("hackcamp.silver.repo_categories").select(
        F.col("repo_id"),
        F.col("category").alias("ai_category"),
    )


def _advisory_aggs():
    adv = spark.read.table("hackcamp.silver.repo_advisories")
    return adv.groupBy("repo_id").agg(
        F.count(F.lit(1)).alias("advisory_count"),
        F.max("cvss_score").alias("max_cvss"),
        F.max_by("severity", _severity_rank_col(F.col("severity"))).alias("max_severity"),
        F.collect_set("vuln_bucket").alias("_adv_buckets"),
    )


@dp.materialized_view(
    name="hackcamp.gold.repo_health",
    comment=(
        "Baseline maintainer-risk scores, F15 category/vuln_buckets, and galaxy-map "
        "coordinates (language x/y and category cat_x/cat_y). "
        "status: healthy | watchlist | at_risk | ignored "
        "(ignored = deprecated/archived; excluded from living triage). "
        "importance is ecosystem weight (log stars/dependents), not the same as health_score."
    ),
    table_properties={"quality": "gold"},
)
def repo_health():
    repos = spark.read.table("hackcamp.silver.repos")
    adv = _advisory_aggs()
    ai_cats = _read_ai_categories()

    scored_at = F.current_timestamp()
    as_of = F.to_date(scored_at)

    # Missing dates stay NULL (no 999-day sentinel), so the signal drops out.
    days_since_release = F.datediff(as_of, F.to_date("last_release_at"))
    days_since_push = F.datediff(as_of, F.to_date("pushed_at"))
    # Zero previous commits makes the trend unavailable, not a decline.
    commit_ratio = F.when(
        F.col("commits_prev_90d") > 0,
        F.col("commits_90d").cast("double") / F.col("commits_prev_90d"),
    )

    s_release = _linear_score(days_since_release.cast("double"), good=90, bad=540)
    s_commits = _linear_score_high_good(commit_ratio, good=1.0, bad=0.2)
    s_activity = _linear_score(days_since_push.cast("double"), good=30, bad=365)

    health_score = _renormalized_score(
        [
            (WEIGHTS["release"], s_release),
            (WEIGHTS["commits"], s_commits),
            (WEIGHTS["activity"], s_activity),
        ]
    )

    # Deprecated / archived lines: park as ignored (no living triage / PR-review budget).
    # Bare formula risk stays at_risk/watchlist/healthy for everything else.
    is_ignored = F.col("is_archived") | F.col("repo_id").isin(
        list(KNOWN_DEPRECATED_REPOS)
    )
    status = (
        F.when(is_ignored, F.lit("ignored"))
        .when(health_score.isNull(), F.lit("watchlist"))  # insufficient data
        .when(health_score >= 70, F.lit("healthy"))
        .when(health_score >= 40, F.lit("watchlist"))
        .otherwise(F.lit("at_risk"))
    )

    importance = F.when(
        F.col("dependents") > 0,
        F.log10(F.col("dependents") + F.lit(1)),
    ).otherwise(F.log10(F.col("stars") + F.lit(1)))

    # Language cluster centres + seeded offset so positions stay stable across runs
    cx = (
        F.when(F.col("language") == "Python", F.lit(0.0))
        .when(F.col("language") == "JavaScript", F.lit(100.0))
        .when(F.col("language") == "Go", F.lit(50.0))
        .when(F.col("language") == "Rust", F.lit(-50.0))
        .when(F.col("language") == "Java", F.lit(0.0))
        .otherwise(F.lit(0.0))
    )
    cy = (
        F.when(F.col("language") == "Python", F.lit(0.0))
        .when(F.col("language") == "JavaScript", F.lit(0.0))
        .when(F.col("language") == "Go", F.lit(86.0))
        .when(F.col("language") == "Rust", F.lit(86.0))
        .when(F.col("language") == "Java", F.lit(-100.0))
        .otherwise(F.lit(0.0))
    )
    seed = F.xxhash64("repo_id")
    x = cx + ((seed % F.lit(40)) - F.lit(20)).cast("double")
    y = cy + (((seed / F.lit(40)).cast("bigint") % F.lit(40)) - F.lit(20)).cast(
        "double"
    )

    commit_trend_pct = F.when(
        F.col("commits_prev_90d") > 0,
        (F.col("commits_90d") - F.col("commits_prev_90d")).cast("double")
        / F.col("commits_prev_90d")
        * F.lit(100.0),
    ).otherwise(F.lit(None).cast("double"))

    joined = (
        repos.join(adv, on="repo_id", how="left")
        .join(ai_cats, on="repo_id", how="left")
        .withColumn("advisory_count", F.coalesce(F.col("advisory_count"), F.lit(0)))
        .withColumn(
            "_adv_buckets",
            F.coalesce(F.col("_adv_buckets"), F.array().cast("array<string>")),
        )
    )

    category = F.coalesce(
        _normalize_ai_category(F.col("ai_category")),
        _heuristic_category_col(),
        F.lit("other"),
    )

    # Distinguish ok+empty advisories from Other / failed fetch.
    vuln_buckets = (
        F.when(
            (F.col("advisory_fetch_status") == "ok") & (F.col("advisory_count") == 0),
            F.array(F.lit(BUCKET_NONE)),
        )
        .when(F.col("advisory_count") == 0, F.array().cast("array<string>"))
        .when(
            F.size(F.col("_adv_buckets")) == 0,
            F.array(F.lit(BUCKET_OTHER)),
        )
        .otherwise(F.col("_adv_buckets"))
    )

    # Category cluster centres (hex-ish layout) + same seeded offset as language.
    cat_cx = (
        F.when(category == "Front-end", F.lit(100.0))
        .when(category == "Back-end", F.lit(-100.0))
        .when(category == "Machine learning", F.lit(50.0))
        .when(category == "Database", F.lit(-50.0))
        .when(category == "Hardware/embedded", F.lit(0.0))
        .when(category == "DevOps & infra", F.lit(0.0))
        .otherwise(F.lit(0.0))  # other
    )
    cat_cy = (
        F.when(category == "Front-end", F.lit(0.0))
        .when(category == "Back-end", F.lit(0.0))
        .when(category == "Machine learning", F.lit(86.0))
        .when(category == "Database", F.lit(86.0))
        .when(category == "Hardware/embedded", F.lit(-100.0))
        .when(category == "DevOps & infra", F.lit(100.0))
        .otherwise(F.lit(-50.0))
    )
    cat_x = cat_cx + ((seed % F.lit(40)) - F.lit(20)).cast("double")
    cat_y = cat_cy + (((seed / F.lit(40)).cast("bigint") % F.lit(40)) - F.lit(20)).cast(
        "double"
    )

    return joined.select(
        "repo_id",
        F.date_format(scored_at, "yyyyMMddHHmmss").alias("run_id"),
        F.round(health_score, 2).alias("health_score"),
        status.alias("status"),
        F.round(importance, 4).alias("importance"),
        days_since_release.alias("days_since_release"),
        F.round(commit_trend_pct, 2).alias("commit_trend_pct"),
        category.alias("category"),
        vuln_buckets.alias("vuln_buckets"),
        F.col("advisory_count").cast("long").alias("advisory_count"),
        F.col("max_severity"),
        F.round(F.col("max_cvss"), 2).alias("max_cvss"),
        F.round(x, 2).alias("x"),
        F.round(y, 2).alias("y"),
        F.round(cat_x, 2).alias("cat_x"),
        F.round(cat_y, 2).alias("cat_y"),
        scored_at.alias("scored_at"),
        "language",
        "stars",
        "dependents",
        "is_archived",
        "name",
        "owner",
    )
