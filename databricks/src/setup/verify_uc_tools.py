# Databricks notebook source
# MAGIC %md
# MAGIC # Ticket #6: execute the tool contracts, then check the live catalog
# MAGIC Fixture mode uses only session-local views and temporary SQL functions.
# MAGIC It does not replace data, seed the corpus, call GitHub or invoke a model.

# COMMAND ----------

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED_TOOLS = (
    "get_repo_metrics", "get_commit_trend", "get_release_history",
    "get_issue_backlog", "get_previous_finding",
)
ALL_TOOLS = REQUIRED_TOOLS + ("get_contributor_concentration",)


def sql_statements(text):
    """Split at real delimiters, preserving quoted strings and SQL comments."""
    start = 0
    for token in re.finditer(r"'(?:''|[^'])*'|--[^\n]*|;", text):
        if token.group() == ";":
            statement = text[start:token.start()].strip()
            if statement:
                yield statement
            start = token.end()
    if text[start:].strip():
        yield text[start:].strip()


def call_tool(spark, prefix, name, repo, weeks=12):
    assert name in ALL_TOOLS
    args = {"repo": repo}
    params = ":repo"
    if name == "get_commit_trend":
        args["weeks"] = weeks
        params += ", :weeks"
    row = spark.sql(f"SELECT {prefix}{name}({params}) AS result", args=args).first()
    assert row and row.result is not None, f"{name} returned SQL NULL"
    result = json.loads(row.result)
    assert isinstance(result, dict), f"{name} did not return a JSON object"
    return result


