# Databricks notebook source
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from investigation_coverage import check_coverage

dbutils.widgets.text("coverage_id", "")
coverage_id = dbutils.widgets.get("coverage_id")
assert coverage_id.isdigit()
root = f"/Volumes/hackcamp/raw/github/coverage/{coverage_id}"
baseline = json.loads(dbutils.fs.head(root + "/baseline.json", 1000000))
rows = spark.sql("""SELECT f.*, t.payload FROM hackcamp.agent.findings f
    LEFT JOIN hackcamp.agent.trace_steps t
      ON t.trace_id=f.trace_id AND t.repo_id=f.repo_id AND t.run_id=f.run_id
    WHERE startswith(f.run_id, :prefix)""", args={"prefix": f"coverage-{coverage_id}-"}).collect()
summary = {"coverage_id": coverage_id, "passed": False}
try:
    summary.update(check_coverage([r.asDict() for r in rows], baseline["baseline_repos"], baseline["target"]))
    summary["starting_counts"] = baseline.get("starting_counts")
    for row in rows:
        assert row.payload, f"Missing app trace for {row.repo_id}"
        payload = json.loads(row.payload)
        assert (payload["repo_id"], payload["run_id"], payload["trace_id"]) == (row.repo_id, row.run_id, row.trace_id)
        steps = payload["steps"]
        assert [s["order"] for s in steps] == list(range(1, len(steps) + 1))
        assert sum(s["kind"] == "tool" for s in steps) == row.tool_calls
        assert row.tool_calls <= 8
        assert row.risk_level in {"healthy", "watchlist", "at_risk", "ignored", "inconclusive"}
    summary["application_run_ids"] = sorted({r.run_id for r in rows})
    summary["passed"] = True
finally:
    summary["checked_at"] = datetime.now(timezone.utc).isoformat()
    dbutils.fs.put(root + "/summary.json", json.dumps(summary, indent=2), overwrite=True)
    print(json.dumps(summary, indent=2))
dbutils.jobs.taskValues.set(key="summary_path", value=root + "/summary.json")
