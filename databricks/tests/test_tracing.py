"""Trace identity, coverage, public export and finding lookup without remote calls."""

import ast
import copy
import importlib.util
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trace_steps", ROOT / "src/agent/trace_steps.py")
steps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(steps)


class Verdict:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


class Span:
    def __init__(self, tracer, name, span_type):
        self.tracer, self.name, self.span_type = tracer, name, span_type
        self.parent_id = tracer.stack[-1].span_id if tracer.stack else None
        self.trace_id = tracer.stack[-1].trace_id if tracer.stack else f"trace-{len(tracer.spans)}"
        self.span_id = str(len(tracer.spans))
        self.start_time_ns = (len(tracer.spans) + 1) * 1_000_000
        self.end_time_ns = self.start_time_ns + 1_000_000
        self.inputs, self.outputs, self.attributes, self.status = None, None, {}, "OK"
        tracer.spans.append(self)

    def __enter__(self):
        self.tracer.stack.append(self)
        return self

    def __exit__(self, kind, value, tb):
        self.tracer.stack.pop()
        if kind:
            self.status = "ERROR"

    def set_inputs(self, value):
        self.inputs = copy.deepcopy(value)

    def set_outputs(self, value):
        self.outputs = copy.deepcopy(value)

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, value):
        self.status = value


class Tracer:
    def __init__(self):
        self.stack, self.spans = [], []

    def start_span(self, **kwargs):
        return Span(self, **kwargs)

    def get_last_active_trace_id(self):
        raise AssertionError("A global last-trace lookup must never link a finding")


def message(content=None, names=()):
    return NS(content=content, reasoning_content="HIDDEN_REASONING_SENTINEL",
              tool_calls=[NS(id=f"call-{i}", function=NS(name=name, arguments='{"repo":"org/repo"}'))
                          for i, name in enumerate(names)])


FINAL = json.dumps({"repo_id": "org/repo", "risk_level": "healthy", "explanation": "Measured activity is stable."})


def investigation_namespace(responses, budget=4):
    tracer = Tracer()
    queue = list(responses)

    def create(**kwargs):
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return NS(choices=[NS(message=response)])

    def validate(value, repo, called, count):
        return Verdict({**value, "repo_id": repo, "tool_calls": count})

    namespace = {
        "mlflow": tracer, "llm": NS(chat=NS(completions=NS(create=create))),
        "json": json, "MODEL": "test-model", "RUN_ID": "test-run",
        "MAX_TOOL_CALLS": budget, "OPENAI_TOOLS": [], "SYSTEM_PROMPT": "PRIVATE_PROMPT_SENTINEL",
        "REPO_TIMEOUT_SEC": 180, "time": time,
        "Verdict": Verdict, "ValidationError": RuntimeError, "public_summary": steps.public_summary,
        "extract_json": json.loads, "validate_verdict": validate,
        "execute_tool": lambda *args: json.dumps({"value": "x" * 4000}),
        "inconclusive": lambda repo, count, reason: Verdict({"repo_id": repo, "risk_level": "inconclusive", "tool_calls": count, "explanation": reason}),
    }
    tree = ast.parse((ROOT / "src/agent/run_investigation.py").read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("call_model", "investigate_repo")]
    exec(compile(ast.Module(body=functions, type_ignores=[]), "investigation_tracing", "exec"), namespace)
    return namespace, tracer


def exported_trace(tracer, trace_id):
    return NS(info=NS(trace_id=trace_id, experiment_id="123"),
              data=NS(spans=list(reversed([s for s in tracer.spans if s.trace_id == trace_id]))))


