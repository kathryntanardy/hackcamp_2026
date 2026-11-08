"""Gold health score vs the PRD formula. Needs pyspark + Java; skipped otherwise."""

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pyspark = pytest.importorskip("pyspark")
from pyspark.sql import SparkSession  # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "src/pipelines/repo_health/transformations/03_gold.py"
sys.path.insert(0, str(SOURCE.parent))  # 03_gold imports siblings from its own folder


@pytest.fixture(scope="module")
def spark():
    s = SparkSession.builder.master("local[1]").appName("gold-test").getOrCreate()
    yield s
    s.stop()


def load_gold(spark, silver_df, advisories_df=None, categories_df=None):
    # The real pipelines decorator only works inside a pipeline graph; make it a no-op.
    fake_dp = types.ModuleType("pyspark.pipelines")
    fake_dp.materialized_view = lambda **kw: (lambda f: f)
    saved = sys.modules.get("pyspark.pipelines")
    sys.modules["pyspark.pipelines"] = fake_dp
    saved_attr = getattr(pyspark, "pipelines", None)
    pyspark.pipelines = fake_dp
    try:
        spec = importlib.util.spec_from_file_location("gold", SOURCE)
        gold = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gold)
    finally:
        if saved is not None:
            sys.modules["pyspark.pipelines"] = saved
        if saved_attr is not None:
            pyspark.pipelines = saved_attr

    if advisories_df is None:
        advisories_df = spark.createDataFrame(
            [],
            "repo_id string, ghsa_id string, cve_id string, severity string, "
            "cvss_score double, cwes array<string>, vuln_bucket string, summary string, "
            "published_at timestamp, pulled_at timestamp, advisory_fetch_status string",
        )
    if categories_df is None:
        categories_df = spark.createDataFrame(
            [], "repo_id string, category string"
        )

    tables = {
        "hackcamp.silver.repos": silver_df,
        "hackcamp.silver.repo_advisories": advisories_df,
        "hackcamp.silver.repo_categories": categories_df,
    }

    gold.spark = types.SimpleNamespace(
        read=types.SimpleNamespace(table=lambda name: tables[name]),
        createDataFrame=spark.createDataFrame,
    )
    return gold


def ago(days):
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def repo(repo_id, release_days, push_days, c90, cprev, archived=False, **extra):
    owner, name = repo_id.split("/")
    row = {
        "repo_id": repo_id, "name": name, "owner": owner, "language": "Java",
        "stars": 1000, "dependents": 0, "is_archived": archived,
        "last_release_at": ago(release_days) if release_days is not None else None,
        "pushed_at": ago(push_days) if push_days is not None else None,
        "commits_90d": c90, "commits_prev_90d": cprev,
        # never collected by the scraper; must not drag the score down
        "maintainer_reply_rate": None, "top_contributor_share": None,
        "description": None, "topics": [], "advisory_fetch_status": "ok",
    }
    row.update(extra)
    return row


SCHEMA = (
    "repo_id string, name string, owner string, language string, stars long, dependents long, "
    "is_archived boolean, last_release_at timestamp, pushed_at timestamp, commits_90d long, "
    "commits_prev_90d long, maintainer_reply_rate double, top_contributor_share double, "
    "description string, topics array<string>, advisory_fetch_status string"
)


@pytest.fixture(scope="module")
def scored(spark):
    rows = [
        repo("a/active", 1, 0, 200, 70, description="A React UI library", topics=["frontend"]),
        repo("a/no-releases", None, 0, 600, 530),   # tags only (kafka-like) -> renormalize
        repo("a/stale", 600, 400, 0, 50),           # all bad -> 0
        repo("a/archived", 1, 0, 200, 70, archived=True),
        repo("a/empty", None, None, 0, 0),          # no signals at all
        repo("a/new", 10, 5, 30, 0),                # no previous commits -> trend unavailable
        # old silver defaults (reply 0.0, share 1.0) are deferred terms and must not count
        {**repo("a/old-defaults", 1, 0, 200, 70), "maintainer_reply_rate": 0.0,
         "top_contributor_share": 1.0},
        repo(
            "lodash/lodash", 1, 0, 200, 70,
            description="A modern JavaScript utility library",
            topics=["javascript", "utilities"],
        ),
        repo(
            "a/clean", 1, 0, 200, 70,
            description="Boring library with no vulns",
            advisory_fetch_status="ok",
        ),
    ]
    df = spark.createDataFrame(rows, SCHEMA)
    advisories = spark.createDataFrame(
        [
            {
                "repo_id": "lodash/lodash",
                "ghsa_id": "GHSA-1",
                "cve_id": "CVE-1",
                "severity": "high",
                "cvss_score": 8.1,
                "cwes": ["CWE-94"],
                "vuln_bucket": "Code execution",
                "summary": "template injection",
                "published_at": None,
                "pulled_at": None,
                "advisory_fetch_status": "ok",
            },
            {
                "repo_id": "lodash/lodash",
                "ghsa_id": "GHSA-2",
                "cve_id": "CVE-2",
                "severity": "medium",
                "cvss_score": 6.5,
                "cwes": ["CWE-1321"],
                "vuln_bucket": "Prototype pollution",
                "summary": "prototype pollution",
                "published_at": None,
                "pulled_at": None,
                "advisory_fetch_status": "ok",
            },
        ]
    )
    categories = spark.createDataFrame(
        [{"repo_id": "lodash/lodash", "category": "Back-end"}]
    )
    out = load_gold(spark, df, advisories, categories).repo_health().collect()
    return {r.repo_id: r for r in out}


def test_fully_healthy_repo_can_reach_healthy(scored):
    # old 5-term formula capped this at 65 because missing terms counted as 0
    assert scored["a/active"].health_score == 100.0
    assert scored["a/active"].status == "healthy"


def test_deferred_issue_and_bus_terms_do_not_count(scored):
    # this is what capped prod at 65 with zero healthy repos
    assert scored["a/old-defaults"].health_score == 100.0


def test_missing_release_is_excluded_not_zeroed(scored):
    r = scored["a/no-releases"]
    assert r.days_since_release is None
    assert r.health_score == 100.0
    assert r.status == "healthy"


def test_all_bad_signals_is_at_risk(scored):
    assert scored["a/stale"].health_score == 0.0
    assert scored["a/stale"].status == "at_risk"


def test_archived_is_parked_as_ignored(scored):
    # PRD: archived/deprecated lines are ignored, not living risk
    assert scored["a/archived"].status == "ignored"


def test_no_signals_gives_null_score_and_watchlist(scored):
    assert scored["a/empty"].health_score is None
    assert scored["a/empty"].status == "watchlist"


def test_zero_previous_commits_drops_trend(scored):
    r = scored["a/new"]
    assert r.commit_trend_pct is None
    # release (30) + activity (10) both perfect, commits term excluded
    assert r.health_score == 100.0


def test_f15_category_prefers_ai_query_then_heuristic(scored):
    assert scored["lodash/lodash"].category == "Back-end"  # from AI table
    assert scored["a/active"].category == "Front-end"  # heuristic from description


def test_f15_vuln_buckets_and_advisory_stats(scored):
    r = scored["lodash/lodash"]
    assert r.advisory_count == 2
    assert r.max_severity == "high"
    assert r.max_cvss == 8.1
    assert set(r.vuln_buckets) == {"Code execution", "Prototype pollution"}
    assert scored["a/clean"].vuln_buckets == ["No GitHub advisories"]
    assert scored["a/clean"].advisory_count == 0


def test_f15_category_coords_present(scored):
    r = scored["lodash/lodash"]
    assert r.cat_x is not None and r.cat_y is not None
