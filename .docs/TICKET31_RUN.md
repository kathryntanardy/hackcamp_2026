# Ticket #31 — description, topics, security advisories (F14/F15)

## Implementation

- GraphQL metrics query now requests `description` and `repositoryTopics`.
- Separate REST pass: `GET /repos/{owner}/{repo}/security-advisories` per repo
  with bounded retries; payload fields `advisories[]` + `advisory_fetch_status`
  (`ok` | `failed` | `not_fetched`).
- Silver:
  - `hackcamp.silver.repos` — adds `description`, `topics`, `advisory_fetch_status`
  - `hackcamp.silver.repo_advisories` — one row per GHSA (`ghsa_id`, `cve_id`,
    `severity`, `cvss_score`, `cwes`, `summary`, `published_at`)
- Job param `fetch_advisories` (default `true`); scrape timeout raised to 2h.

## Verify locally

```sh
python -m unittest databricks.tests.test_github_scrape -v
```

## Databricks (profile `school`)

Smoke (does not replace active Volume input):

```sh
cd databricks
databricks bundle deploy -t dev --profile school
databricks bundle run github_scrape -t dev --profile school \
  --params repo_limit=5,minimum_repos=5,publish=false,fetch_advisories=true
```

Full refresh after a successful **publish** of 1,000 repos:

```sh
databricks bundle run github_scrape -t dev --profile school \
  --params repo_limit=1000,minimum_repos=1000,publish=true,fetch_advisories=true
databricks bundle run repo_health -t dev --profile school --full-refresh-all
```

Done check:

```sql
SELECT count(*) AS repos_with_description
FROM hackcamp.silver.repos
WHERE description IS NOT NULL AND length(description) > 0;

SELECT repo_id, ghsa_id, cwes, severity
FROM hackcamp.silver.repo_advisories
WHERE repo_id = 'lodash/lodash';
-- Expect CWE-94 / CWE-1321 among lodash advisories when fetch succeeded.
```

## Run log (2026-11-07 / `school`)

| Step | Result |
|------|--------|
| Smoke `repo_limit=5`, `publish=false`, `fetch_advisories=true` | SUCCESS (`412990853283866`) |
| Full scrape `1000` + publish + advisories | SUCCESS (~13m, `519008123071270`) |
| `repo_health --full-refresh-all` | COMPLETED (`67060020-6042-454e-8903-d2a7ececd502`) |

Silver verify:

| Metric | Value |
|--------|-------|
| `silver.repos` | 1000 |
| with description | 996 |
| with topics | 862 |
| `advisory_fetch_status=ok` | 1000 |
| failed / not_fetched | 0 / 0 |
| `silver.repo_advisories` rows | 3682 |

`lodash/lodash` advisories include **CWE-94** (`GHSA-r5fr-rjxr-66jc`) and **CWE-1321** (`GHSA-f23m-r3pf-42rh`, `GHSA-xxjr-mmjv-4gpg`).
