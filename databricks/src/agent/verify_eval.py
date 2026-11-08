# Databricks notebook source
# MAGIC %md
# MAGIC # Verify ticket #14 evaluation artifacts and the persisted score

# COMMAND ----------

import json
import os
import sys
import mlflow

sys.path.insert(0, os.getcwd())
from eval_metrics import score, baseline_prediction

dbutils.widgets.text("mlflow_run_id", "")
dbutils.widgets.text("summary_path", "")
mlflow.set_tracking_uri("databricks")
mlflow_run_id = dbutils.widgets.get("mlflow_run_id")
summary_path = dbutils.widgets.get("summary_path")
assert mlflow_run_id and summary_path, "Pass the completed evaluation's run ID and summary path"
summary = json.loads(dbutils.fs.head(summary_path, 100000))
assert summary["mlflow_run_id"] == mlflow_run_id
assert summary["judge_status"] == "completed"
audit_path = summary_path.rsplit("/", 1)[0] + "/grounding_assessments.json"
audit = json.loads(dbutils.fs.head(audit_path, 10000000))
assert audit["final"]["complete"] and audit["final"]["valid"] == summary["n_cases"]
assert audit["final"]["mean"] == summary["judge_metrics"]["grounded/mean"]
artifacts = {name: mlflow.artifacts.load_dict(f"runs:/{mlflow_run_id}/{name}.json")
             for name in ("eval_results", "eval_labels_snapshot", "weight_sensitivity")}
table = artifacts["eval_results"]
results = [dict(zip(table["columns"], row)) for row in table["data"]]
labels = artifacts["eval_labels_snapshot"]
assert len(results) == len(labels) == summary["n_cases"]
assert len({r["repo_id"].lower() for r in results}) == len(results)
assert score(results) == summary["agent"]
assert score({"label": r["label"], "pred": r["formula_pred"]} for r in results) == summary["formula"]
assert all(baseline_prediction(r) == r["formula_status"] for r in labels), "Weight comparison differs from deployed baseline"
assert all(r["trace_id"] for r in results)
if not summary["is_smoke"]:
    assert 30 <= len(results) <= 50
    persisted = spark.sql("SELECT eval_score FROM hackcamp.agent.runs WHERE run_id=:run_id",
                          args={"run_id": summary["score_target_run_id"]}).collect()
    assert persisted and all(r.eval_score == summary["agent"]["accuracy"] for r in persisted)
assert spark.sql("SELECT count(*) AS n FROM hackcamp.agent.findings WHERE run_id=:run_id",
                 args={"run_id": summary["run_id"]}).first().n == 0
root = summary_path.rsplit("/", 1)[0]
for name, data in artifacts.items():
    dbutils.fs.put(f"{root}/{name}.json", json.dumps(data, indent=2), overwrite=True)
verification = {"passed": True, "run_id": summary["run_id"], "mlflow_run_id": mlflow_run_id,
                "cases": len(results), "unique_repos": len(results), "score_matches": True,
                "baseline_reproduced": True, "production_findings_written": 0}
agent, formula = summary["agent"], summary["formula"]
grounding = summary["judge_metrics"].get("grounded/mean")
verification["target_checks"] = {
    "flag_recall_80pct": agent["at_risk_recall"] is not None and agent["at_risk_recall"] >= .8,
    "flag_precision_75pct": agent["at_risk_precision"] is not None and agent["at_risk_precision"] >= .75,
    "agent_beats_formula": agent["accuracy"] > formula["accuracy"],
    "groundedness_90pct": grounding is not None and grounding >= .9,
    "median_3_to_6_tools": 3 <= agent.get("median_tool_calls", 0) <= 6,
    "first_20_under_10min": summary["first_20_repos_duration_sec"] < 600 if len(results) >= 20 else None,
}
client = mlflow.MlflowClient()
for key, value in verification["target_checks"].items():
    if value is not None:
        client.log_metric(mlflow_run_id, f"target_{key}", float(value))
dbutils.fs.put(f"{root}/verification.json", json.dumps(verification, indent=2), overwrite=True)
dbutils.jobs.taskValues.set(key="verification_path", value=f"{root}/verification.json")
print(json.dumps(verification, indent=2))
