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
        "description": f"{name} is a popular open-source project",
        "primaryLanguage": {"name": language}, "stargazerCount": 1000,
        "isArchived": False, "pushedAt": "2026-11-06T00:00:00Z",
        "latestRelease": {"publishedAt": "2026-10-01T00:00:00Z"},
        "repositoryTopics": {"nodes": [{"topic": {"name": "http"}}, {"topic": {"name": language.lower()}}]},
        "issues": {"totalCount": 7}, "pullRequests": {"totalCount": 3},
        "defaultBranchRef": {"target": {"recent": {"totalCount": 12}, "total": {"totalCount": 32}}},
    }


def records(count):
    expected_languages = {repo: language for language, repos in scrape.REPOS_BY_LANGUAGE.items() for repo in repos}
    return [scrape.normalize_repo(repo_payload(repo, expected_languages[repo]), scrape.iso_utc(AS_OF))
            for repo in scrape.CURATED_REPOS[:count]]


def expanded_records(count):
    languages = list(scrape.REPOS_BY_LANGUAGE)
    return [scrape.normalize_repo(repo_payload(f"public/repo-{i}", languages[i % 5]), scrape.iso_utc(AS_OF))
            for i in range(count)]


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
        # Offline notebook tests do not hit the advisories REST pass.
        self.enrich_patch = patch.object(
            scrape, "enrich_advisories", side_effect=lambda records, *a, **k: records
        )
        self.enrich_patch.start()
        self.addCleanup(self.enrich_patch.stop)

    def dbutils(self, **overrides):
        # Existing small-corpus modes remain supported explicitly.
        values = {"repo_limit": "100", "minimum_repos": "50", "fetch_advisories": "false", **overrides}

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
        self.assertFalse(result["meets_f1"])  # Legacy mode does not meet the new 1,000-repo requirement.
        active = self.fs.ls(self.root + "/repos")
        self.assertEqual(len(active), 1)
        self.assertEqual(len(active[0].read_text().splitlines()), 50)
        self.assertFalse(self.fs.path(self.root + "/repos/old_seed.json").exists())
        self.assertTrue(self.fs.path(result["snapshot_path"] + "/previous_repos/old_seed.json").exists())
        self.assertEqual(len(self.fs.ls(result["snapshot_path"] + "/repos")), 1)

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
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["attempted_count"], 0)
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

    def test_thousand_repo_snapshot_publishes_ten_compatible_json_lines_files(self):
        collected = expanded_records(1000)
        candidates = [f"public/repo-{i}" for i in range(1200)]

        def collect(ids, token, as_of, batch_size, *, target_count, attempted_repo_ids):
            self.assertEqual(target_count, 1000)
            attempted_repo_ids.extend(ids[:1000])
            return collected, [], None

        with patch.object(scrape, "discover_repo_ids", return_value=candidates), \
                patch.object(scrape, "collect_repos", side_effect=collect), redirect_stdout(io.StringIO()):
            result = scrape.run_notebook(self.dbutils(repo_limit="1000", minimum_repos="1000"))
        self.assertTrue(result["published"])
        self.assertEqual(result["successful_count"], 1000)
        self.assertTrue(result["meets_f1"])
        self.assertEqual(result["attempted_count"], 1000)
        self.assertEqual(result["candidate_count"], 1200)
        files = self.fs.ls(self.root + "/repos")
        self.assertEqual(len(files), 10)
        rows = [json.loads(line) for path in files for line in path.read_text().splitlines()]
        self.assertEqual(len(rows), 1000)
        self.assertEqual(len({row["repo_id"].lower() for row in rows}), 1000)
        self.assertTrue(all(row["payload"]["source"] == "github_graphql" for row in rows))
        self.assertEqual(sum(file["records"] for file in result["files"]), 1000)

    def test_expanded_run_never_publishes_a_partial_thousand_repo_result(self):
        with patch.object(scrape, "discover_repo_ids", return_value=[f"public/repo-{i}" for i in range(1200)]), \
                patch.object(scrape, "collect_repos", return_value=(expanded_records(999), [], None)), \
                redirect_stdout(io.StringIO()), self.assertRaises(scrape.CollectionError):
            scrape.run_notebook(self.dbutils(repo_limit="1000", minimum_repos="1000"))
        self.assertFalse(self.summary()["published"])
        self.assertTrue(self.fs.path(self.root + "/repos/old_seed.json").exists())

    def test_expanded_publication_cannot_lower_the_target_gate(self):
        with self.assertRaisesRegex(ValueError, "minimum_repos >= 1000"):
            scrape.run_notebook(self.dbutils(repo_limit="1000", minimum_repos="900"))


