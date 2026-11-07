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
dbutils.widgets.text("experiment_path", "/Users/philip03ho@gmail.com/hackcamp-agent")

BUDGET_N = int(dbutils.widgets.get("budget_n"))
MODEL = dbutils.widgets.get("model_endpoint")
MAX_TOOL_CALLS = int(dbutils.widgets.get("max_tool_calls"))
EXPERIMENT_PATH = dbutils.widgets.get("experiment_path")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]

print(f"run_id={RUN_ID} model={MODEL} budget_n={BUDGET_N}")

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
llm = OpenAI(api_key=_DB_TOKEN, base_url=f"{_DB_HOST}/serving-endpoints")

# COMMAND ----------

# MAGIC %run ./live_fetch_tools

# COMMAND ----------

UC_TOOLS = {
    "get_repo_metrics": {
        "uc": "hackcamp.tools.get_repo_metrics",
        "sql": "SELECT hackcamp.tools.get_repo_metrics(?) AS r",
        "params": ["repo"],
        "description": "Baseline health score and core metrics for a repo_id.",
    },
    "get_commit_trend": {
        "uc": "hackcamp.tools.get_commit_trend",
        "sql": "SELECT hackcamp.tools.get_commit_trend(?, ?) AS r",
        "params": ["repo", "weeks"],
        "description": "Commit trend over recent vs previous windows; weeks defaults to 12.",
    },
    "get_release_history": {
        "uc": "hackcamp.tools.get_release_history",
        "sql": "SELECT hackcamp.tools.get_release_history(?) AS r",
        "params": ["repo"],
        "description": "Last release date and days since release.",
    },
    "get_issue_backlog": {
        "uc": "hackcamp.tools.get_issue_backlog",
        "sql": "SELECT hackcamp.tools.get_issue_backlog(?) AS r",
        "params": ["repo"],
        "description": "Open issues/PRs, reply rate, estimated unanswered count.",
    },
    "get_contributor_concentration": {
        "uc": "hackcamp.tools.get_contributor_concentration",
        "sql": "SELECT hackcamp.tools.get_contributor_concentration(?) AS r",
        "params": ["repo"],
        "description": "Top contributor share / bus-factor proxy.",
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
            "name": "get_contributor_concentration",
            "description": UC_TOOLS["get_contributor_concentration"]["description"],
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
Investigate ONE repository using the provided tools. Choose which tools to call yourself.
Do not invent metrics — every claim must come from a tool result.
Prefer UC metric tools first; use fetch_recent_issues / fetch_readme_signals when you need live GitHub evidence.
Never open issues or post comments — tools are read-only.

Scoring rubric (align with baseline formula):
- healthy: active releases/commits, shared ownership, maintainers reply
- watchlist: slowing activity, rising bus factor, aging releases
- at_risk: archived, long release gap, near-zero commits, unanswered backlog, single maintainer dominance
- inconclusive: only if tools conflict and you cannot decide

Stop calling tools when you have enough evidence (aim for confidence >= 0.7), or after the tool budget.
When done, reply with ONLY a JSON object (no markdown) matching:
{
  "repo_id": "org/repo",
  "risk_level": "healthy|watchlist|at_risk|inconclusive",
  "confidence": 0.0,
  "headline": "one line",
  "explanation": "2-4 sentences",
  "evidence": [{"signal": "...", "tool": "get_release_history", "value": "..."}],
  "changed_since_last": "newly_at_risk|recovered|unchanged|first_seen",
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
        allowed = {"healthy", "watchlist", "at_risk", "inconclusive"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}")
        return v

    @field_validator("changed_since_last")
    @classmethod
    def _changed(cls, v: str) -> str:
        allowed = {"newly_at_risk", "recovered", "unchanged", "first_seen"}
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

# MAGIC %md
# MAGIC ## Investigate

# COMMAND ----------

def investigate_repo(repo_id: str, triage_reason: str) -> tuple[Verdict, str | None]:
    user_msg = (
        f"Investigate maintainer risk for `{repo_id}`.\n"
        f"Triage reason: {triage_reason}\n"
        f"Start by calling get_repo_metrics, then choose further tools as needed.\n"
        f"Tool budget: {MAX_TOOL_CALLS} calls."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    called_tools: set[str] = set()
    tool_calls = 0
    verdict: Verdict | None = None

    with mlflow.start_span(name=f"investigate:{repo_id}", span_type="AGENT") as root:
        root.set_inputs({"repo_id": repo_id, "triage_reason": triage_reason})

        while tool_calls < MAX_TOOL_CALLS:
            with mlflow.start_span(name="llm_decide", span_type="CHAT_MODEL") as llm_span:
                llm_span.set_inputs({"messages_tail": messages[-2:], "model": MODEL})
                resp = llm.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                    temperature=0.2,
                )
                msg = resp.choices[0].message
                llm_span.set_outputs(
                    {
                        "content": msg.content,
                        "tool_calls": [
                            {"name": t.function.name, "arguments": t.function.arguments}
                            for t in (msg.tool_calls or [])
                        ],
                    }
                )

            if msg.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    if tool_calls >= MAX_TOOL_CALLS:
                        break
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {"repo": repo_id}
                    args.setdefault("repo", repo_id)

                    with mlflow.start_span(name=name, span_type="TOOL") as tool_span:
                        tool_span.set_inputs(args)
                        result = execute_tool(name, args, repo_id)
                        tool_span.set_outputs({"result": result[:2000]})

                    called_tools.add(name)
                    tool_calls += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue

            # No tool calls — expect final JSON verdict
            content = msg.content or ""
            try:
                raw = extract_json(content)
                verdict = validate_verdict(raw, repo_id, called_tools, tool_calls)
                if tool_calls < 2:
                    # Force at least 2 tools per PRD when model stops early
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You must call at least 2 different tools before concluding. "
                                "Continue investigating."
                            ),
                        }
                    )
                    continue
                root.set_outputs(verdict.model_dump())
                break
            except (json.JSONDecodeError, ValidationError) as exc:
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your last reply was invalid ({exc}). "
                            "Return ONLY valid verdict JSON."
                        ),
                    }
                )
                # one structured retry then fall through
                retry = llm.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.1,
                )
                retry_content = retry.choices[0].message.content or ""
                try:
                    raw = extract_json(retry_content)
                    verdict = validate_verdict(raw, repo_id, called_tools, tool_calls)
                    root.set_outputs(verdict.model_dump())
                except Exception as exc2:
                    verdict = inconclusive(
                        repo_id, tool_calls, f"Invalid verdict after retry: {exc2}"
                    )
                    root.set_outputs(verdict.model_dump())
                break
        else:
            # Budget exhausted — ask for verdict from evidence so far
            messages.append(
                {
                    "role": "user",
                    "content": "Tool budget reached. Return the final verdict JSON now.",
                }
            )
            final = llm.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.1
            )
            try:
                raw = extract_json(final.choices[0].message.content or "")
                verdict = validate_verdict(raw, repo_id, called_tools, tool_calls)
            except Exception as exc:
                verdict = inconclusive(repo_id, tool_calls, f"Budget exhausted; {exc}")
            root.set_outputs(verdict.model_dump())

    if verdict is None:
        verdict = inconclusive(repo_id, tool_calls, "No verdict produced")

    trace_id = None
    try:
        trace_id = mlflow.get_last_active_trace_id()
    except Exception:
        pass
    return verdict, trace_id

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