def fixture_checks(spark, definitions):
    as_of = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
    rows = []
    for repo, recent, previous, release, issues in (
        ("fixture/healthy", 100, 50, as_of - timedelta(days=30), 9),
        ("fixture/no_history", None, None, None, None),
        ("fixture/zero_previous", 5, 0, as_of - timedelta(days=60), 0),
    ):
        # Non-null legacy estimates deliberately prove the tools ignore them.
        rows.append((repo, repo.split("/")[1], "fixture", "Python", 1000,
                     False, as_of, release, recent, previous, issues, 4,
                     500, 9000, 0.95, 0.99, as_of))
    spark.createDataFrame(rows, """
        repo_id STRING, name STRING, owner STRING, language STRING, stars BIGINT,
        is_archived BOOLEAN, pushed_at TIMESTAMP, last_release_at TIMESTAMP,
        commits_90d INT, commits_prev_90d INT, open_issues INT, open_prs INT,
        contributors INT, dependents BIGINT, maintainer_reply_rate DOUBLE,
        top_contributor_share DOUBLE, pulled_at TIMESTAMP
    """).createOrReplaceTempView("ticket6_silver")
    spark.createDataFrame([
        ("fixture/healthy", "run-1", 90.0, "healthy", 3.0, as_of),
        ("fixture/no_history", "run-1", None, "watchlist", 3.0, as_of),
        ("fixture/zero_previous", "run-1", 80.0, "healthy", 3.0, as_of),
    ], "repo_id STRING, run_id STRING, health_score DOUBLE, status STRING, importance DOUBLE, scored_at TIMESTAMP"
    ).createOrReplaceTempView("ticket6_gold")
    spark.createDataFrame([
        ("fixture/healthy", "older", "watchlist", 0.8, "older verdict", "earlier evidence",
         "first_seen", [], 2, "trace-1", as_of - timedelta(days=2)),
        ("fixture/healthy", "newer", "healthy", 0.9, "latest verdict", "recent evidence",
         "recovered", [], 3, "trace-2", as_of - timedelta(days=1)),
    ], """repo_id STRING, run_id STRING, risk_level STRING, confidence DOUBLE,
          headline STRING, explanation STRING, changed_since_last STRING,
          alternatives ARRAY<STRING>, tool_calls INT, trace_id STRING, investigated_at TIMESTAMP"""
    ).createOrReplaceTempView("ticket6_findings")

    statements = list(sql_statements(definitions))
    assert len(statements) == len(ALL_TOOLS), "Expected exactly six SQL function definitions"
    for statement in statements:
        temporary = statement.replace(
            "CREATE OR REPLACE FUNCTION hackcamp.tools.",
            "CREATE OR REPLACE TEMPORARY FUNCTION ticket6_",
        ).replace("hackcamp.silver.repos", "ticket6_silver").replace(
            "hackcamp.gold.repo_health", "ticket6_gold"
        ).replace("hackcamp.agent.findings", "ticket6_findings")
        spark.sql(temporary)

    passed = []
    call = lambda name, repo="fixture/healthy", **kwargs: call_tool(spark, "ticket6_", name, repo, **kwargs)
    for name in REQUIRED_TOOLS:
        result = call(name, "missing/repo")
        assert result["found"] is False and result["repo_id"] == "missing/repo", name
        passed.append(f"{name}: missing repo is explicit JSON")
        assert call(name, "x' OR TRUE --")["found"] is False, name
    passed.append("repository parameters are bound, not interpolated")

    metrics = call("get_repo_metrics", " FIXTURE/HEALTHY ")
    assert metrics["found"] and metrics["repo_id"] == "fixture/healthy"
    assert metrics["health_score"] == 90.0 and metrics["stars"] == 1000
    for field in ("contributors", "dependents", "maintainer_reply_rate", "top_contributor_share"):
        assert field in metrics and metrics[field] is None, field
    assert call("get_repo_metrics", "fixture/no_history")["health_score"] is None
    passed.append("baseline metrics preserve unknowns and ignore legacy estimates")

    trend = call("get_commit_trend", weeks=52)
    assert trend["commits_90d"] == 100 and trend["commits_prev_90d"] == 50
    assert trend["trend_pct"] == 100.0 and trend["window_days"] == 90
    assert trend["weekly_history_available"] is False and "estimated_weekly" not in trend
    assert call("get_commit_trend", weeks=1)["trend_pct"] == trend["trend_pct"]
    assert call("get_commit_trend", "fixture/zero_previous")["trend_pct"] is None
    assert call("get_commit_trend", "fixture/no_history")["commits_90d"] is None
    assert call("get_commit_trend", "fixture/no_history")["trend_pct"] is None
    passed.append("fixed commit windows: exact change, zero denominator and missing data")

    release = call("get_release_history")
    assert release["days_since_release"] == 30 and release["full_history_available"] is False
    assert len(release["releases"]) == 1 and release["releases"][0]["days_since_previous"] is None
    missing = call("get_release_history", "fixture/no_history")
    assert missing["last_release_at"] is None and missing["days_since_release"] is None
    assert missing["releases"] == []
    passed.append("latest release uses snapshot date; absent releases stay unknown")

    backlog = call("get_issue_backlog")
    assert backlog["open_issues"] == 9 and backlog["open_prs"] == 4
    assert backlog["response_metrics_available"] is False
    for field in ("maintainer_reply_rate", "unanswered_count", "estimated_unanswered", "median_first_response_hours"):
        assert field in backlog and backlog[field] is None, field
    assert call("get_issue_backlog", "fixture/no_history")["open_issues"] is None
    passed.append("backlog counts never fabricate response or unanswered metrics")

    prior = call("get_previous_finding")
    assert prior["found"] and prior["run_id"] == "newer" and prior["trace_id"] == "trace-2"
    assert call("get_previous_finding", "fixture/no_history")["found"] is False
    passed.append("previous finding selects latest verdict and handles first-seen repos")

    disabled = call("get_contributor_concentration")
    assert disabled["available"] is False
    assert all(disabled[field] is None for field in ("contributors", "top_contributor_share", "bus_factor_score"))
    passed.append("contributor tool is explicitly disabled and returns no proxy")
    return passed