class InvestigationTraceTests(unittest.TestCase):
    def test_expired_deadline_stops_before_any_model_call_and_keeps_trace_id(self):
        namespace, tracer = investigation_namespace([])
        namespace["REPO_TIMEOUT_SEC"] = 0
        verdict, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        self.assertEqual(verdict.model_dump()["risk_level"], "inconclusive")
        self.assertIn("Per-repo timeout", verdict.model_dump()["explanation"])
        self.assertEqual(trace_id, tracer.spans[0].trace_id)
        self.assertTrue(tracer.spans[0].attributes["timed_out"])
        self.assertEqual(len(tracer.spans), 1)

    def test_model_request_uses_remaining_budget_and_late_response_is_not_accepted(self):
        namespace, tracer = investigation_namespace([])
        clock, requests = [0.0], []
        namespace["time"] = NS(monotonic=lambda: clock[0])
        namespace["REPO_TIMEOUT_SEC"] = 5

        def delayed_model(**kwargs):
            requests.append(kwargs)
            clock[0] = 6.0
            return NS(choices=[NS(message=message(FINAL))])

        namespace["llm"].chat.completions.create = delayed_model
        verdict, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        self.assertEqual(requests[0]["timeout"], 5.0)
        self.assertEqual(verdict.model_dump()["risk_level"], "inconclusive")
        self.assertTrue(tracer.spans[0].attributes["timed_out"])
        self.assertEqual(trace_id, tracer.spans[0].trace_id)

    def test_timeout_after_tool_preserves_its_evidence_and_skips_remaining_tools(self):
        namespace, tracer = investigation_namespace([message(names=("one", "two"))])
        clock = [0.0]
        namespace["time"] = NS(monotonic=lambda: clock[0])
        namespace["REPO_TIMEOUT_SEC"] = 5

        def delayed_tool(*args):
            clock[0] = 6.0
            return json.dumps({"value": "completed first tool"})

        namespace["execute_tool"] = delayed_tool
        verdict, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        tools = [span for span in tracer.spans if span.span_type == "TOOL"]
        self.assertEqual([span.name for span in tools], ["one"])
        self.assertEqual(tools[0].outputs["result"]["value"], "completed first tool")
        self.assertEqual(verdict.model_dump()["tool_calls"], 1)
        self.assertEqual(verdict.model_dump()["risk_level"], "inconclusive")
        self.assertEqual(trace_id, tools[0].trace_id)

    def test_trace_captures_full_tool_results_and_own_root_id(self):
        namespace, tracer = investigation_namespace([
            message("Check releases and activity.", ("get_release_history", "get_commit_trend")), message(FINAL)
        ])
        verdict, trace_id = namespace["investigate_repo"]("org/repo", "test priority")
        self.assertEqual(trace_id, tracer.spans[0].trace_id)
        self.assertEqual(tracer.spans[0].inputs["run_id"], "test-run")
        tools = [s for s in tracer.spans if s.span_type == "TOOL"]
        self.assertEqual(len(tools), 2)
        self.assertEqual(len(tools[0].outputs["result"]["value"]), 4000)
        self.assertEqual(verdict.model_dump()["tool_calls"], 2)
        self.assertTrue(all(s.trace_id == trace_id for s in tracer.spans))

    def test_structured_retry_is_a_model_span(self):
        namespace, tracer = investigation_namespace([
            message(names=("get_repo_metrics", "get_commit_trend")), message("invalid JSON"), message(FINAL)
        ])
        namespace["investigate_repo"]("org/repo", "priority")
        phases = [s.attributes["phase"] for s in tracer.spans if s.span_type == "CHAT_MODEL"]
        self.assertEqual(phases, ["decide", "decide", "structured_retry"])

    def test_budget_finalization_is_traced_and_unexecuted_tools_are_not_claimed(self):
        namespace, tracer = investigation_namespace([
            message(names=("one", "two", "not_executed")), message(FINAL)
        ], budget=2)
        namespace["investigate_repo"]("org/repo", "priority")
        self.assertEqual([s.name for s in tracer.spans if s.span_type == "TOOL"], ["one", "two"])
        self.assertIn("budget_finalize", [s.attributes.get("phase") for s in tracer.spans])

    def test_model_error_still_produces_inconclusive_output_on_the_owning_trace(self):
        namespace, tracer = investigation_namespace([RuntimeError("endpoint unavailable")])
        verdict, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        self.assertEqual(verdict.model_dump()["risk_level"], "inconclusive")
        self.assertEqual(tracer.spans[0].status, "ERROR")
        self.assertEqual(tracer.spans[0].outputs["repo_id"], "org/repo")
        self.assertEqual(trace_id, tracer.spans[0].trace_id)

    def test_tool_error_is_recorded_with_inputs_and_error_status(self):
        namespace, tracer = investigation_namespace([message(names=("one", "two")), message(FINAL)])
        namespace["execute_tool"] = lambda *args: (_ for _ in ()).throw(ValueError("tool unavailable"))
        namespace["investigate_repo"]("org/repo", "priority")
        tools = [s for s in tracer.spans if s.span_type == "TOOL"]
        self.assertTrue(all(s.status == "ERROR" and "error" in s.outputs["result"] for s in tools))
        self.assertEqual(tools[0].inputs["repo"], "org/repo")

    def test_two_investigations_have_distinct_trace_ids(self):
        namespace, tracer = investigation_namespace([
            message(names=("one", "two")), message(FINAL), message(names=("one", "two")), message(FINAL)
        ])
        first = namespace["investigate_repo"]("org/repo", "first")[1]
        second = namespace["investigate_repo"]("org/repo", "second")[1]
        self.assertNotEqual(first, second)


