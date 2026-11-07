"""Unit tests for the ignored / deprecated parking rules."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "deprecated_repos",
    ROOT / "src/pipelines/repo_health/transformations/deprecated_repos.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class DeprecatedReposTests(unittest.TestCase):
    def test_archived_is_always_ignored(self):
        self.assertTrue(mod.is_ignored("someone/random", True))

    def test_known_deprecated_is_ignored_even_if_not_archived(self):
        self.assertTrue(mod.is_ignored("moment/moment", False))
        self.assertTrue(mod.is_ignored("request/request", False))

    def test_living_controls_are_not_ignored(self):
        self.assertFalse(mod.is_ignored("facebook/react", False))
        self.assertFalse(mod.is_ignored("vuejs/vue", False))
        self.assertFalse(mod.is_ignored("kennethreitz/records", False))

    def test_gold_source_parks_ignored_status(self):
        gold = (ROOT / "src/pipelines/repo_health/transformations/03_gold.py").read_text()
        self.assertIn('F.lit("ignored")', gold)
        self.assertIn("KNOWN_DEPRECATED_REPOS", gold)
        self.assertNotIn(
            'F.when(F.col("is_archived"), F.lit("at_risk"))',
            gold,
        )


if __name__ == "__main__":
    unittest.main()
