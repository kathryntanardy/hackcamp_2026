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

dbutils.widgets.text("budget_n", "5")
dbutils.widgets.text("model_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("max_tool_calls", "8")
dbutils.widgets.text("repo_timeout_sec", "180")
dbutils.widgets.text("experiment_path", "")

BUDGET_N = int(dbutils.widgets.get("budget_n"))
MODEL = dbutils.widgets.get("model_endpoint")
MAX_TOOL_CALLS = int(dbutils.widgets.get("max_tool_calls"))
REPO_TIMEOUT_SEC = int(dbutils.widgets.get("repo_timeout_sec"))
EXPERIMENT_PATH = dbutils.widgets.get("experiment_path").strip() or f"/Users/{WorkspaceClient().current_user.me().user_name}/hackcamp-agent"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]

print(
    f"run_id={RUN_ID} model={MODEL} budget_n={BUDGET_N} "
    f"max_tool_calls={MAX_TOOL_CALLS} repo_timeout_sec={REPO_TIMEOUT_SEC}"
)

# COMMAND ----------

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(EXPERIMENT_PATH)


def _databricks_auth() -> tuple[str, str]:
    """Resolve host + token for Foundation Model API calls from a job/notebook."""
    import os

    host = None
    token = None

    # Notebook / job context (preferred on Databricks)
    try:
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        host = ctx.apiUrl().get() if ctx.apiUrl().isDefined() else None
        token = ctx.apiToken().get() if ctx.apiToken().isDefined() else None
    except Exception:
        pass

    # WorkspaceClient / env fallbacks
    w = WorkspaceClient()
    host = host or w.config.host or os.environ.get("DATABRICKS_HOST")
    token = (
        token
        or w.config.token
        or os.environ.get("DATABRICKS_TOKEN")
        or os.environ.get("OPENAI_API_KEY")
    )

    if not host or not token:
        raise RuntimeError(
            "Could not resolve Databricks host/token for Foundation Model API calls"
        )
    return host.rstrip("/"), token


_DB_HOST, _DB_TOKEN = _databricks_auth()
llm = OpenAI(api_key=_DB_TOKEN, base_url=f"{_DB_HOST}/serving-endpoints", max_retries=0)

# COMMAND ----------

# MAGIC %run ./live_fetch_tools

# COMMAND ----------

# MAGIC %run ./trace_steps

# COMMAND ----------

UC_TOOLS = {
    "get_repo_metrics": {
        "uc": "hackcamp.tools.get_repo_metrics",
        "sql": "SELECT hackcamp.tools.get_repo_metrics(?) AS r",
        "params": ["repo"],
        "description": "Latest gold baseline score and collected snapshot metrics. Null metrics are unknown, not zero.",
    },
    "get_commit_trend": {
        "uc": "hackcamp.tools.get_commit_trend",
        "sql": "SELECT hackcamp.tools.get_commit_trend(?, ?) AS r",
        "params": ["repo", "weeks"],
        "description": "Two fixed 90-day commit totals and their percentage change. No weekly history. weeks is compatibility-only; a zero denominator gives unknown change.",
    },
    "get_release_history": {
        "uc": "hackcamp.tools.get_release_history",
        "sql": "SELECT hackcamp.tools.get_release_history(?) AS r",
        "params": ["repo"],
        "description": "Latest release only and days since release at collection time. No full history or inter-release gaps; absent release data is unknown.",
    },
    "get_issue_backlog": {
        "uc": "hackcamp.tools.get_issue_backlog",
        "sql": "SELECT hackcamp.tools.get_issue_backlog(?) AS r",
        "params": ["repo"],
        "description": "Open issue and PR counts only. Reply rates, unanswered counts and response times are unavailable and null.",
    },
    "get_previous_finding": {
        "uc": "hackcamp.tools.get_previous_finding",
        "sql": "SELECT hackcamp.tools.get_previous_finding(?) AS r",
        "params": ["repo"],
        "description": "Most recent prior agent verdict for this repo, if any.",
    },
}