class AppTraceTests(unittest.TestCase):
    def payload(self):
        namespace, tracer = investigation_namespace([
            message("Compare measured activity.", ("get_repo_metrics", "get_commit_trend")), message(FINAL)
        ])
        _, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        trace = exported_trace(tracer, trace_id)
        return trace, steps.trace_to_steps(trace, repo_id="org/repo", run_id="test-run", host="https://workspace.example")

    def test_steps_are_ordered_with_complete_evidence_and_public_summaries(self):
        trace, payload = self.payload()
        self.assertEqual([s["order"] for s in payload["steps"]], [1, 2, 3, 4])
        self.assertEqual([s["kind"] for s in payload["steps"]], ["decision", "tool", "tool", "decision"])
        self.assertEqual(payload["steps"][1]["reasoning"], "Compare measured activity.")
        self.assertEqual(len(payload["steps"][1]["outputs"]["value"]), 4000)
        self.assertEqual(payload["explanation"], "Measured activity is stable.")
        self.assertNotIn("HIDDEN_REASONING_SENTINEL", json.dumps(payload))
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", json.dumps(payload))

    def test_missing_public_summary_is_explicit_not_invented(self):
        namespace, tracer = investigation_namespace([message(names=("one", "two")), message(FINAL)])
        _, trace_id = namespace["investigate_repo"]("org/repo", "priority")
        payload = steps.trace_to_steps(exported_trace(tracer, trace_id), repo_id="org/repo", run_id="test-run")
        tool = next(s for s in payload["steps"] if s["kind"] == "tool")
        self.assertIsNone(tool["reasoning"])
        self.assertFalse(tool["reasoning_available"])

    def test_trace_from_another_repo_or_run_is_rejected(self):
        trace, _ = self.payload()
        with self.assertRaises(ValueError):
            steps.trace_to_steps(trace, repo_id="wrong/repo", run_id="test-run")
        with self.assertRaises(ValueError):
            steps.trace_to_steps(trace, repo_id="org/repo", run_id="wrong-run")

    def test_finding_lookup_is_bound_and_returns_saved_payload(self):
        _, payload = self.payload()
        captured = []
        row = NS(repo_id="org/repo", run_id="test-run", trace_id=payload["trace_id"], payload=json.dumps(payload))
        spark = NS(sql=lambda q, args: (captured.append((q, args)) or NS(first=lambda: row)))
        result = steps.get_finding_trace(spark, "org/repo", "test-run")
        self.assertTrue(result["found"])
        self.assertEqual(result["steps"], payload["steps"])
        self.assertEqual(captured[0][1], {"repo_id": "org/repo", "run_id": "test-run"})
        self.assertNotIn("org/repo", captured[0][0])

    def test_unknown_finding_and_missing_export_are_distinct(self):
        spark = NS(sql=lambda *a, **kw: NS(first=lambda: None))
        self.assertFalse(steps.get_finding_trace(spark, "missing/repo")["found"])
        row = NS(repo_id="org/repo", run_id="old-run", trace_id="old-trace", payload=None)
        spark.sql = lambda *a, **kw: NS(first=lambda: row)
        result = steps.get_finding_trace(spark, "org/repo")
        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "not_ready")

    def test_mismatched_saved_payload_is_rejected(self):
        _, payload = self.payload()
        row = NS(repo_id="org/repo", run_id="other-run", trace_id=payload["trace_id"], payload=json.dumps(payload))
        with self.assertRaises(ValueError):
            steps.get_finding_trace(NS(sql=lambda *a, **kw: NS(first=lambda: row)), "org/repo")


if __name__ == "__main__":
    unittest.main()
