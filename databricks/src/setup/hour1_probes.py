# Databricks notebook source
# MAGIC %md
# MAGIC # Hour-1 workspace probes
# MAGIC - UC Python outbound HTTP test
# MAGIC - Foundation Model tool-calling comparison

# COMMAND ----------

# MAGIC %pip install -q --upgrade "openai>=1.40.0" "databricks-sdk>=0.36.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import os
from databricks.sdk import WorkspaceClient
from openai import OpenAI

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1) UC Python function outbound HTTP

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE FUNCTION hackcamp.tools.http_probe()
RETURNS STRING
LANGUAGE PYTHON
DETERMINISTIC
COMMENT 'Hour-1 probe: can UC Python functions make outbound HTTP?'
AS $$
import urllib.request
try:
    req = urllib.request.Request(
        "https://httpbin.org/get",
        headers={"User-Agent": "hackcamp-hour1-probe"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read(200).decode("utf-8", errors="replace")
        return f"ok status={resp.status} body_prefix={body[:80]!r}"
except Exception as e:
    return f"error type={type(e).__name__} msg={e}"
$$
""")
print("Created hackcamp.tools.http_probe")

http_result = spark.sql("SELECT hackcamp.tools.http_probe() AS result").collect()[0]["result"]
print("HTTP_PROBE_RESULT:", http_result)
dbutils.jobs.taskValues.set(key="http_probe_result", value=http_result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2) Foundation Model tool-calling bakeoff

# COMMAND ----------

def _auth():
    host = token = None
    try:
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        host = ctx.apiUrl().get() if ctx.apiUrl().isDefined() else None
        token = ctx.apiToken().get() if ctx.apiToken().isDefined() else None
    except Exception:
        pass
    w = WorkspaceClient()
    host = (host or w.config.host or os.environ.get("DATABRICKS_HOST", "")).rstrip("/")
    token = token or w.config.token or os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:
        raise RuntimeError("missing host/token")
    return host, token


host, token = _auth()
llm = OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")

CANDIDATES = [
    "databricks-meta-llama-3-3-70b-instruct",
    "databricks-llama-4-maverick",
    "databricks-meta-llama-3-1-8b-instruct",
    "databricks-gpt-oss-20b",
    "databricks-qwen3-next-80b-a3b-instruct",
    "databricks-qwen35-122b-a10b",
    "databricks-gemma-3-12b",
]

tools = [
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers and return the sum",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
        },
    }
]

results = []
for model in CANDIDATES:
    row = {"model": model, "supports_tools_param": False, "emitted_tool_call": False, "error": None}
    try:
        resp = llm.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "Use the add_numbers tool to add 2 and 3. Do not answer without the tool.",
                }
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=256,
        )
        row["supports_tools_param"] = True
        msg = resp.choices[0].message
        row["emitted_tool_call"] = bool(getattr(msg, "tool_calls", None))
        row["content_preview"] = (msg.content or "")[:120]
        if msg.tool_calls:
            row["tool_name"] = msg.tool_calls[0].function.name
            row["tool_args"] = msg.tool_calls[0].function.arguments
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
    results.append(row)
    print(json.dumps(row))

# Prefer models that both accept tools= and emit a tool call
winners = [r for r in results if r["supports_tools_param"] and r["emitted_tool_call"] and not r["error"]]
# Prefer known strong instruct models in a fixed order among winners
preferred_order = [
    "databricks-meta-llama-3-3-70b-instruct",
    "databricks-llama-4-maverick",
    "databricks-qwen35-122b-a10b",
    "databricks-qwen3-next-80b-a3b-instruct",
    "databricks-gpt-oss-20b",
    "databricks-meta-llama-3-1-8b-instruct",
]
pick = None
for name in preferred_order:
    if any(r["model"] == name for r in winners):
        pick = name
        break
if pick is None and winners:
    pick = winners[0]["model"]

summary = {
    "http_probe_result": http_result,
    "tool_calling_results": results,
    "recommended_model": pick,
    "winner_count": len(winners),
}
print("SUMMARY_JSON:" + json.dumps(summary))

# Persist for the hour-1 report (avoid display()/schema inference issues)
out_path = "/Volumes/hackcamp/raw/github/hour1_probe_summary.json"
dbutils.fs.put(out_path, json.dumps(summary, indent=2), overwrite=True)
print(f"Wrote {out_path}")

spark.sql(
    """
    CREATE TABLE IF NOT EXISTS hackcamp.agent.hour1_checks (
      checked_at TIMESTAMP,
      http_probe_result STRING,
      recommended_model STRING,
      summary_json STRING
    ) USING DELTA
    """
)
spark.createDataFrame(
    [
        {
            "checked_at": __import__("datetime").datetime.utcnow(),
            "http_probe_result": http_result,
            "recommended_model": pick,
            "summary_json": json.dumps(summary),
        }
    ]
).write.mode("append").saveAsTable("hackcamp.agent.hour1_checks")

dbutils.jobs.taskValues.set(
    key="recommended_model", value=pick or "none"
)
dbutils.jobs.taskValues.set(
    key="http_probe_ok", value=str(http_result.startswith("ok"))
)
print("HOUR1_PROBES_DONE")