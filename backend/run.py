"""Databricks Apps entrypoint — binds DATABRICKS_APP_PORT (local fallback 8000)."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
