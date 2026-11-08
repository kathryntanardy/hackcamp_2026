# Databricks notebook source
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from investigation_coverage import triage_sql, coverage_plan

dbutils.widgets.text("coverage_id", "")
dbutils.widgets.text("coverage_target", "500")
coverage_id = dbutils.widgets.get("coverage_id")
assert coverage_id.isdigit(), "Pass the parent job run ID"
counts = spark.sql("""WITH f AS (SELECT DISTINCT lower(repo_id) AS repo_id FROM hackcamp.agent.findings)
    SELECT count(*) AS corpus, count_if(f.repo_id IS NOT NULL) AS investigated,
      count_if(f.repo_id IS NULL AND g.status <> 'ignored') AS eligible_remaining,
      count_if(f.repo_id IS NULL AND g.status = 'ignored') AS excluded_ignored
    FROM hackcamp.gold.repo_health g LEFT JOIN f ON lower(g.repo_id)=f.repo_id""").first().asDict()
target, budgets = coverage_plan(counts["eligible_remaining"], dbutils.widgets.get("coverage_target"))
if target:
    rows = spark.sql(triage_sql(target, True)).collect()
    assert len(rows) == target, "Eligible count changed during preflight"
baseline = [r.repo_id for r in spark.sql("SELECT DISTINCT repo_id FROM hackcamp.agent.findings").collect()]
summary = {"coverage_id": coverage_id, "target": target, "baseline_repos": baseline,
           "started_at": datetime.now(timezone.utc).isoformat(), "planned_batches": sum(n > 0 for n in budgets),
           "batch_size": 50, "batch_budgets": budgets, "starting_counts": counts}
root = f"/Volumes/hackcamp/raw/github/coverage/{coverage_id}"
dbutils.fs.mkdirs(root)
dbutils.fs.put(root + "/baseline.json", json.dumps(summary, indent=2), overwrite=False)
for i, budget in enumerate(budgets, 1):
    dbutils.jobs.taskValues.set(key=f"batch_{i:02d}_budget", value=budget)
print(json.dumps({k:v for k,v in summary.items() if k != "baseline_repos"}, indent=2))
