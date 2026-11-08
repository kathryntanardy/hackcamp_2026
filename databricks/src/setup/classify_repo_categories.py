# Databricks notebook source
# MAGIC %md
# MAGIC # Classify repo categories (F15 / #32) — optional notebook path
# MAGIC
# MAGIC Prefer the SQL job task (`classify_repo_categories.sql` on the Serverless
# MAGIC warehouse). This notebook is a fallback that does the same `ai_query`
# MAGIC overwrite of `hackcamp.silver.repo_categories`.

# COMMAND ----------

dbutils.widgets.text("model_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("limit", "0")  # 0 = all repos

# COMMAND ----------

MODEL = dbutils.widgets.get("model_endpoint").strip()
LIMIT = int(dbutils.widgets.get("limit") or "0")

LABELS = (
    "Front-end",
    "Back-end",
    "Machine learning",
    "Database",
    "Hardware/embedded",
    "DevOps & infra",
    "other",
)
LABEL_LIST = ", ".join(LABELS)

# COMMAND ----------

from pyspark.sql import functions as F

repos = spark.table("hackcamp.silver.repos").select(
    "repo_id",
    F.coalesce(F.col("description"), F.lit("")).alias("description"),
    F.coalesce(F.col("topics"), F.array().cast("array<string>")).alias("topics"),
)
if LIMIT > 0:
    repos = repos.limit(LIMIT)

with_prompt = repos.withColumn(
    "prompt",
    F.concat(
        F.lit(
            "Classify this GitHub repository into exactly one of these labels "
            f"and reply with only that label: {LABEL_LIST}.\n"
            "Repo description: "
        ),
        F.col("description"),
        F.lit("\nTopics: "),
        F.concat_ws(", ", F.col("topics")),
    ),
)

classified = with_prompt.select(
    "repo_id",
    F.expr(
        f"""
        ai_query(
          '{MODEL}',
          prompt,
          failOnError => false
        )
        """
    ).alias("ai"),
).select(
    "repo_id",
    F.trim(F.col("ai.result")).alias("raw_category"),
    F.col("ai.errorMessage").alias("error_message"),
)

normalized = classified.withColumn(
    "category",
    F.coalesce(
        F.expr(
            """
            CASE lower(trim(raw_category))
              WHEN 'front-end' THEN 'Front-end'
              WHEN 'frontend' THEN 'Front-end'
              WHEN 'front end' THEN 'Front-end'
              WHEN 'back-end' THEN 'Back-end'
              WHEN 'backend' THEN 'Back-end'
              WHEN 'back end' THEN 'Back-end'
              WHEN 'machine learning' THEN 'Machine learning'
              WHEN 'machine-learning' THEN 'Machine learning'
              WHEN 'ml' THEN 'Machine learning'
              WHEN 'database' THEN 'Database'
              WHEN 'hardware/embedded' THEN 'Hardware/embedded'
              WHEN 'hardware' THEN 'Hardware/embedded'
              WHEN 'embedded' THEN 'Hardware/embedded'
              WHEN 'devops & infra' THEN 'DevOps & infra'
              WHEN 'devops' THEN 'DevOps & infra'
              WHEN 'other' THEN 'other'
              ELSE NULL
            END
            """
        ),
        F.lit("other"),
    ),
).withColumn("classified_at", F.current_timestamp()).withColumn(
    "model_endpoint", F.lit(MODEL)
)

out = normalized.select(
    "repo_id", "category", "raw_category", "error_message", "model_endpoint", "classified_at"
)

out.write.format("delta").mode("overwrite").option(
    "overwriteSchema", "true"
).saveAsTable("hackcamp.silver.repo_categories")

counts = (
    spark.table("hackcamp.silver.repo_categories")
    .groupBy("category")
    .count()
    .orderBy(F.desc("count"))
    .collect()
)
for row in counts:
    print(f"  {row['category']}: {row['count']}")
n = spark.table("hackcamp.silver.repo_categories").count()
err_n = spark.table("hackcamp.silver.repo_categories").filter("error_message IS NOT NULL").count()
other_n = spark.table("hackcamp.silver.repo_categories").filter("category = 'other'").count()
print(f"Wrote {n} rows to hackcamp.silver.repo_categories via ai_query({MODEL})")
print(f"errors={err_n} other={other_n} other_pct={100.0 * other_n / max(n, 1):.1f}")
