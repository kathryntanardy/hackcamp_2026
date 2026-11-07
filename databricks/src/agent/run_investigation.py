# Databricks notebook source
# MAGIC %md
# MAGIC # Maintainer-risk investigation agent
# MAGIC Triages repos from `gold.repo_health`, investigates with UC tool functions via a Foundation Model, writes verdicts to `agent.findings` with MLflow traces.

# COMMAND ----------

# MAGIC %pip install -q --upgrade "mlflow[databricks]>=3.1.0" "openai>=1.40.0" "pydantic>=2.0" "databricks-sdk>=0.36.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import uuid
from datetime import datetime, timezone

dbutils.widgets.text("budget_n", "5")
dbutils.widgets.text("model_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("max_tool_calls", "8")
dbutils.widgets.text("experiment_path", "/Users/philip03ho@gmail.com/hackcamp-agent")

BUDGET_N = int(dbutils.widgets.get("budget_n"))
MODEL = dbutils.widgets.get("model_endpoint")
MAX_TOOL_CALLS = int(dbutils.widgets.get("max_tool_calls"))
EXPERIMENT_PATH = dbutils.widgets.get("experiment_path")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]

print(f"run_id={RUN_ID} model={MODEL} budget_n={BUDGET_N}")

# COMMAND ----------

# MAGIC %run ./agent_core

# COMMAND ----------

# MAGIC %md
# MAGIC ## Triage

# COMMAND ----------

candidates = (
    spark.table("hackcamp.gold.repo_health")
    .withColumn(
        "priority",
        F.col("importance") * (F.lit(100.0) - F.col("health_score")),
    )
    .orderBy(F.col("priority").desc())
    .limit(BUDGET_N)
    .select(
        "repo_id",
        "language",
        "health_score",
        "status",
        "importance",
        "priority",
        "days_since_release",
        "commit_trend_pct",
    )
)

triage_rows = candidates.collect()
triage = []
for r in triage_rows:
    reason = (
        f"priority={r.priority:.1f} status={r.status} "
        f"health={r.health_score} importance={r.importance}"
    )
    triage.append({"repo_id": r.repo_id, "reason": reason, **r.asDict()})
    print(f"triage: {r.repo_id} — {reason}")

assert triage, "No repos to investigate — is gold.repo_health empty?"

# COMMAND ----------

findings: list[dict[str, Any]] = []
tool_calls_total = 0

for item in triage:
    repo_id = item["repo_id"]
    print(f"\n=== Investigating {repo_id} ===")
    verdict, trace_id = investigate_repo(repo_id, item["reason"])
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
        f"tools={verdict.tool_calls} trace={trace_id}"
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

findings_df = spark.createDataFrame(findings, schema=findings_schema)
findings_df.createOrReplaceTempView("new_findings")

spark.sql(
    """
    MERGE INTO hackcamp.agent.findings AS t
    USING new_findings AS s
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

print(f"Wrote {len(findings)} findings for run_id={RUN_ID}")
display(findings_df.select("repo_id", "risk_level", "confidence", "headline", "tool_calls", "trace_id"))
