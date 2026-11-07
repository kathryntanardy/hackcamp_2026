# Databricks notebook source
# MAGIC %md
# MAGIC # Agent eval on `agent.eval_labels`
# MAGIC Runs the same agent as `run_investigation` on every labelled repo, scores agent vs the baseline
# MAGIC formula (`gold.repo_health.status`), and logs metrics + a per-repo table to MLflow.
# MAGIC Groundedness of explanations is checked by an MLflow GenAI LLM judge (best effort).
# MAGIC Nothing is written to `agent.findings`, so eval runs don't pollute the map.

# COMMAND ----------

# MAGIC %pip install -q --upgrade "mlflow[databricks]>=3.1.0" "openai>=1.40.0" "pydantic>=2.0" "databricks-sdk>=0.36.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import uuid
from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("model_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("max_tool_calls", "8")
dbutils.widgets.text("repo_timeout_sec", "180")
dbutils.widgets.text("experiment_path", "")
dbutils.widgets.text("limit", "0")  # 0 = all labelled repos; set e.g. 5 for a smoke run
dbutils.widgets.text("run_judge", "true")

MODEL = dbutils.widgets.get("model_endpoint")
MAX_TOOL_CALLS = int(dbutils.widgets.get("max_tool_calls"))
REPO_TIMEOUT_SEC = int(dbutils.widgets.get("repo_timeout_sec"))
EXPERIMENT_PATH = dbutils.widgets.get("experiment_path").strip() or f"/Users/{WorkspaceClient().current_user.me().user_name}/hackcamp-agent"
# investigate_repo tags traces with RUN_ID; prefix keeps eval traces apart from real runs
RUN_ID = "eval-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
LIMIT = int(dbutils.widgets.get("limit"))
RUN_JUDGE = dbutils.widgets.get("run_judge").lower() == "true"

# COMMAND ----------

# MAGIC %run ./agent_core

# COMMAND ----------

import os
import sys

sys.path.insert(0, os.getcwd())  # notebook dir, so the plain .py module imports
from eval_metrics import score

# COMMAND ----------

# MAGIC %md
# MAGIC ## Labelled set joined with the formula's status

# COMMAND ----------

labelled = spark.sql(
    """
    SELECT l.repo_id, l.label, l.label_source, g.status AS formula_status, g.health_score,
           -- round-robin across labels so a small `limit` still covers every label
           row_number() OVER (PARTITION BY l.label ORDER BY l.repo_id) AS rr
    FROM hackcamp.agent.eval_labels l
    LEFT JOIN hackcamp.gold.repo_health g ON g.repo_id = l.repo_id
    ORDER BY rr, l.label
    """
).collect()

missing = [r.repo_id for r in labelled if r.formula_status is None]
cases = [r for r in labelled if r.formula_status is not None]
if LIMIT > 0:
    cases = cases[:LIMIT]
print(f"labelled={len(labelled)} in_gold={len(labelled) - len(missing)} evaluating={len(cases)}")
if missing:
    print("not in gold (skipped):", missing)
assert cases, "No labelled repos found in gold.repo_health"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run the agent on each labelled repo

# COMMAND ----------


def tool_results_from_trace(trace_id):
    """Concatenate tool outputs from a trace so the judge can check grounding."""
    if not trace_id:
        return ""
    try:
        trace = mlflow.get_trace(trace_id)
        spans = trace.search_spans(span_type="TOOL")
        return "\n".join(f"{s.name}: {(s.outputs or {}).get('result', '')}" for s in spans)
    except Exception as e:
        return f"(could not load trace: {e})"


results = []
with mlflow.start_run(run_name=f"eval-{MODEL}") as mlrun:
    mlflow.log_params(
        {"model": MODEL, "max_tool_calls": MAX_TOOL_CALLS, "n_cases": len(cases)}
    )
    for c in cases:
        print(f"=== {c.repo_id} (label={c.label}) ===")
        try:
            verdict, trace_id = investigate_repo(
                c.repo_id, f"eval case; formula status={c.formula_status}"
            )
        except Exception as e:  # one bad repo shouldn't kill the eval
            verdict, trace_id = inconclusive(c.repo_id, 0, f"agent error: {e}"), None
        results.append(
            {
                "repo_id": c.repo_id,
                "label": c.label,
                "pred": verdict.risk_level,
                "formula_pred": c.formula_status,
                "confidence": float(verdict.confidence),
                "tool_calls": int(verdict.tool_calls),
                "headline": verdict.headline,
                "explanation": verdict.explanation,
                "evidence": json.dumps([e.model_dump() for e in verdict.evidence], default=str),
                "trace_id": trace_id,
            }
        )
        print(f"  agent={verdict.risk_level} formula={c.formula_status}")

    agent_m = score(results)
    formula_m = score({"label": r["label"], "pred": r["formula_pred"]} for r in results)

    def _log(prefix, m):
        mlflow.log_metrics({f"{prefix}_{k}": v for k, v in m.items() if v is not None})

    _log("agent", agent_m)
    _log("formula", formula_m)
    if agent_m["accuracy"] is not None and formula_m["accuracy"] is not None:
        mlflow.log_metric("agent_minus_formula_accuracy", agent_m["accuracy"] - formula_m["accuracy"])

    mlflow.log_table(
        {k: [r[k] for r in results] for k in results[0]}, artifact_file="eval_results.json"
    )

    # Groundedness: LLM judge checks each explanation against the tool outputs in its trace.
    if RUN_JUDGE:
        try:
            from mlflow.genai.scorers import Guidelines

            judge_data = [
                {
                    "inputs": {
                        "repo_id": r["repo_id"],
                        "tool_results": tool_results_from_trace(r["trace_id"]),
                    },
                    "outputs": {
                        "headline": r["headline"],
                        "explanation": r["explanation"],
                        "evidence": r["evidence"],
                    },
                }
                for r in results
            ]
            grounded = Guidelines(
                name="grounded",
                guidelines=(
                    "Every factual claim in the headline, explanation and evidence must be "
                    "supported by the tool_results in the inputs. Claims not present in "
                    "tool_results fail."
                ),
            )
            judge = mlflow.genai.evaluate(data=judge_data, scorers=[grounded])
            print("judge metrics:", judge.metrics)
            for k, v in judge.metrics.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(f"judge_{k.replace('/', '_')}", v)
        except Exception as e:
            print(f"Groundedness judge skipped: {type(e).__name__}: {e}")

print(f"MLflow run: {mlrun.info.run_id}")

# COMMAND ----------

summary = spark.createDataFrame(
    [
        (k, agent_m.get(k), formula_m.get(k))
        for k in ["n", "accuracy", "at_risk_precision", "at_risk_recall",
                  "hard_case_false_alarm_rate", "inconclusive_rate", "median_tool_calls"]
    ],
    "metric string, agent double, formula double",
)
display(summary)
display(spark.createDataFrame(results).select("repo_id", "label", "pred", "formula_pred", "confidence", "tool_calls", "headline"))
