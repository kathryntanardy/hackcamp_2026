"""Unit tests for F12 alternative sanitization (no remote Vector Search)."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "find_alternatives", ROOT / "src/agent/find_alternatives.py"
)
mod = importlib.util.module_from_spec(spec)
# Avoid importing WorkspaceClient side effects at module level beyond the import.
spec.loader.exec_module(mod)


class SanitizeAlternativesTest(unittest.TestCase):
    def test_drops_mangled_empty(self):
        self.assertEqual(mod.sanitize_alternatives(["[]"]), [])
        self.assertEqual(mod.sanitize_alternatives("[]"), [])
        self.assertEqual(mod.sanitize_alternatives(None), [])

    def test_keeps_org_repo(self):
        self.assertEqual(
            mod.sanitize_alternatives(["vuejs/core", "facebook/react", "not-a-repo"]),
            ["vuejs/core", "facebook/react"],
        )

    def test_dedupes_and_caps_at_three(self):
        self.assertEqual(
            mod.sanitize_alternatives(
                ["a/b", "A/B", "c/d", "e/f", "g/h"]
            ),
            ["a/b", "c/d", "e/f"],
        )


if __name__ == "__main__":
    unittest.main()
