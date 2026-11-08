# Databricks notebook source
# MAGIC %md
# MAGIC # Maintainer-risk investigation agent
# MAGIC Triages repos from `gold.repo_health`, investigates with UC tool functions via a Foundation Model, writes verdicts to `agent.findings` with MLflow traces.

# COMMAND ----------

# MAGIC %pip install -q --upgrade "mlflow[databricks]>=3.1.0" "openai>=1.40.0" "pydantic>=2.0" "databricks-sdk>=0.36.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import mlflow
from databricks.sdk import WorkspaceClient
from openai import OpenAI
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pydantic import BaseModel, Field, ValidationError, field_validator

# COMMAND ----------

dbutils.widgets.text("budget_n", "10")
dbutils.widgets.text("model_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("max_tool_calls", "8")
dbutils.widgets.text("repo_timeout_sec", "180")
dbutils.widgets.text("experiment_path", "")
dbutils.widgets.text("uninvestigated_only", "false")
dbutils.widgets.text("coverage_id", "")

BUDGET_N = int(dbutils.widgets.get("budget_n"))
MODEL = dbutils.widgets.get("model_endpoint")
MAX_TOOL_CALLS = int(dbutils.widgets.get("max_tool_calls"))
REPO_TIMEOUT_SEC = int(dbutils.widgets.get("repo_timeout_sec"))
EXPERIMENT_PATH = dbutils.widgets.get("experiment_path").strip() or f"/Users/{WorkspaceClient().current_user.me().user_name}/hackcamp-agent"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
UNINVESTIGATED_ONLY = dbutils.widgets.get("uninvestigated_only").lower() == "true"
COVERAGE_ID = dbutils.widgets.get("coverage_id").strip()
if BUDGET_N == 0 and COVERAGE_ID and UNINVESTIGATED_ONLY:
    assert COVERAGE_ID.isdigit()
    dbutils.notebook.exit("Coverage target already filled; this batch has no remaining work.")
if COVERAGE_ID:
    assert re.fullmatch(r"[0-9]+", COVERAGE_ID), "coverage_id must be the numeric parent job run ID"
    assert UNINVESTIGATED_ONLY, "Coverage runs must select uninvestigated repositories"
    RUN_ID = f"coverage-{COVERAGE_ID}-{RUN_ID}"

print(
    f"run_id={RUN_ID} model={MODEL} budget_n={BUDGET_N} "
    f"max_tool_calls={MAX_TOOL_CALLS} repo_timeout_sec={REPO_TIMEOUT_SEC}"
)

# COMMAND ----------

# MAGIC %run ./agent_core

# COMMAND ----------

import os
import sys
sys.path.insert(0, os.getcwd())
from investigation_coverage import triage_sql

# COMMAND ----------

# MAGIC %md
# MAGIC ## Triage

# COMMAND ----------

# Parked / deprecated lines: skip gold `ignored` and any prior ignored finding.
prev_ignored = (
    spark.table("hackcamp.agent.findings")
    .filter(F.col("risk_level") == "ignored")
    .select("repo_id")
    .distinct()
)
ignored_gold = (
    spark.table("hackcamp.gold.repo_health")
    .filter(F.col("status") == "ignored")
    .select("repo_id")
)
parked = ignored_gold.union(prev_ignored).distinct()
parked_n = parked.count()
print(f"triage: skipping {parked_n} ignored/deprecated repo(s)")

candidates = spark.sql(triage_sql(BUDGET_N, UNINVESTIGATED_ONLY))

triage_rows = candidates.collect()
if COVERAGE_ID:
    assert len(triage_rows) == BUDGET_N, "Not enough uninvestigated repositories to fill this coverage batch"
    dbutils.fs.put(f"/Volumes/hackcamp/raw/github/coverage/{COVERAGE_ID}/selection_{RUN_ID}.json",
                   json.dumps([r.asDict() for r in triage_rows], default=str), overwrite=True)
triage = []
for r in triage_rows:
    reason = (
        f"priority={r.priority:.1f} status={r.status} "
        f"health={r.health_score} importance={r.importance}"
    )
    triage.append({"repo_id": r.repo_id, "reason": reason, **r.asDict()})
    print(f"triage: {r.repo_id} — {reason}")

assert triage, (
    "No repos to investigate — is gold.repo_health empty, or is everything ignored?"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Investigate

# COMMAND ----------

# COMMAND ----------

findings: list[dict[str, Any]] = []
trace_exports = []
tool_calls_total = 0
# Memory (F13): latest prior finding per triaged repo, read before this run's MERGE.
previous_findings = load_previous_findings([t["repo_id"] for t in triage])
print(f"memory: {len(previous_findings)}/{len(triage)} repo(s) have a previous finding")

for item in triage:
    repo_id = item["repo_id"]
    print(f"\n=== Investigating {repo_id} ===")
    verdict, trace_id = investigate_repo(repo_id, item["reason"],
                                         previous=previous_findings.get(repo_id), use_memory=True)
    trace_payload = fetch_trace_steps(trace_id, repo_id=repo_id, run_id=RUN_ID, host=_DB_HOST)
    trace_exports.append((trace_id, repo_id, RUN_ID, json.dumps(trace_payload),
                          datetime.now(timezone.utc).replace(tzinfo=None)))
    tool_calls_total += verdict.tool_calls
    row = {
        "repo_id": verdict.repo_id,
        "run_id": RUN_ID,
        "risk_level": verdict.risk_level,
        "confidence": float(verdict.confidence),
        "headline": verdict.headline,
        "explanation": verdict.explanation,
        "evidence": [
            {"signal": e.signal, "tool": e.tool, "value": str(e.value)}
            for e in verdict.evidence
        ],
        "changed_since_last": verdict.changed_since_last,
        "alternatives": verdict.alternatives,
        "tool_calls": int(verdict.tool_calls),
        "trace_id": trace_id,
        "investigated_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    findings.append(row)
    print(
        f"→ {verdict.risk_level} conf={verdict.confidence:.2f} "
        f"tools={verdict.tool_calls} changed={verdict.changed_since_last} trace={trace_id}"
    )
    print(f"  {verdict.headline}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persist findings + run stats

# COMMAND ----------

evidence_schema = ArrayType(
    StructType(
        [
            StructField("signal", StringType(), True),
            StructField("tool", StringType(), True),
            StructField("value", StringType(), True),
        ]
    )
)

findings_schema = StructType(
    [
        StructField("repo_id", StringType(), False),
        StructField("run_id", StringType(), False),
        StructField("risk_level", StringType(), True),
        StructField("confidence", DoubleType(), True),
        StructField("headline", StringType(), True),
        StructField("explanation", StringType(), True),
        StructField("evidence", evidence_schema, True),
        StructField("changed_since_last", StringType(), True),
        StructField("alternatives", ArrayType(StringType()), True),
        StructField("tool_calls", IntegerType(), True),
        StructField("trace_id", StringType(), True),
        StructField("investigated_at", TimestampType(), True),
    ]
)

# Publish app-readable steps before linking findings to their trace IDs.
trace_exports_df = spark.createDataFrame(
    trace_exports, "trace_id STRING, repo_id STRING, run_id STRING, payload STRING, created_at TIMESTAMP"
)
trace_exports_df.createOrReplaceTempView("new_trace_steps")
spark.sql("""
    MERGE INTO hackcamp.agent.trace_steps t USING new_trace_steps s
    ON t.trace_id = s.trace_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
findings_df = spark.createDataFrame(findings, schema=findings_schema)
findings_df.createOrReplaceTempView("new_findings")

# Join gold so Unity Catalog lineage records gold.repo_health → agent.findings
# (createDataFrame alone is not a UC table source and leaves findings with no upstream).
spark.sql(
    """
    MERGE INTO hackcamp.agent.findings AS t
    USING (
      SELECT s.*
      FROM new_findings s
      LEFT JOIN hackcamp.gold.repo_health g ON s.repo_id = g.repo_id
    ) AS s
    ON t.repo_id = s.repo_id AND t.run_id = s.run_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """
)

runs_schema = StructType(
    [
        StructField("run_id", StringType(), False),
        StructField("started_at", TimestampType(), True),
        StructField("repos_triaged", IntegerType(), True),
        StructField("repos_investigated", IntegerType(), True),
        StructField("tool_calls_total", IntegerType(), True),
        StructField("model", StringType(), True),
        StructField("eval_score", DoubleType(), True),
    ]
)
runs_df = spark.createDataFrame(
    [
        (
            RUN_ID,
            datetime.now(timezone.utc).replace(tzinfo=None),
            int(len(triage)),
            int(len(findings)),
            int(tool_calls_total),
            MODEL,
            None,
        )
    ],
    schema=runs_schema,
)
runs_df.write.mode("append").saveAsTable("hackcamp.agent.runs")

dbutils.jobs.taskValues.set(key="run_id", value=RUN_ID)
print(f"Wrote {len(findings)} findings and trace exports for run_id={RUN_ID}")
display(findings_df.select("repo_id", "risk_level", "confidence", "headline", "tool_calls", "trace_id"))
