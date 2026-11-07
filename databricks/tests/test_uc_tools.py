"""Offline safety checks; SQL behavior is tested by the uc_tools Databricks job."""

import ast
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_uc_tools", ROOT / "src/setup/verify_uc_tools.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class ToolSafetyTests(unittest.TestCase):
    def test_sql_splitter_preserves_semicolons_inside_comments_and_escaped_strings(self):
        source = "-- comment; not a delimiter\nSELECT 'it''s; quoted'; SELECT 2;"
        statements = list(verify.sql_statements(source))
        self.assertEqual(len(statements), 2)
        self.assertIn("'it''s; quoted'", statements[0])
        self.assertEqual(statements[1], "SELECT 2")

    def test_real_definitions_have_exactly_the_six_expected_public_signatures(self):
        statements = list(verify.sql_statements((ROOT / "src/setup/create_uc_tools.sql").read_text()))
        self.assertEqual(len(statements), 6)
        import re
        names = {re.search(r"CREATE OR REPLACE FUNCTION hackcamp.tools.(\w+)\(", s).group(1) for s in statements}
        self.assertEqual(names, set(verify.ALL_TOOLS))

    def test_repository_argument_is_bound_even_when_it_contains_sql(self):
        calls = []

        def sql(statement, args):
            calls.append((statement, args))
            return SimpleNamespace(first=lambda: SimpleNamespace(result=json.dumps({"found": False})))

        malicious = "repo/x'); DROP TABLE anything; --"
        result = verify.call_tool(SimpleNamespace(sql=sql), "ticket6_", "get_commit_trend", malicious, weeks=12)
        self.assertFalse(result["found"])
        self.assertNotIn(malicious, calls[0][0])
        self.assertEqual(calls[0][1], {"repo": malicious, "weeks": 12})

    def test_sql_null_is_a_contract_failure_not_an_empty_success(self):
        spark = SimpleNamespace(sql=lambda *a, **kw: SimpleNamespace(first=lambda: SimpleNamespace(result=None)))
        with self.assertRaisesRegex(AssertionError, "SQL NULL"):
            verify.call_tool(spark, "ticket6_", "get_repo_metrics", "missing/repo")

    def test_disabled_contributor_tool_is_not_available_to_the_model_or_dispatcher(self):
        source = (ROOT / "src/agent/run_investigation.py").read_text()
        tree = ast.parse(source)
        selected = [node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id in ("UC_TOOLS", "LIVE_TOOLS", "OPENAI_TOOLS") for t in node.targets)]
        namespace = {}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "agent_tool_declarations", "exec"), namespace)
        self.assertNotIn("get_contributor_concentration", namespace["UC_TOOLS"])
        offered = {tool["function"]["name"] for tool in namespace["OPENAI_TOOLS"]}
        self.assertNotIn("get_contributor_concentration", offered)
        self.assertTrue(set(verify.REQUIRED_TOOLS) <= offered)


if __name__ == "__main__":
    unittest.main()