LIVE_TOOLS = {
    "fetch_recent_issues": {
        "description": (
            "Fetch the last n GitHub issues for a repo (titles) and whether a "
            "maintainer replied. Read-only. Results are cached in Delta."
        ),
    },
    "fetch_readme_signals": {
        "description": (
            "Scan the README/repo for deprecated, unmaintained, archived, or "
            "'use X instead' signals. Read-only. Results are cached in Delta."
        ),
    },
}

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_repo_metrics",
            "description": UC_TOOLS["get_repo_metrics"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string", "description": "org/repo"}},
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_commit_trend",
            "description": UC_TOOLS["get_commit_trend"]["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "weeks": {"type": "integer", "default": 12},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_release_history",
            "description": UC_TOOLS["get_release_history"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_issue_backlog",
            "description": UC_TOOLS["get_issue_backlog"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_previous_finding",
            "description": UC_TOOLS["get_previous_finding"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_recent_issues",
            "description": LIVE_TOOLS["fetch_recent_issues"]["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "n": {"type": "integer", "default": 5},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_readme_signals",
            "description": LIVE_TOOLS["fetch_readme_signals"]["description"],
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a maintainer-risk analyst for open-source packages.
Investigate ONE repository using the provided tools. Choose which tools to call and in what order — there is no fixed sequence.
Do not invent metrics — every claim must come from a tool result.
Null or unavailable is unknown, not zero or evidence of abandonment.
The MVP provides fixed 90-day commit windows, latest release and backlog counts.
Do not claim weekly history, inter-release gaps, contributor concentration, or unanswered/response-time metrics from the snapshot.
Contributor concentration is disabled until measured history exists.
Only get_previous_finding may return historical verdicts; distinguish their date from the current snapshot.
Prefer UC metric tools; use fetch_recent_issues / fetch_readme_signals when you need live GitHub evidence.
When requesting tools, provide a brief public decision summary in assistant content when possible.
Do not provide private chain-of-thought; final explanations should summarize the evidence.
Never open issues or post comments — tools are read-only.

When signals conflict (e.g. low recent commits but steady releases, or high stars but archived), dig deeper with another tool before deciding — that often means mature/quiet rather than abandoned.

Scoring rubric (align with baseline formula):
- healthy: active releases/commits, shared ownership, maintainers reply
- watchlist: slowing activity, rising bus factor, aging releases
- at_risk: thinning maintenance or long silence without an official deprecation notice
- ignored: officially deprecated / unmaintained (README or project status) or archived-as-deprecated — park it; maintainers will not review future PRs
- inconclusive: evidence is missing, insufficient or conflicting; never force a risk verdict from unavailable metrics

If tools show official deprecation (or gold status already ignored), emit risk_level=ignored and stop. Do not keep investigating parked lines.

Stop calling tools when confidence >= 0.7, after an ignored decision, or after the tool budget (max 8 calls).
When done, reply with ONLY a JSON object (no markdown) matching:
{
  "repo_id": "org/repo",
  "risk_level": "healthy|watchlist|at_risk|ignored|inconclusive",
  "confidence": 0.0,
  "headline": "one line",
  "explanation": "2-4 sentences",
  "evidence": [{"signal": "...", "tool": "get_release_history", "value": "..."}],
  "changed_since_last": "newly_at_risk|recovered|unchanged|first_seen|newly_ignored",
  "alternatives": [],
  "tool_calls": 0
}
Every evidence.tool must be a tool you actually called.
"""

# COMMAND ----------

class EvidenceItem(BaseModel):
    signal: str
    tool: str
    value: Any = ""


class Verdict(BaseModel):
    repo_id: str
    risk_level: str
    confidence: float = Field(ge=0.0, le=1.0)
    headline: str
    explanation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    changed_since_last: str = "first_seen"
    alternatives: list[str] = Field(default_factory=list)
    tool_calls: int = 0

    @field_validator("risk_level")
    @classmethod
    def _risk(cls, v: str) -> str:
        allowed = {"healthy", "watchlist", "at_risk", "ignored", "inconclusive"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}")
        return v

    @field_validator("changed_since_last")
    @classmethod
    def _changed(cls, v: str) -> str:
        allowed = {
            "newly_at_risk",
            "recovered",
            "unchanged",
            "first_seen",
            "newly_ignored",
        }
        if v not in allowed:
            return "first_seen"
        return v


def _safe_repo(repo_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo_id):
        raise ValueError(f"invalid repo_id: {repo_id}")
    return repo_id


def execute_tool(name: str, args: dict[str, Any], allowed_repo: str) -> str:
    repo = _safe_repo(str(args.get("repo", allowed_repo)))
    if repo != allowed_repo:
        return json.dumps({"error": "tool repo must match investigation target"})

    if name in LIVE_TOOLS:
        try:
            if name == "fetch_recent_issues":
                n = int(args.get("n", 5))
                return json.dumps(fetch_recent_issues(repo, n=n))
            if name == "fetch_readme_signals":
                return json.dumps(fetch_readme_signals(repo))
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}", "tool": name})

    if name not in UC_TOOLS:
        return json.dumps({"error": f"unknown tool {name}"})

    spec = UC_TOOLS[name]
    if name == "get_commit_trend":
        weeks = int(args.get("weeks", 12))
        weeks = max(1, min(weeks, 52))
        row = spark.sql(
            f"SELECT {spec['uc']}('{repo}', {weeks}) AS r"
        ).collect()[0]
    else:
        row = spark.sql(f"SELECT {spec['uc']}('{repo}') AS r").collect()[0]
    return row.r if row.r is not None else json.dumps({"error": "null result"})


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def validate_verdict(
    raw: dict[str, Any], repo_id: str, called_tools: set[str], tool_calls: int
) -> Verdict:
    raw = dict(raw)
    raw["repo_id"] = repo_id
    raw["tool_calls"] = tool_calls
    verdict = Verdict.model_validate(raw)
    kept = [e for e in verdict.evidence if e.tool in called_tools]
    verdict.evidence = kept
    if verdict.confidence >= 0.7 and len(kept) == 0 and called_tools:
        verdict.confidence = min(verdict.confidence, 0.69)
    return verdict


def inconclusive(repo_id: str, tool_calls: int, reason: str) -> Verdict:
    return Verdict(
        repo_id=repo_id,
        risk_level="inconclusive",
        confidence=0.0,
        headline="Investigation inconclusive",
        explanation=reason,
        evidence=[],
        changed_since_last="first_seen",
        alternatives=[],
        tool_calls=tool_calls,
    )

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

candidates = (
    spark.table("hackcamp.gold.repo_health")
    .filter(F.col("status") != "ignored")
    .join(parked, on="repo_id", how="left_anti")
    .withColumn(
        "priority",
        F.col("importance")
        * (F.lit(100.0) - F.coalesce(F.col("health_score"), F.lit(50.0))),
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

assert triage, (
    "No repos to investigate — is gold.repo_health empty, or is everything ignored?"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Investigate

# COMMAND ----------

def call_model(messages, *, phase="decide", temperature=0.2, tools=None, timeout=90):
    """Trace every model call, including validation retries and budget finalization."""
    with mlflow.start_span(name=f"llm_{phase}", span_type="CHAT_MODEL") as span:
        span.set_attribute("phase", phase)
        span.set_inputs({"messages": messages, "model": MODEL})
        kwargs = {"model": MODEL, "messages": messages, "temperature": temperature, "timeout": timeout}
        if tools is not None:
            kwargs.update(tools=tools, tool_choice="auto")
        response = llm.chat.completions.create(**kwargs)
        message = response.choices[0].message
        # Log only the visible answer/tool requests, never provider reasoning_content.
        span.set_outputs({
            "content": message.content,
            "tool_calls": [{"name": call.function.name, "arguments": call.function.arguments}
                           for call in (message.tool_calls or [])],
        })
        return message


def investigate_repo(repo_id: str, triage_reason: str) -> tuple[Verdict, str]:
    user_msg = (
        f"Investigate maintainer risk for `{repo_id}`.\n"
        f"Triage reason: {triage_reason}\n"
        "Choose which tools to call and in what order (no fixed sequence).\n"
        f"Tool budget: {MAX_TOOL_CALLS} calls. Per-repo wall clock: {REPO_TIMEOUT_SEC}s."
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}]
    called_tools = set()
    tool_calls = 0
    decisions = 0
    verdict = None
    deadline = time.monotonic() + REPO_TIMEOUT_SEC

    def _timed_out():
        return time.monotonic() >= deadline

    def _call_with_deadline(messages, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
        message = call_model(messages, timeout=min(90, remaining), **kwargs)
        if _timed_out():
            raise TimeoutError(f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
        return message

    with mlflow.start_span(name=f"investigate:{repo_id}", span_type="AGENT") as root:
        # Capture the owning root directly; a global last-trace lookup can be stale.
        trace_id = root.trace_id
        if not trace_id:
            raise RuntimeError("Investigation did not receive an MLflow trace ID")
        root.set_inputs({"repo_id": repo_id, "run_id": RUN_ID, "triage_reason": triage_reason,
                         "repo_timeout_sec": REPO_TIMEOUT_SEC})
        root.set_attribute("repo_id", repo_id)
        root.set_attribute("run_id", RUN_ID)
        try:
            while tool_calls < MAX_TOOL_CALLS and decisions < MAX_TOOL_CALLS + 2:
                if _timed_out():
                    raise TimeoutError(f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
                decisions += 1
                msg = _call_with_deadline(messages, tools=OPENAI_TOOLS)
                if msg.tool_calls:
                    messages.append({
                        "role": "assistant", "content": msg.content or "",
                        "tool_calls": [{"id": tc.id, "type": "function", "function": {
                            "name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in msg.tool_calls],
                    })
                    for tc in msg.tool_calls:
                        if _timed_out():
                            raise TimeoutError(f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
                        if tool_calls >= MAX_TOOL_CALLS:
                            # Complete the model protocol without claiming an unexecuted tool span.
                            messages.append({"role": "tool", "tool_call_id": tc.id,
                                             "content": '{"error":"Tool budget exhausted; not executed"}'})
                            continue
                        name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                            if not isinstance(args, dict):
                                args = {}
                        except json.JSONDecodeError:
                            args = {}
                        args.setdefault("repo", repo_id)
                        with mlflow.start_span(name=name, span_type="TOOL") as tool_span:
                            tool_span.set_inputs(args)
                            tool_span.set_attribute("step_index", tool_calls + 1)
                            tool_span.set_attribute("tool_call_id", tc.id)
                            summary = public_summary(msg.content)
                            if summary:
                                tool_span.set_attribute("decision_summary", summary)
                            try:
                                result = execute_tool(name, args, repo_id)
                            except Exception as exc:
                                result = json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:500]}", "tool": name})
                            try:
                                parsed = json.loads(result)
                            except (ValueError, TypeError):
                                parsed = result
                            tool_span.set_outputs({"result": parsed})
                            if isinstance(parsed, dict) and parsed.get("error"):
                                tool_span.set_status("ERROR")
                        called_tools.add(name)
                        tool_calls += 1
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                        if _timed_out():
                            raise TimeoutError(f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
                    continue

                content = msg.content or ""
                try:
                    verdict = validate_verdict(extract_json(content), repo_id, called_tools, tool_calls)
                    if len(called_tools) < 2:
                        verdict = None
                        messages.extend([{"role": "assistant", "content": content}, {
                            "role": "user", "content": "Call at least 2 different tools before concluding; continue investigating."}])
                        continue
                    break
                except (json.JSONDecodeError, ValidationError) as exc:
                    messages.extend([{"role": "assistant", "content": content}, {
                        "role": "user", "content": f"Your last reply was invalid ({exc}). Return ONLY valid verdict JSON."}])
                    retry = _call_with_deadline(messages, phase="structured_retry", temperature=0.1)
                    try:
                        verdict = validate_verdict(extract_json(retry.content or ""), repo_id, called_tools, tool_calls)
                    except Exception as exc2:
                        verdict = inconclusive(repo_id, tool_calls, f"Invalid verdict after retry: {type(exc2).__name__}")
                    break
            if verdict is None:
                messages.append({"role": "user", "content": "Investigation limit reached. Return the final verdict JSON from available evidence now."})
                final = _call_with_deadline(messages, phase="budget_finalize", temperature=0.1)
                try:
                    verdict = validate_verdict(extract_json(final.content or ""), repo_id, called_tools, tool_calls)
                except Exception as exc:
                    verdict = inconclusive(repo_id, tool_calls, f"No valid final verdict: {type(exc).__name__}")
        except Exception as exc:
            root.set_status("ERROR")
            root.set_attribute("error_type", type(exc).__name__)
            if isinstance(exc, TimeoutError) or _timed_out():
                root.set_attribute("timed_out", True)
                verdict = inconclusive(repo_id, tool_calls, f"Per-repo timeout after {REPO_TIMEOUT_SEC}s")
            else:
                verdict = inconclusive(repo_id, tool_calls, f"Investigation failed: {type(exc).__name__}: {str(exc)[:300]}")
        root.set_outputs(verdict.model_dump())
    return verdict, trace_id

# COMMAND ----------

findings: list[dict[str, Any]] = []
trace_exports = []
tool_calls_total = 0

for item in triage:
    repo_id = item["repo_id"]
    print(f"\n=== Investigating {repo_id} ===")
    verdict, trace_id = investigate_repo(repo_id, item["reason"])
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

dbutils.jobs.taskValues.set(key="run_id", value=RUN_ID)
print(f"Wrote {len(findings)} findings and trace exports for run_id={RUN_ID}")
display(findings_df.select("repo_id", "risk_level", "confidence", "headline", "tool_calls", "trace_id"))