class CollectionTests(unittest.TestCase):
    def test_discovery_is_paginated_unique_interleaved_and_preserves_curated_controls(self):
        calls, pauses = [], []

        def search(language, token, cursor):
            page = int(cursor or 0)
            calls.append((language, cursor))
            names = [scrape.CURATED_REPOS[0]] + [f"{language.lower()}/repo-{page * 100 + i}" for i in range(100)]
            return names, str(page + 1)

        found = scrape.discover_repo_ids(1000, "token", search=search, sleep=pauses.append)
        self.assertEqual(found[:100], scrape.CURATED_REPOS)
        self.assertEqual(len(found), 1200)
        self.assertEqual(len({repo.lower() for repo in found}), 1200)
        self.assertEqual({repo.split('/')[0] for repo in found[100:105]}, {lang.lower() for lang in scrape.REPOS_BY_LANGUAGE})
        self.assertTrue(any(cursor is not None for _, cursor in calls))
        self.assertEqual(len(pauses), len(calls) - 1)

    def test_discovery_exhaustion_fails_without_an_infinite_search_loop(self):
        calls = []

        def search(language, token, cursor):
            calls.append(language)
            return [], None

        with self.assertRaises(scrape.CollectionError):
            scrape.discover_repo_ids(1000, "token", search=search, sleep=lambda _: None)
        self.assertEqual(len(calls), 5)

    def test_small_smoke_run_does_not_search(self):
        found = scrape.discover_repo_ids(5, "token", search=lambda *a: self.fail("Unexpected search"))
        self.assertEqual(found, scrape.CURATED_REPOS[:5])

    def test_collection_refills_redirect_duplicates_and_stops_at_unique_target(self):
        attempts = []

        def fetch(ids, token, as_of):
            return {"data": {f"r{i}": repo_payload("public/repo-0" if repo == "old/name" else repo)
                             for i, repo in enumerate(ids)}}

        found, failures, fatal = scrape.collect_repos(
            ["public/repo-0", "old/name", "public/repo-1", "public/repo-2", "public/not-needed"],
            "token", AS_OF, batch_size=2, fetch=fetch, target_count=3, attempted_repo_ids=attempts,
        )
        self.assertEqual(len(found), 3)
        self.assertEqual(len({row["repo_id"] for row in found}), 3)
        self.assertEqual(len(failures), 1)
        self.assertIsNone(fatal)
        self.assertNotIn("public/not-needed", attempts)

    def test_curated_list_is_unique_balanced_and_smoke_test_covers_languages(self):
        self.assertEqual(len(scrape.CURATED_REPOS), 100)
        self.assertEqual(len({r.lower() for r in scrape.CURATED_REPOS}), 100)
        self.assertEqual(len({r["payload"]["language"] for r in records(5)}), 5)

    def test_normalization_uses_real_counts_and_keeps_uncollected_metrics_null(self):
        record = scrape.normalize_repo(repo_payload(), scrape.iso_utc(AS_OF))
        self.assertEqual(record["payload"]["commits_prev_90d"], 20)
        self.assertEqual(record["payload"]["open_issues"], 7)
        self.assertEqual(record["payload"]["description"], "requests is a popular open-source project")
        self.assertEqual(record["payload"]["topics"], ["http", "python"])
        self.assertEqual(record["payload"]["advisory_fetch_status"], "not_fetched")
        self.assertEqual(record["payload"]["advisories"], [])
        for key in ("contributors", "dependents", "maintainer_reply_rate", "top_contributor_share"):
            self.assertIsNone(record["payload"][key])
        repo = repo_payload()
        repo.update(defaultBranchRef=None, latestRelease=None)
        missing = scrape.normalize_repo(repo, scrape.iso_utc(AS_OF))["payload"]
        self.assertIsNone(missing["commits_90d"])
        self.assertIsNone(missing["last_release_at"])

    def test_advisory_pass_keeps_ghsa_fields_and_marks_failures(self):
        advisory = {
            "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
            "cve_id": "CVE-2021-23337",
            "severity": "high",
            "cvss": {"score": 7.2},
            "cwes": [{"cwe_id": "CWE-94"}, {"cwe_id": "CWE-1321"}],
            "summary": "Command injection in lodash template",
            "published_at": "2021-02-15T00:00:00Z",
        }
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if "lodash" in request.full_url:
                return Response([advisory])
            raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)

        records = [
            scrape.normalize_repo(repo_payload("lodash/lodash", "JavaScript"), scrape.iso_utc(AS_OF)),
            scrape.normalize_repo(repo_payload("psf/requests", "Python"), scrape.iso_utc(AS_OF)),
        ]
        scrape.enrich_advisories(records, "token", opener=opener, sleep=lambda _: None, pause_sec=0)
        self.assertEqual(records[0]["payload"]["advisory_fetch_status"], "ok")
        self.assertEqual(records[0]["payload"]["advisories"][0]["cwes"], ["CWE-94", "CWE-1321"])
        self.assertEqual(records[0]["payload"]["advisories"][0]["cvss_score"], 7.2)
        self.assertEqual(records[1]["payload"]["advisory_fetch_status"], "failed")
        self.assertEqual(records[1]["payload"]["advisories"], [])
        self.assertTrue(all("/security-advisories" in url for url in calls))

    def test_graphql_query_requests_description_and_topics(self):
        query = scrape.build_query(["psf/requests"])
        self.assertIn("description", query)
        self.assertIn("repositoryTopics", query)

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
