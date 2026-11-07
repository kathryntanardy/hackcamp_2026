"""SQL warehouse access. Auth comes from the Databricks SDK config
(DATABRICKS_CONFIG_PROFILE locally, injected service principal on Databricks Apps)."""

import os
from typing import Any

import certifi
from databricks import sql
from databricks.sdk.core import Config

DEFAULT_WAREHOUSE_ID = "61553be907916cd7"  # Serverless Starter Warehouse


def query(statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = Config()
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", DEFAULT_WAREHOUSE_ID)
    with sql.connect(
        server_hostname=cfg.host.removeprefix("https://").rstrip("/"),
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
        _tls_trusted_ca_file=certifi.where(),  # some local Pythons have an empty CA store
    ) as conn, conn.cursor() as cur:
        cur.execute(statement, params or {})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
