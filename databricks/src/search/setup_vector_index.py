"""Ticket #30: create the Vector Search endpoint + Delta Sync index over gold.repo_search_docs,
then trigger a sync. Idempotent. Run locally: DATABRICKS_CONFIG_PROFILE=school python setup_vector_index.py
Run build_search_docs.sql first (bundle job `repo_search_docs`)."""

import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn, EndpointType,
    PipelineType, VectorIndexType)

ENDPOINT = "hackcamp-vs"
INDEX = "hackcamp.gold.repo_search_index"
SOURCE = "hackcamp.gold.repo_search_docs"
EMBEDDING_MODEL = "databricks-gte-large-en"


def main() -> None:
    w = WorkspaceClient()
    try:
        w.vector_search_endpoints.get_endpoint(ENDPOINT)
    except NotFound:
        print(f"creating endpoint {ENDPOINT} (takes a few minutes)")
        w.vector_search_endpoints.create_endpoint_and_wait(ENDPOINT, endpoint_type=EndpointType.STANDARD)
    try:
        w.vector_search_indexes.get_index(INDEX)
        print(f"index {INDEX} exists; triggering sync")
        w.vector_search_indexes.sync_index(INDEX)
    except NotFound:
        print(f"creating index {INDEX}")
        w.vector_search_indexes.create_index(
            name=INDEX, endpoint_name=ENDPOINT, primary_key="repo_id",
            index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=SOURCE, pipeline_type=PipelineType.TRIGGERED,
                columns_to_sync=["repo_id", "language", "category", "status", "search_text"],
                embedding_source_columns=[EmbeddingSourceColumn(
                    name="search_text", embedding_model_endpoint_name=EMBEDDING_MODEL)]))
    while True:
        status = w.vector_search_indexes.get_index(INDEX).status
        print(f"ready={status.ready} rows={status.indexed_row_count} {status.message}")
        if status.ready:
            return
        time.sleep(20)


if __name__ == "__main__":
    main()
