"""SQL warehouse access. Auth comes from the Databricks SDK config
(DATABRICKS_CONFIG_PROFILE locally, injected service principal on Databricks Apps).
On Render/external hosts, set DATABRICKS_HOST + DATABRICKS_TOKEN (+ warehouse id)."""

import os
from typing import Any

import certifi
from databricks import sql
from databricks.sdk.core import Config

DEFAULT_WAREHOUSE_ID = "61553be907916cd7"  # Serverless Starter Warehouse


def query(statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = Config()
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", DEFAULT_WAREHOUSE_ID)
    host = (cfg.host or "").removeprefix("https://").rstrip("/")
    http_path = f"/sql/1.0/warehouses/{warehouse_id}"
    # PAT path is reliable on Render; credentials_provider is for Apps / local profile.
    token = (os.environ.get("DATABRICKS_TOKEN") or "").strip()
    connect_kwargs: dict[str, Any] = {
        "server_hostname": host,
        "http_path": http_path,
        "_tls_trusted_ca_file": certifi.where(),  # some local Pythons have an empty CA store
    }
    if token:
        connect_kwargs["access_token"] = token
    else:
        connect_kwargs["credentials_provider"] = cfg.authenticate
    with sql.connect(**connect_kwargs) as conn, conn.cursor() as cur:
        cur.execute(statement, params or {})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
