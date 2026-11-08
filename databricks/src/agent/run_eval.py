# Databricks notebook source
# MAGIC %md
# MAGIC # Agent eval on `agent.eval_labels`
# MAGIC Runs the same agent as `run_investigation` on every labelled repo, scores agent vs the baseline
# MAGIC formula (`gold.repo_health.status`), and logs metrics + a per-repo table to MLflow.
# MAGIC Groundedness is checked by an MLflow GenAI LLM judge; judge failures leave the evaluation incomplete.
# MAGIC Nothing is written to `agent.findings`, so eval runs don't pollute the map.

# COMMAND ----------

# MAGIC %pip install -q --upgrade "mlflow[databricks]>=3.1.0" "openai>=1.40.0" "pydantic>=2.0" "databricks-sdk>=0.36.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import uuid
import time
import hashlib
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
from eval_metrics import score, weight_sensitivity
from grounding_eval import complete_grounding

# COMMAND ----------

# MAGIC %md
# MAGIC ## Labelled set joined with the formula's status

# COMMAND ----------

labelled = spark.sql(
    """
    SELECT l.repo_id, l.label, l.label_source, l.notes, g.status AS formula_status, g.health_score,
           g.days_since_release, datediff(to_date(g.scored_at), to_date(s.pushed_at)) AS days_since_push,
           CASE WHEN s.commits_prev_90d > 0 THEN cast(s.commits_90d AS DOUBLE) / s.commits_prev_90d END AS commit_ratio,
           -- round-robin across labels so a small `limit` still covers every label
           row_number() OVER (PARTITION BY l.label ORDER BY l.repo_id) AS rr
    FROM hackcamp.agent.eval_labels l
    LEFT JOIN hackcamp.gold.repo_health g ON g.repo_id = l.repo_id
    LEFT JOIN hackcamp.silver.repos s ON s.repo_id = l.repo_id
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
assert not missing, "Repair missing/renamed labels before evaluation; do not silently shrink the set"
assert LIMIT > 0 or 30 <= len(cases) <= 50, "Full evaluation requires 30–50 cases"
assert len({c.repo_id.lower() for c in cases}) == len(cases), "Duplicate evaluation labels"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run the agent on each labelled repo

# COMMAND ----------


def tool_results_from_trace(trace_id):
    """Concatenate tool outputs from a trace so the judge can check grounding."""
    if not trace_id:
        raise RuntimeError("Cannot judge grounding without a trace")
    trace = mlflow.get_trace(trace_id)
    if trace is None:
        raise RuntimeError(f"Trace unavailable: {trace_id}")
    spans = trace.search_spans(span_type="TOOL")
    if not spans:
        raise RuntimeError(f"Trace has no tool evidence: {trace_id}")
    return json.dumps([{"tool": s.name, "inputs": s.inputs, "outputs": s.outputs} for s in spans], default=str)


results = []
batch_start = time.monotonic()
judge_status = "not_requested"
judge_metrics = {}
judge_coverage = None
with mlflow.start_run(run_name=f"eval-{MODEL}") as mlrun:
    mlflow.set_tags({"evaluation_run_id": RUN_ID, "evaluation_kind": "smoke" if LIMIT else "full",
                     "scoring_policy": "binary_flag_includes_ignored; separate verdict_accuracy",
                     "dataset": "hackcamp.agent.eval_labels"})
    mlflow.log_params(
        {"model": MODEL, "max_tool_calls": MAX_TOOL_CALLS, "n_cases": len(cases),
         "repo_timeout_sec": REPO_TIMEOUT_SEC, "run_judge": RUN_JUDGE,
         "model_max_retries": llm.max_retries, "memory_enabled": False,
         "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
         "weight_release": 30, "weight_commits": 25, "weight_activity": 10}
    )
    mlflow.log_dict([c.asDict() for c in cases], "eval_labels_snapshot.json")
    mlflow.log_dict({label: sum(c.label == label for c in cases) for label in sorted({c.label for c in cases})},
                    "label_counts.json")
    weight_trials = weight_sensitivity([c.asDict() for c in cases])
    mlflow.log_dict({"trials": weight_trials, "final_weights": {"release": 30, "commits": 25, "activity": 10},
                     "decision": "Retain PRD weights; sensitivity results reuse evaluation labels and are not held-out evidence."},
                    "weight_sensitivity.json")
    for c in cases:
        print(f"=== {c.repo_id} (label={c.label}) ===")
        repo_started = time.monotonic()
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
                "duration_sec": time.monotonic() - repo_started,
            }
        )
        mlflow.log_metric("cases_completed", len(results))
        print(f"  agent={verdict.risk_level} formula={c.formula_status}")

    agent_m = score(results)
    formula_m = score({"label": r["label"], "pred": r["formula_pred"]} for r in results)

    def _log(prefix, m):
        mlflow.log_metrics({f"{prefix}_{k}": v for k, v in m.items() if v is not None})

    _log("agent", agent_m)
    _log("formula", formula_m)
    investigation_duration = time.monotonic() - batch_start
    mlflow.log_metric("investigation_duration_sec", investigation_duration)
    first_twenty_duration = sum(r["duration_sec"] for r in results[:20])
    mlflow.log_metric("first_20_repos_duration_sec", first_twenty_duration)
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
                model=f"databricks:/{MODEL}",
                timeout=180,
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
                    judge_metrics[k] = v
            audit = complete_grounding(mlflow, mlrun.info.run_id, mlrun.info.experiment_id,
                                       [r["repo_id"] for r in results], grounded)
            judge_coverage = audit["final"]
            mlflow.log_dict(audit, "grounding_assessments.json")
            root = f"/Volumes/hackcamp/raw/github/evaluations/{RUN_ID}"
            dbutils.fs.put(root + "/grounding_assessments.json", json.dumps(audit, default=str), overwrite=True)
            mlflow.log_metric("judge_initial_grounded_mean", audit["initial"]["mean"])
            mlflow.log_metrics({"judge_valid_cases": audit["final"]["valid"], "judge_failed_cases": audit["final"]["failed"]})
            if not audit["final"]["complete"]:
                raise RuntimeError("Some grounding assessments still failed after bounded retries")
            judge_metrics["grounded/mean"] = audit["final"]["mean"]
            mlflow.log_metric("judge_grounded_mean", audit["final"]["mean"])
            mlflow.log_metric("grounded/mean", audit["final"]["mean"])
            judge_status = "completed"
        except Exception as e:
            judge_status = "failed"
            mlflow.log_text(f"{type(e).__name__}: {e}", "judge_error.txt")
            print(f"Groundedness judge failed: {type(e).__name__}: {e}")

    mlflow.set_tag("judge_status", judge_status)
    evaluation_summary = {"run_id": RUN_ID, "mlflow_run_id": mlrun.info.run_id,
                          "experiment_id": mlrun.info.experiment_id, "n_cases": len(cases),
                          "agent": agent_m, "formula": formula_m, "judge_status": judge_status,
                          "judge_metrics": judge_metrics, "investigation_duration_sec": investigation_duration,
                          "judge_coverage": judge_coverage,
                          "first_20_repos_duration_sec": first_twenty_duration,
                          "final_weights": {"release": 30, "commits": 25, "activity": 10},
                          "is_smoke": LIMIT > 0}
    evaluation_summary["model_max_retries"] = llm.max_retries
    evaluation_summary["prompt_sha256"] = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
    # eval_score is the model's labelled-set benchmark, not batch accuracy on
    # unlabelled repos. Attach it to the latest real run of the same model so an
    # eval-only row cannot replace the app's latest investigation/run badges.
    if LIMIT == 0 and judge_status == "completed":
        targets = spark.sql("""SELECT run_id FROM hackcamp.agent.runs
                            WHERE model=:model AND run_id NOT LIKE 'eval-%'
                            ORDER BY started_at DESC LIMIT 1""", args={"model": MODEL}).collect()
        if not targets:
            raise RuntimeError("No real investigation run for this model; cannot attach eval_score")
        target_run_id = targets[0].run_id
        spark.sql("UPDATE hackcamp.agent.runs SET eval_score=:score WHERE run_id=:run_id",
                  args={"score": float(agent_m["accuracy"]), "run_id": target_run_id})
        evaluation_summary["score_target_run_id"] = target_run_id
        mlflow.set_tag("score_target_run_id", target_run_id)

    mlflow.log_dict(evaluation_summary, "evaluation_summary.json")

    summary_path = f"/Volumes/hackcamp/raw/github/evaluations/{RUN_ID}/summary.json"
    dbutils.fs.put(summary_path, json.dumps(evaluation_summary, indent=2), overwrite=True)
    dbutils.jobs.taskValues.set(key="summary_path", value=summary_path)
    dbutils.jobs.taskValues.set(key="mlflow_run_id", value=mlrun.info.run_id)
    print(json.dumps(evaluation_summary, indent=2))
    if RUN_JUDGE and judge_status != "completed":
        raise RuntimeError("Groundedness judge failed; evaluation is incomplete. See MLflow judge_error.txt")

print(f"MLflow run: {mlrun.info.run_id}")

# COMMAND ----------

summary = spark.createDataFrame(
    [
        (k, float(agent_m[k]) if agent_m.get(k) is not None else None,
         float(formula_m[k]) if formula_m.get(k) is not None else None)
        for k in ["n", "accuracy", "at_risk_precision", "at_risk_recall",
                  "hard_case_false_alarm_rate", "inconclusive_rate", "median_tool_calls"]
    ],
    "metric string, agent double, formula double",
)
display(summary)
display(spark.createDataFrame(results).select("repo_id", "label", "pred", "formula_pred", "confidence", "tool_calls", "headline"))
