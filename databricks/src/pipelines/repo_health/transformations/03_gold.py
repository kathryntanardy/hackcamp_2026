"""Gold: baseline health score, status, importance, and map coordinates."""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


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


@dp.materialized_view(
    name="hackcamp.gold.repo_health",
    comment="Baseline health scores and galaxy-map coordinates per repo",
    table_properties={"quality": "gold"},
)
def repo_health():
    repos = spark.read.table("hackcamp.silver.repos")

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

    status = (
        F.when(F.col("is_archived"), F.lit("at_risk"))
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

    return repos.select(
        "repo_id",
        F.date_format(scored_at, "yyyyMMddHHmmss").alias("run_id"),
        F.round(health_score, 2).alias("health_score"),
        status.alias("status"),
        F.round(importance, 4).alias("importance"),
        days_since_release.alias("days_since_release"),
        F.round(commit_trend_pct, 2).alias("commit_trend_pct"),
        F.round(x, 2).alias("x"),
        F.round(y, 2).alias("y"),
        scored_at.alias("scored_at"),
        "language",
        "stars",
        "dependents",
        "is_archived",
        "name",
        "owner",
    )
