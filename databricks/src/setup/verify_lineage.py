# Databricks notebook source
# MAGIC %md
# MAGIC # Ticket #16 — verify Unity Catalog lineage (F11)
# MAGIC Confirms edges for Volume / bronze → silver → gold → findings and prints Catalog Explorer links.

# COMMAND ----------

from pyspark.sql import functions as F

HOST = "https://dbc-a0a04386-0e40.cloud.databricks.com"
LINKS = {
    "volume": f"{HOST}/explore/data/volumes/hackcamp/raw/github",
    "bronze": f"{HOST}/explore/data/hackcamp/bronze/github_repos_raw",
    "silver": f"{HOST}/explore/data/hackcamp/silver/repos",
    "gold": f"{HOST}/explore/data/hackcamp/gold/repo_health",
    "findings": f"{HOST}/explore/data/hackcamp/agent/findings",
    "verdicts_lineage": f"{HOST}/explore/data/hackcamp/gold/verdicts_lineage",
}

edges = (
    spark.table("system.access.table_lineage")
    .where(F.col("event_date") >= F.date_sub(F.current_date(), 30))
    .where(
        (F.col("target_table_full_name").isin(
            "hackcamp.bronze.github_repos_raw",
            "hackcamp.silver.repos",
            "hackcamp.gold.repo_health",
            "hackcamp.agent.findings",
            "hackcamp.gold.verdicts_lineage",
        ))
        | (F.col("source_table_full_name").isin(
            "hackcamp.bronze.github_repos_raw",
            "hackcamp.silver.repos",
            "hackcamp.gold.repo_health",
            "hackcamp.agent.findings",
        ))
        | (F.col("source_path").startswith("/Volumes/hackcamp/raw/github"))
    )
    .select(
        F.coalesce("source_table_full_name", "source_path").alias("source"),
        "source_type",
        F.coalesce("target_table_full_name", "target_path").alias("target"),
        "target_type",
        "entity_type",
    )
    .where(F.col("target").isNotNull() & (F.col("target") != ""))
    .distinct()
    .orderBy("source", "target")
)

rows = [r.asDict() for r in edges.collect()]
required = {
    ("hackcamp.bronze.github_repos_raw", "hackcamp.silver.repos"),
    ("hackcamp.silver.repos", "hackcamp.gold.repo_health"),
}
found_pairs = {(r["source"], r["target"]) for r in rows if r.get("source") and r.get("target")}
missing = sorted(required - found_pairs)
gold_to_findings = any(
    r.get("source") == "hackcamp.gold.repo_health" and r.get("target") == "hackcamp.agent.findings"
    for r in rows
)
volume_seen = any(
    isinstance(r.get("source"), str) and str(r.get("source")).startswith("/Volumes/hackcamp/raw/github")
    for r in rows
) or any(r.get("target") == "hackcamp.bronze.github_repos_raw" for r in rows)

summary = {
    "pipeline_bronze_silver_gold": not missing,
    "missing_pipeline_edges": missing,
    "volume_or_bronze_write_seen": volume_seen,
    "gold_to_findings": gold_to_findings,
    "edge_count": len(rows),
    "catalog_explorer": LINKS,
    "demo_tip": (
        "Open gold.verdicts_lineage → Lineage → See Lineage Graph. "
        "Also open bronze/silver/gold Lineage tabs for the pipeline chain."
    ),
}

print("LINEAGE_SUMMARY")
for k, v in summary.items():
    print(f"  {k}: {v}")
print("\nCatalog Explorer (open Lineage tab on each):")
for name, url in LINKS.items():
    print(f"  {name}: {url}")

display(spark.createDataFrame(rows) if rows else spark.createDataFrame([], "source STRING, source_type STRING, target STRING, target_type STRING, entity_type STRING"))

assert not missing, f"Missing pipeline lineage edges: {missing}"
print("TICKET16_LINEAGE_OK")
