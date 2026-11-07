"""Turn an agent MLflow trace into ordered steps for the "How the agent decided" tab."""

import json
from typing import Any

import mlflow


def _parse(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def spans_to_steps(spans: list[Any]) -> list[dict[str, Any]]:
    """One step per TOOL span; reasoning is the text of the LLM call that chose it."""
    steps: list[dict[str, Any]] = []
    reasoning = None
    for span in sorted(spans, key=lambda s: s.start_time_ns):
        if span.span_type == "CHAT_MODEL":
            reasoning = (span.outputs or {}).get("content") or None
        elif span.span_type == "TOOL":
            result = _parse((span.outputs or {}).get("result"))
            steps.append({
                "step": len(steps) + 1,
                "tool": span.name,
                "inputs": span.inputs or {},
                "result": result,
                "reasoning": reasoning,
            })
            reasoning = None
    return steps


def get_trace_steps(trace_id: str) -> list[dict[str, Any]]:
    mlflow.set_tracking_uri("databricks")
    trace = mlflow.MlflowClient().get_trace(trace_id)
    return spans_to_steps(trace.data.spans)
