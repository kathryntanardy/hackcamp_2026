"""Bronze: Auto Loader ingest of raw GitHub JSON from UC Volume."""

from pyspark import pipelines as dp
from pyspark.sql import functions as F


def _volume_path() -> str:
    return spark.conf.get("volume_path", "/Volumes/hackcamp/raw/github").rstrip("/")


@dp.table(
    name="hackcamp.bronze.github_repos_raw",
    comment="Raw GitHub API responses — one row per repo per pull",
    table_properties={
        "quality": "bronze",
        "pipelines.autoOptimize.zOrderCols": "repo_id",
    },
)
@dp.expect_or_drop("repo_id_present", "repo_id IS NOT NULL AND length(repo_id) > 0")
@dp.expect_or_drop("payload_present", "payload IS NOT NULL")
def github_repos_raw():
    path = f"{_volume_path()}/repos"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.includeExistingFiles", "true")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .load(path)
        .select(
            F.col("repo_id").cast("string").alias("repo_id"),
            F.to_json(F.col("payload")).alias("payload"),
            F.to_timestamp(F.col("pulled_at")).alias("pulled_at"),
            F.col("_metadata.file_path").alias("source_file"),
            F.current_timestamp().alias("ingested_at"),
        )
    )
