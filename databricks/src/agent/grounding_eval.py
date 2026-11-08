"""Audit grounding coverage and retry only failed judge calls, never negative scores."""


def grounding_value(value):
    if value is True or value == "yes":
        return 1
    if value is False or value == "no":
        return 0
    return None


def summarize_grounding(rows, expected_ids):
    expected = {repo.lower() for repo in expected_ids}
    ids = [r["inputs"]["repo_id"].lower() for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Grounding assessments do not cover the exact evaluation corpus")
    valid = [grounding_value(r["value"]) for r in rows if not r["error"] and grounding_value(r["value"]) is not None]
    return {"expected": len(expected), "valid": len(valid), "failed": len(expected) - len(valid),
            "passed": sum(valid), "mean": sum(valid) / len(valid) if valid else None,
            "complete": len(valid) == len(expected)}


def complete_grounding(mlflow, run_id, experiment_id, expected_ids, scorer):
    flush = getattr(mlflow, "flush_trace_async_logging", None)
    if flush:
        flush()
    traces = mlflow.search_traces(experiment_ids=[experiment_id], filter_string=f"trace.run_id = '{run_id}'",
                                 max_results=1000, return_type="list")
    rows = []
    prior_retries = {}
    for trace in traces:
        prior = next((a for a in trace.info.assessments or [] if a.name == "grounded_retry"
                      and not a.error and grounding_value(a.value) is not None), None)
        if prior is not None:
            prior_retries[trace.info.trace_id] = {"value": prior.value, "error": None, "rationale": prior.rationale}
        for assessment in trace.info.assessments or []:
            if assessment.name != "grounded":
                continue
            root = next(s for s in trace.data.spans if not s.parent_id)
            rows.append({"trace_id": trace.info.trace_id, "inputs": root.inputs, "outputs": root.outputs,
                         "value": assessment.value, "error": str(assessment.error) if assessment.error else None,
                         "rationale": assessment.rationale, "retries": []})
    initial = summarize_grounding(rows, expected_ids)
    for row in rows:
        if row["trace_id"] in prior_retries and (row["error"] or grounding_value(row["value"]) is None):
            row["initial_error"] = row["error"]
            row.update(prior_retries[row["trace_id"]])
            row["retries"].append({"existing": True, **prior_retries[row["trace_id"]]})
        # A negative judgement is a quality failure, never a reason to try again.
        if not row["error"] and grounding_value(row["value"]) is not None:
            continue
        row["initial_error"] = row["error"]
        for attempt in range(2):
            try:
                feedback = scorer(inputs=row["inputs"], outputs=row["outputs"])
                error = str(feedback.error) if feedback.error else None
                value = feedback.value
                row["retries"].append({"attempt": attempt + 1, "value": value, "error": error})
                mlflow.log_feedback(trace_id=row["trace_id"], name="grounded_retry", value=value,
                                    rationale=feedback.rationale, source=feedback.source,
                                    error=feedback.error)
                row.update(value=value, error=error, rationale=feedback.rationale)
                if not error and grounding_value(value) is not None:
                    break
            except Exception as exc:
                row["error"] = str(exc)
                row["retries"].append({"attempt": attempt + 1, "value": None, "error": str(exc)})
    return {"initial": initial, "final": summarize_grounding(rows, expected_ids), "assessments": rows}
