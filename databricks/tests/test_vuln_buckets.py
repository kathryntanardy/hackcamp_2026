"""Unit tests for F15 CWE → vulnerability-bucket mapping."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vuln_buckets",
    ROOT / "src/pipelines/repo_health/transformations/vuln_buckets.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class VulnBucketTests(unittest.TestCase):
    def test_lodash_prototype_pollution_and_code_execution(self):
        self.assertEqual(mod.bucket_for_cwes(["CWE-94"]), mod.BUCKET_CODE_EXECUTION)
        self.assertEqual(mod.bucket_for_cwes(["CWE-1321"]), mod.BUCKET_PROTOTYPE_POLLUTION)

    def test_normalize_cwe_variants(self):
        self.assertEqual(mod.normalize_cwe_id("cwe-89"), "89")
        self.assertEqual(mod.normalize_cwe_id("CWE89"), "89")
        self.assertEqual(mod.normalize_cwe_id("89"), "89")

    def test_unmapped_is_other(self):
        self.assertEqual(mod.bucket_for_cwes(["CWE-9999"]), mod.BUCKET_OTHER)
        self.assertEqual(mod.bucket_for_cwes([]), mod.BUCKET_OTHER)

    def test_repo_no_advisories_vs_other(self):
        self.assertEqual(
            mod.repo_vuln_buckets([], advisory_fetch_status="ok", advisory_count=0),
            [mod.BUCKET_NONE],
        )
        self.assertEqual(
            mod.repo_vuln_buckets(
                [mod.BUCKET_OTHER], advisory_fetch_status="ok", advisory_count=1
            ),
            [mod.BUCKET_OTHER],
        )
        self.assertEqual(
            mod.repo_vuln_buckets([], advisory_fetch_status="failed", advisory_count=0),
            [],
        )

    def test_heuristic_category(self):
        self.assertEqual(
            mod.heuristic_category("A React UI toolkit", ["frontend"]),
            "Front-end",
        )
        self.assertEqual(mod.heuristic_category("obscure thing", []), "other")


if __name__ == "__main__":
    unittest.main()
