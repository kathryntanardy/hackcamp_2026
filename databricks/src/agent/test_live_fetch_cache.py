# Databricks notebook source
# MAGIC %md
# MAGIC # Ticket #7 — verify live-fetch tools + Delta cache
# MAGIC Calls each tool twice; second call must set `cache_hit=true` and not require a new API round-trip marker.

# COMMAND ----------

# MAGIC %run ./live_fetch_tools

# COMMAND ----------

dbutils.widgets.text("test_repo", "psf/requests")
TEST_REPO = dbutils.widgets.get("test_repo")

# COMMAND ----------

# Fresh pull (bypass cache) then immediate repeat for issues
issues_1 = fetch_recent_issues(TEST_REPO, n=3, force_refresh=True)
assert issues_1.get("cache_hit") is False, issues_1
issues_2 = fetch_recent_issues(TEST_REPO, n=3, force_refresh=False)
assert issues_2.get("cache_hit") is True, issues_2
assert issues_2.get("issues") == issues_1.get("issues"), "cached issues payload mismatch"

readme_1 = fetch_readme_signals(TEST_REPO, force_refresh=True)
assert readme_1.get("cache_hit") is False, readme_1
readme_2 = fetch_readme_signals(TEST_REPO, force_refresh=False)
assert readme_2.get("cache_hit") is True, readme_2
assert readme_2.get("flags") == readme_1.get("flags"), "cached readme flags mismatch"

# Confirm rows landed in tool_cache
counts = spark.sql(
    f"""
    SELECT tool, count(*) AS n
    FROM hackcamp.agent.tool_cache
    WHERE tool IN ('fetch_recent_issues', 'fetch_readme_signals')
    GROUP BY tool
    ORDER BY tool
    """
).collect()
print("tool_cache counts:", [r.asDict() for r in counts])

summary = {
    "repo": TEST_REPO,
    "issues_first_cache_hit": issues_1["cache_hit"],
    "issues_second_cache_hit": issues_2["cache_hit"],
    "readme_first_cache_hit": readme_1["cache_hit"],
    "readme_second_cache_hit": readme_2["cache_hit"],
    "issues_sample": issues_2.get("issues", [])[:2],
    "readme_flags": readme_2.get("flags"),
    "use_instead": readme_2.get("use_instead"),
    "ok": True,
}
print("TICKET7_SUMMARY:" + json.dumps(summary))
dbutils.jobs.taskValues.set(key="ticket7_ok", value="true")
print("TICKET7_PASS")
