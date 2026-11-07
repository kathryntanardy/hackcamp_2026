"""Gold: baseline health score, status, importance, and map coordinates."""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


def _linear_score(value, good, bad):
    """Map value onto [0,1] where `good` → 1 and `bad` → 0 (linear between)."""
    return F.greatest(
        F.lit(0.0),
        F.least(
            F.lit(1.0),
            (F.lit(bad) - value) / F.lit(float(bad - good)),
        ),
    )


def _linear_score_high_good(value, good, bad):
    """Map value onto [0,1] where higher is better (`good` → 1, `bad` → 0)."""
    return F.greatest(
        F.lit(0.0),
        F.least(
            F.lit(1.0),
            (value - F.lit(bad)) / F.lit(float(good - bad)),
        ),
    )


@dp.materialized_view(
    name="hackcamp.gold.repo_health",
    comment="Baseline health scores and galaxy-map coordinates per repo",
    table_properties={"quality": "gold"},
)
def repo_health():
    repos = spark.read.table("hackcamp.silver.repos")

    scored_at = F.current_timestamp()
    as_of = F.to_date(scored_at)

    days_since_release = F.coalesce(
        F.datediff(as_of, F.to_date("last_release_at")), F.lit(999)
    )
    days_since_push = F.coalesce(
        F.datediff(as_of, F.to_date("pushed_at")), F.lit(999)
    )
    commit_ratio = F.when(
        F.col("commits_prev_90d") > 0,
        F.col("commits_90d").cast("double") / F.col("commits_prev_90d"),
    ).otherwise(F.when(F.col("commits_90d") > 0, F.lit(1.0)).otherwise(F.lit(0.0)))

    s_release = _linear_score(days_since_release.cast("double"), good=90, bad=540)
    s_commits = _linear_score_high_good(commit_ratio, good=1.0, bad=0.2)
    s_issues = _linear_score_high_good(
        F.col("maintainer_reply_rate"), good=0.8, bad=0.2
    )
    s_bus = _linear_score_high_good(
        F.lit(1.0) - F.col("top_contributor_share"), good=0.6, bad=0.1
    )
    s_activity = _linear_score(days_since_push.cast("double"), good=30, bad=365)

    health_score = (
        30 * s_release
        + 25 * s_commits
        + 20 * s_issues
        + 15 * s_bus
        + 10 * s_activity
    )

    status = (
        F.when(F.col("is_archived"), F.lit("at_risk"))
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
