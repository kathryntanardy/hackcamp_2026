# Databricks notebook source
# MAGIC %md
# MAGIC # Ticket #11: verify the persisted finding → MLflow → app-steps link

# COMMAND ----------

# MAGIC %run ./trace_steps

# COMMAND ----------

import json
from datetime import datetime, timezone
import mlflow

dbutils.widgets.text("run_id", "")
dbutils.widgets.text("volume_path", "/Volumes/hackcamp/raw/github")
run_id = dbutils.widgets.get("run_id")
assert run_id, "Pass the investigation run_id to verify its trace links"
mlflow.set_tracking_uri("databricks")

findings = spark.sql("""
    SELECT repo_id, run_id, trace_id, tool_calls FROM hackcamp.agent.findings
    WHERE run_id = :run_id ORDER BY repo_id
""", args={"run_id": run_id}).collect()
assert findings, "No persisted findings for the requested run"
summary = {"run_id": run_id, "passed": False, "findings": []}
try:
    for finding in findings:
        assert finding.trace_id, "A finding was persisted without its own trace ID"
        fresh = fetch_trace_steps(finding.trace_id, repo_id=finding.repo_id, run_id=run_id)
        saved = get_finding_trace(spark, finding.repo_id, run_id)
        assert saved["found"] and saved["trace_id"] == finding.trace_id
        assert saved["repo_id"] == finding.repo_id and saved["run_id"] == run_id
        assert saved["steps"] == fresh["steps"], "Stored app steps differ from the retrieved MLflow trace"
        steps = saved["steps"]
        assert [step["order"] for step in steps] == list(range(1, len(steps) + 1))
        assert [step["started_at_ms"] for step in steps] == sorted(step["started_at_ms"] for step in steps)
        tools = [step for step in steps if step["kind"] == "tool"]
        decisions = [step for step in steps if step["kind"] == "decision"]
        assert len(tools) == finding.tool_calls and len(tools) >= 2
        assert decisions and all(step["phase"] for step in decisions)
        assert all(step["tool_name"] and isinstance(step["inputs"], dict) for step in tools)
        assert all(step["outputs"] is not None and step["result_summary"] for step in tools)
        assert all("reasoning" in step and "reasoning_available" in step for step in steps)
        assert "reasoning_content" not in json.dumps(decisions), "Hidden provider reasoning must not be exported"
        summary["findings"].append({
            "repo_id": finding.repo_id, "trace_id": finding.trace_id,
            "tool_steps": len(tools), "decision_steps": len(decisions),
            "experiment_id": saved["experiment_id"], "experiment_url": saved["experiment_url"],
        })
    assert get_finding_trace(spark, "ticket11-missing/not-a-repo", run_id)["found"] is False
    summary["passed"] = True
finally:
    root = dbutils.widgets.get("volume_path").rstrip("/") + "/ticket11_verification/" + run_id
    dbutils.fs.mkdirs(root)
    summary["checked_at"] = datetime.now(timezone.utc).isoformat()
    dbutils.fs.put(root + "/summary.json", json.dumps(summary, indent=2), overwrite=True)
    print("TICKET11_SUMMARY: " + json.dumps(summary, indent=2))
    dbutils.jobs.taskValues.set(key="verification_summary", value=root + "/summary.json")
