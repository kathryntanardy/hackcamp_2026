# Databricks notebook source
# MAGIC %md
# MAGIC # Recover timed-out grounding checks without repeating investigations

# COMMAND ----------

import json
import os
import sys
import mlflow
from mlflow.genai.scorers import Guidelines

sys.path.insert(0, os.getcwd())
from grounding_eval import complete_grounding

dbutils.widgets.text("summary_path", "")
summary_path = dbutils.widgets.get("summary_path")
summary = json.loads(dbutils.fs.head(summary_path, 100000))
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(experiment_id=summary["experiment_id"])
run = mlflow.get_run(summary["mlflow_run_id"])
table = mlflow.artifacts.load_dict(f"runs:/{summary['mlflow_run_id']}/eval_results.json")
repos = [row[table["columns"].index("repo_id")] for row in table["data"]]
scorer = Guidelines(name="grounded", model=f"databricks:/{run.data.params['model']}", timeout=180,
                    guidelines="Every factual claim in the headline, explanation and evidence must be "
                               "supported by the tool_results in the inputs. Claims not present in tool_results fail.")
with mlflow.start_run(run_id=summary["mlflow_run_id"]):
    audit = complete_grounding(mlflow, summary["mlflow_run_id"], summary["experiment_id"], repos, scorer)
    mlflow.log_dict(audit, "grounding_assessments.json")
    root = summary_path.rsplit("/", 1)[0]
    dbutils.fs.put(root + "/grounding_assessments.json", json.dumps(audit, default=str, indent=2), overwrite=True)
    mlflow.log_metrics({"judge_initial_grounded_mean": audit["initial"]["mean"],
                        "judge_valid_cases": audit["final"]["valid"], "judge_failed_cases": audit["final"]["failed"]})
    summary["judge_coverage"] = audit["final"]
    summary["judge_initial_coverage"] = audit["initial"]
    summary["judge_status"] = "completed" if audit["final"]["complete"] else "failed"
    summary["judge_metrics"]["grounded/mean"] = audit["final"]["mean"]
    mlflow.log_metric("judge_grounded_mean", audit["final"]["mean"])
    mlflow.log_metric("grounded/mean", audit["final"]["mean"])
    mlflow.set_tag("judge_status", summary["judge_status"])
    mlflow.log_dict(summary, "evaluation_summary.json")
    dbutils.fs.put(summary_path, json.dumps(summary, indent=2), overwrite=True)
    print(json.dumps({k:v for k,v in audit.items() if k != "assessments"}, indent=2))
    assert audit["final"]["complete"], "Grounding coverage remains incomplete after bounded retries"