def live_checks(spark):
    passed = []
    # SHOW FUNCTIONS accepts a schema in the current catalog on this runtime.
    spark.sql("USE CATALOG hackcamp")
    registered = {row[0].split(".")[-1] for row in spark.sql("SHOW USER FUNCTIONS IN tools").collect()}
    assert set(ALL_TOOLS) <= registered, f"Missing catalog functions: {set(ALL_TOOLS) - registered}"
    for name in ALL_TOOLS:
        description = "\n".join(str(row[0]) for row in spark.sql(f"DESCRIBE FUNCTION EXTENDED hackcamp.tools.{name}").collect())
        assert "Usage:" in description or "Comment:" in description or "Description:" in description, name
    passed.append("all six governed functions registered with descriptions")

    samples = spark.sql("""
        SELECT s.repo_id, s.stars, s.commits_90d, s.commits_prev_90d,
               s.open_issues, s.open_prs, s.last_release_at, s.pulled_at,
               g.health_score, g.status
        FROM hackcamp.silver.repos s
        JOIN hackcamp.gold.repo_health g ON s.repo_id = g.repo_id
        WHERE s.repo_id IN ('psf/requests', 'request/request', 'codehaus/jackson')
    """).collect()
    assert len(samples) >= 2, "Need at least two known real repos in silver and gold"
    count = spark.sql("SELECT count(*) AS n FROM hackcamp.silver.repos").first().n
    assert count >= 50, "Load the ticket #3 snapshot through ticket #4 before checking the tools"
    for row in samples:
        call = lambda name: call_tool(spark, "hackcamp.tools.", name, row.repo_id)
        metrics = call("get_repo_metrics")
        assert metrics["found"] and metrics["stars"] == row.stars
        assert metrics["health_score"] == row.health_score and metrics["status"] == row.status
        assert all(metrics[key] is None for key in ("contributors", "dependents", "maintainer_reply_rate", "top_contributor_share"))
        trend = call("get_commit_trend")
        assert trend["commits_90d"] == row.commits_90d and trend["commits_prev_90d"] == row.commits_prev_90d
        assert trend["weekly_history_available"] is False
        backlog = call("get_issue_backlog")
        assert backlog["open_issues"] == row.open_issues and backlog["open_prs"] == row.open_prs
        assert backlog["median_first_response_hours"] is None
        release = call("get_release_history")
        assert release["full_history_available"] is False
        assert (release["last_release_at"] is None) == (row.last_release_at is None)
        call("get_previous_finding")
        passed.append(f"live metrics, commits, release, backlog and previous finding: {row.repo_id}")
    for name in REQUIRED_TOOLS:
        assert call_tool(spark, "hackcamp.tools.", name, "ticket6-missing/not-a-repo")["found"] is False
    passed.append("live catalog functions return explicit not-found JSON")
    return passed


def run_verification(spark, dbutils):
    for name, default in (("mode", "fixtures"), ("sql_file", ""), ("volume_path", "/Volumes/hackcamp/raw/github")):
        dbutils.widgets.text(name, default)
    mode = dbutils.widgets.get("mode")
    assert mode in ("fixtures", "live"), "mode must be fixtures or live"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    summary = {"mode": mode, "run_id": run_id, "passed": False}
    root = dbutils.widgets.get("volume_path").rstrip("/") + "/ticket6_verification/" + run_id
    dbutils.fs.mkdirs(root)
    try:
        if mode == "fixtures":
            checks = fixture_checks(spark, Path(dbutils.widgets.get("sql_file")).read_text())
        else:
            checks = live_checks(spark)
        summary.update(passed=True, checks=checks, check_count=len(checks))
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        dbutils.fs.put(root + "/summary.json", json.dumps(summary, indent=2), overwrite=True)
        print("TICKET6_SUMMARY: " + json.dumps(summary, indent=2))
    dbutils.jobs.taskValues.set(key="verification_summary", value=root + "/summary.json")


# COMMAND ----------

if "dbutils" in globals() and "spark" in globals():
    run_verification(spark, dbutils)
