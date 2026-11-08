import importlib.util
from pathlib import Path
from types import SimpleNamespace as Obj
import pytest

spec = importlib.util.spec_from_file_location("grounding_eval", Path(__file__).resolve().parents[1] / "src/agent/grounding_eval.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_partial_coverage_and_negative_scores_are_distinct():
    rows = [{"inputs": {"repo_id": "a/b"}, "value": "no", "error": None},
            {"inputs": {"repo_id": "c/d"}, "value": None, "error": "timeout"}]
    assert m.summarize_grounding(rows, ["a/b", "c/d"]) == {
        "expected": 2, "valid": 1, "failed": 1, "passed": 0, "mean": 0, "complete": False}
    with pytest.raises(ValueError):
        m.summarize_grounding(rows[:1], ["a/b", "c/d"])


def test_existing_negative_retry_is_preserved_without_rescoring():
    assessments = [Obj(name="grounded", value=None, error="timeout", rationale=None),
                   Obj(name="grounded_retry", value="no", error=None, rationale="unsupported")]
    trace = Obj(info=Obj(trace_id="trace", assessments=assessments),
                data=Obj(spans=[Obj(parent_id=None, inputs={"repo_id": "a/b"}, outputs={})]))
    mlflow = Obj(search_traces=lambda **kw: [trace])
    def scorer(**kw):
        raise AssertionError("Existing negative judgement must not be retried")
    audit = m.complete_grounding(mlflow, "run", "experiment", ["a/b"], scorer)
    assert audit["final"]["complete"] and audit["final"]["mean"] == 0
