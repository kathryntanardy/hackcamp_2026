# Databricks notebook source
"""Ticket #11: project MLflow traces into ordered, app-readable public steps."""

import json
import time


def public_summary(content, limit=600):
    """Use visible assistant text/verdict explanations, never provider reasoning."""
    if not content:
        return None
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        value = content
    if isinstance(value, dict):
        value = value.get("explanation") or value.get("headline")
    if not isinstance(value, str):
        return None
    return value[:limit]


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _status(span):
    status = getattr(span, "status", None)
    return str(getattr(status, "status_code", status) or "UNKNOWN").split(".")[-1]


def trace_to_steps(trace, *, repo_id, run_id, host=None):
    """Serialize public decision summaries and complete tool evidence in time order."""
    spans = list(trace.data.spans)
    roots = [span for span in spans if str(span.span_type).split(".")[-1] == "AGENT"
             and isinstance(span.inputs, dict) and span.inputs.get("repo_id") == repo_id
             and span.inputs.get("run_id") == run_id]
    if len(roots) != 1:
        raise ValueError("Trace does not belong to exactly one matching repository investigation")
    root = roots[0]
    root_outputs = root.outputs if isinstance(root.outputs, dict) else {}
    steps = []
    for span in sorted(spans, key=lambda s: (s.start_time_ns or 0, s.span_id)):
        kind = str(span.span_type).split(".")[-1]
        if kind not in ("TOOL", "CHAT_MODEL"):
            continue
        attributes = getattr(span, "attributes", {}) or {}
        outputs = span.outputs if isinstance(span.outputs, dict) else {}
        if kind == "TOOL":
            result = _json_value(outputs.get("result"))
            reasoning = attributes.get("decision_summary")
            result_summary = json.dumps(result, ensure_ascii=False, default=str)[:600]
            inputs = span.inputs
        else:
            # Never forward messages, system prompts or hidden reasoning fields to the app.
            reasoning = public_summary(outputs.get("content"))
            result = {"content_summary": reasoning, "tool_calls": outputs.get("tool_calls", [])}
            result_summary = reasoning or "Model selected tool calls without a public explanation."
            inputs = {"model": (span.inputs or {}).get("model")} if isinstance(span.inputs, dict) else {}
        steps.append({
            "order": len(steps) + 1, "span_id": span.span_id,
            "kind": "tool" if kind == "TOOL" else "decision",
            "tool_name": span.name if kind == "TOOL" else None,
            "phase": attributes.get("phase"), "status": _status(span),
            "started_at_ms": (span.start_time_ns or 0) // 1_000_000,
            "duration_ms": max(0, ((span.end_time_ns or span.start_time_ns or 0)
                                   - (span.start_time_ns or 0)) // 1_000_000),
            "inputs": inputs, "outputs": result, "result_summary": result_summary,
            "reasoning": reasoning, "reasoning_available": bool(reasoning),
        })
    experiment_id = getattr(trace.info, "experiment_id", None)
    return {
        "trace_id": trace.info.trace_id, "repo_id": repo_id, "run_id": run_id,
        "status": _status(root), "experiment_id": experiment_id,
        "experiment_url": (f"{host.rstrip('/')}/ml/experiments/{experiment_id}/traces"
                           if host and experiment_id else None),
        "explanation": root_outputs.get("explanation"), "steps": steps,
    }


def fetch_trace_steps(trace_id, *, repo_id, run_id, host=None, mlflow_module=None):
    if mlflow_module is None:
        import mlflow as mlflow_module
    flush = getattr(mlflow_module, "flush_trace_async_logging", None)
    if flush:
        flush()
    for attempt in range(3):
        trace = mlflow_module.get_trace(trace_id)
        if trace is not None:
            if trace.info.trace_id != trace_id:
                raise ValueError("MLflow returned a different trace ID")
            return trace_to_steps(trace, repo_id=repo_id, run_id=run_id, host=host)
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"MLflow trace is not retrievable: {trace_id}")


def get_finding_trace(spark, repo_id, run_id=None):
    """Backend handoff: fetch a finding's ordered steps using only the SQL warehouse."""
    row = spark.sql("""
        SELECT f.repo_id, f.run_id, f.trace_id, t.payload
        FROM hackcamp.agent.findings f
        LEFT JOIN hackcamp.agent.trace_steps t
          ON f.trace_id = t.trace_id AND f.repo_id = t.repo_id AND f.run_id = t.run_id
        WHERE f.repo_id = :repo_id AND (:run_id IS NULL OR f.run_id = :run_id)
        ORDER BY f.investigated_at DESC NULLS LAST, f.run_id DESC
        LIMIT 1
    """, args={"repo_id": repo_id, "run_id": run_id}).first()
    if row is None:
        return {"found": False, "repo_id": repo_id, "run_id": run_id, "steps": []}
    if row.payload is None:
        return {"found": True, "status": "not_ready", "repo_id": row.repo_id,
                "run_id": row.run_id, "trace_id": row.trace_id, "steps": []}
    payload = json.loads(row.payload)
    if (payload.get("trace_id"), payload.get("repo_id"), payload.get("run_id")) != (
        row.trace_id, row.repo_id, row.run_id
    ):
        raise ValueError("Stored trace steps do not match the finding")
    return {"found": True, **payload}
