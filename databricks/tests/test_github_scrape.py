"""Offline tests: python3 -m unittest discover -s databricks/tests -v."""

import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "src/ingest/scrape_github_repos.py"
SPEC = importlib.util.spec_from_file_location("github_scrape", SOURCE)
scrape = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scrape)
AS_OF = datetime(2026, 11, 7, 20, tzinfo=timezone.utc)


def repo_payload(repo_id="psf/requests", language="Python"):
    owner, name = repo_id.split("/")
    return {
        "nameWithOwner": repo_id, "name": name, "owner": {"login": owner},
        "primaryLanguage": {"name": language}, "stargazerCount": 1000,
        "isArchived": False, "pushedAt": "2026-11-06T00:00:00Z",
        "latestRelease": {"publishedAt": "2026-10-01T00:00:00Z"},
        "issues": {"totalCount": 7}, "pullRequests": {"totalCount": 3},
        "defaultBranchRef": {"target": {"recent": {"totalCount": 12}, "total": {"totalCount": 32}}},
    }


def records(count):
    expected_languages = {repo: language for language, repos in scrape.REPOS_BY_LANGUAGE.items() for repo in repos}
    return [scrape.normalize_repo(repo_payload(repo, expected_languages[repo]), scrape.iso_utc(AS_OF))
            for repo in scrape.CURATED_REPOS[:count]]


class Response(io.BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(json.dumps(payload).encode())
        self.headers = headers or {}


class LocalFS:
    """Exercise publication and rollback against real temporary directories."""
    def __init__(self, root):
        self.root = Path(root)
        self.fail_copy = False

    def path(self, path):
        return self.root / path.lstrip("/")

    def mkdirs(self, path):
        self.path(path).mkdir(parents=True, exist_ok=True)

    def ls(self, path):
        if not self.path(path).exists():
            raise FileNotFoundError("PATH_NOT_FOUND")
        return list(self.path(path).iterdir())

    def put(self, path, content, overwrite=False):
        target = self.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w" if overwrite else "x") as output:
            output.write(content)
        return True

    def mv(self, source, destination, recurse=False):
        target = self.path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.path(source)), str(target))
        return True

    def cp(self, source, destination, recurse=False):
        if self.fail_copy:
            self.put(destination.rsplit("/", 1)[0] + "/partial.json", "{}")
            raise OSError("Simulated interrupted copy")
        shutil.copy2(self.path(source), self.path(destination))
        return True


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fs = LocalFS(self.temp.name)
        self.root = "/Volumes/hackcamp/raw/github"
        self.fs.put(self.root + "/repos/old_seed.json", '{"mock": true}')

    def dbutils(self, **overrides):
        values = dict(overrides)

        def text(name, default):
            values.setdefault(name, default)

        return SimpleNamespace(
            widgets=SimpleNamespace(text=text, get=values.__getitem__), fs=self.fs,
            secrets=SimpleNamespace(get=lambda scope, key: "not-a-real-token"),
            jobs=SimpleNamespace(taskValues=SimpleNamespace(set=lambda **kwargs: None)),
        )

    def summary(self):
        paths = list(self.fs.path(self.root + "/snapshots").glob("*/summary.json"))
        return json.loads(paths[0].read_text())

    def test_published_snapshot_contains_only_real_repos_and_preserves_previous_input(self):
        with patch.object(scrape, "collect_repos", return_value=(records(50), [], None)), redirect_stdout(io.StringIO()):
            result = scrape.run_notebook(self.dbutils(repo_limit="50"))
        self.assertTrue(result["published"])
        self.assertTrue(result["meets_f1"])
        self.assertEqual(len(self.fs.ls(self.root + "/repos")), 50)
        self.assertFalse(self.fs.path(self.root + "/repos/old_seed.json").exists())
        self.assertTrue(self.fs.path(result["snapshot_path"] + "/previous_repos/old_seed.json").exists())
        self.assertEqual(len(self.fs.ls(result["snapshot_path"] + "/repos")), 50)

    def test_smoke_run_never_changes_active_input(self):
        with patch.object(scrape, "collect_repos", return_value=(records(5), [], None)), redirect_stdout(io.StringIO()):
            result = scrape.run_notebook(self.dbutils(repo_limit="5", minimum_repos="5", publish="false"))
        self.assertFalse(result["published"])
        self.assertFalse(result["meets_f1"])
        self.assertEqual(result["status"], "smoke_passed")
        self.assertEqual(len(self.fs.ls(self.root + "/repos")), 1)

    def test_below_minimum_retains_old_input_and_saves_failure_summary(self):
        failures = [{"repo_id": repo, "reason": "Unavailable"} for repo in scrape.CURATED_REPOS[49:]]
        with patch.object(scrape, "collect_repos", return_value=(records(49), failures, None)), redirect_stdout(io.StringIO()):
            with self.assertRaises(scrape.CollectionError):
                scrape.run_notebook(self.dbutils())
        self.assertEqual(self.summary()["status"], "failed")
        self.assertEqual(self.summary()["successful_count"], 49)
        self.assertEqual(len(self.fs.ls(self.root + "/repos")), 1)

    def test_authentication_failure_after_50_successes_cannot_publish(self):
        fatal = {"reason": "GitHub denied access.", "authentication_failed": True}
        with patch.object(scrape, "collect_repos", return_value=(records(50), [], fatal)), redirect_stdout(io.StringIO()):
            with self.assertRaises(scrape.CollectionError):
                scrape.run_notebook(self.dbutils())
        self.assertFalse(self.summary()["published"])

    def test_missing_secret_has_safe_summary_and_no_active_change(self):
        dbutils = self.dbutils()
        dbutils.secrets.get = lambda *args: (_ for _ in ()).throw(RuntimeError("secret backend detail"))
        with redirect_stdout(io.StringIO()), self.assertRaises(scrape.AuthenticationError):
            scrape.run_notebook(dbutils)
        summary = self.summary()
        self.assertEqual(summary["failed_count"], 100)
        self.assertNotIn("secret backend detail", json.dumps(summary))
        self.assertEqual(len(self.fs.ls(self.root + "/repos")), 1)

    def test_volume_permission_failure_stops_before_collecting_or_publishing(self):
        dbutils = self.dbutils()
        with patch.object(self.fs, "mkdirs", side_effect=PermissionError("USE CATALOG denied")), \
                patch.object(scrape, "collect_repos") as collect:
            with self.assertRaisesRegex(scrape.CollectionError, "run-as account has USE CATALOG"):
                scrape.run_notebook(dbutils)
        collect.assert_not_called()
        self.assertTrue(self.fs.path(self.root + "/repos/old_seed.json").exists())

    def test_publish_copy_failure_restores_previous_input(self):
        self.fs.fail_copy = True
        with patch.object(scrape, "collect_repos", return_value=(records(50), [], None)), redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                scrape.run_notebook(self.dbutils(repo_limit="50"))
        self.assertTrue(self.fs.path(self.root + "/repos/old_seed.json").exists())
        self.assertEqual(len(self.fs.ls(self.root + "/repos")), 1)
        self.assertFalse(self.summary()["published"])


