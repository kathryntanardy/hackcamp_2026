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
sys.path.insert(0, str(SOURCE.parent))  # 03_gold imports deprecated_repos from its own folder


@pytest.fixture(scope="module")
def spark():
    s = SparkSession.builder.master("local[1]").appName("gold-test").getOrCreate()
    yield s
    s.stop()


def load_gold(spark, silver_df):
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
    gold.spark = types.SimpleNamespace(read=types.SimpleNamespace(table=lambda name: silver_df))
    return gold


def ago(days):
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def repo(repo_id, release_days, push_days, c90, cprev, archived=False):
    owner, name = repo_id.split("/")
    return {
        "repo_id": repo_id, "name": name, "owner": owner, "language": "Java",
        "stars": 1000, "dependents": 0, "is_archived": archived,
        "last_release_at": ago(release_days) if release_days is not None else None,
        "pushed_at": ago(push_days) if push_days is not None else None,
        "commits_90d": c90, "commits_prev_90d": cprev,
        # never collected by the scraper; must not drag the score down
        "maintainer_reply_rate": None, "top_contributor_share": None,
    }


SCHEMA = (
    "repo_id string, name string, owner string, language string, stars long, dependents long, "
    "is_archived boolean, last_release_at timestamp, pushed_at timestamp, commits_90d long, "
    "commits_prev_90d long, maintainer_reply_rate double, top_contributor_share double"
)


@pytest.fixture(scope="module")
def scored(spark):
    rows = [
        repo("a/active", 1, 0, 200, 70),            # everything great -> 100
        repo("a/no-releases", None, 0, 600, 530),   # tags only (kafka-like) -> renormalize
        repo("a/stale", 600, 400, 0, 50),           # all bad -> 0
        repo("a/archived", 1, 0, 200, 70, archived=True),
        repo("a/empty", None, None, 0, 0),          # no signals at all
        repo("a/new", 10, 5, 30, 0),                # no previous commits -> trend unavailable
        # old silver defaults (reply 0.0, share 1.0) are deferred terms and must not count
        {**repo("a/old-defaults", 1, 0, 200, 70), "maintainer_reply_rate": 0.0,
         "top_contributor_share": 1.0},
    ]
    df = spark.createDataFrame(rows, SCHEMA)
    out = load_gold(spark, df).repo_health().collect()
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