class CollectionTests(unittest.TestCase):
    def test_curated_list_is_unique_balanced_and_smoke_test_covers_languages(self):
        self.assertEqual(len(scrape.CURATED_REPOS), 100)
        self.assertEqual(len({r.lower() for r in scrape.CURATED_REPOS}), 100)
        self.assertEqual(len({r["payload"]["language"] for r in records(5)}), 5)

    def test_normalization_uses_real_counts_and_keeps_uncollected_metrics_null(self):
        record = scrape.normalize_repo(repo_payload(), scrape.iso_utc(AS_OF))
        self.assertEqual(record["payload"]["commits_prev_90d"], 20)
        self.assertEqual(record["payload"]["open_issues"], 7)
        for key in ("contributors", "dependents", "maintainer_reply_rate", "top_contributor_share"):
            self.assertIsNone(record["payload"][key])
        repo = repo_payload()
        repo.update(defaultBranchRef=None, latestRelease=None)
        missing = scrape.normalize_repo(repo, scrape.iso_utc(AS_OF))["payload"]
        self.assertIsNone(missing["commits_90d"])
        self.assertIsNone(missing["last_release_at"])

    def test_partial_graphql_error_does_not_discard_good_siblings_or_accept_incomplete_repo(self):
        def fetch(*args):
            return {"data": {"r0": repo_payload(), "r1": repo_payload("pallets/flask")},
                    "errors": [{"path": ["r1", "issues"], "type": "NOT_FOUND"}]}
        found, failures, fatal = scrape.collect_repos(["psf/requests", "pallets/flask"], "token", AS_OF, fetch=fetch)
        self.assertEqual([r["repo_id"] for r in found], ["psf/requests"])
        self.assertEqual(failures[0]["repo_id"], "pallets/flask")
        self.assertIsNone(fatal)

    def test_renamed_duplicates_count_only_once(self):
        def fetch(*args):
            return {"data": {"r0": repo_payload(), "r1": repo_payload()}}
        found, failures, _ = scrape.collect_repos(["psf/requests", "old/requests"], "token", AS_OF, fetch=fetch)
        self.assertEqual(len(found), 1)
        self.assertEqual(len(failures), 1)

    def test_transport_retries_429_then_sends_one_fixed_time_window(self):
        calls, sleeps = [], []

        def opener(request, timeout):
            calls.append(json.loads(request.data))
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "Rate limited", {"Retry-After": "2"}, None)
            return Response({"data": {"r0": repo_payload()}})

        scrape.fetch_batch(["psf/requests"], "private-token", AS_OF, opener=opener, sleep=sleeps.append)
        self.assertEqual(sleeps, [2])
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0]["variables"]["asOf"], "2026-11-07T20:00:00Z")
        self.assertIn("until: $asOf", calls[0]["query"])
        self.assertNotIn("private-token", json.dumps(calls))

    def test_authentication_error_is_not_retried_or_leaked(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "private-token", {}, None)
        with self.assertRaises(scrape.AuthenticationError) as error:
            scrape.fetch_batch(["psf/requests"], "private-token", AS_OF, opener=opener, sleep=lambda _: self.fail("Retried auth"))
        self.assertNotIn("private-token", str(error.exception))

    def test_long_rate_limit_stops_immediately(self):
        with self.assertRaises(scrape.CollectionError):
            scrape.retry_delay({"Retry-After": "120"}, 0)

    def test_transient_failure_has_at_most_three_attempts(self):
        calls, sleeps = [], []

        def opener(request, timeout):
            calls.append(request)
            raise urllib.error.URLError("temporary failure")

        with self.assertRaises(scrape.CollectionError):
            scrape.fetch_batch(["psf/requests"], "token", AS_OF, opener=opener, sleep=sleeps.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1, 2])


if __name__ == "__main__":
    unittest.main()
