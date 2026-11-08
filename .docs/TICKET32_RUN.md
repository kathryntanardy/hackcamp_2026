# Ticket #32 — categories + CWE vulnerability buckets (F15)

## Implementation

- CWE → bucket map in `vuln_buckets.py` (10 buckets + Other / unclassified + No GitHub advisories).
- `silver.repo_advisories.vuln_bucket` derived from each advisory's CWE IDs.
- Job `classify_categories` runs `ai_query` over description + topics →
  `hackcamp.silver.repo_categories`.
- Gold adds `category`, `vuln_buckets`, `advisory_count`, `max_severity`,
  `max_cvss`, `cat_x`, `cat_y` (AI label preferred; keyword heuristic fallback).
- API `/api/repos` and `/api/repos/{id}` expose the new gold fields; drawer
  detail includes per-repo advisories with `vuln_bucket`.

## Verify locally

```sh
python -m unittest databricks.tests.test_vuln_buckets -v
# optional (needs local Spark/Java):
pytest databricks/tests/test_gold_score.py -q
pytest backend/tests/test_api.py -q
```

## Databricks (profile `school`)

```sh
cd databricks
databricks bundle deploy -t dev --profile school
# Classify all 1,000 repos (slow; LLM per row). Smoke with LIMIT via notebook if needed.
databricks bundle run classify_categories -t dev --profile school
databricks bundle run repo_health -t dev --profile school --full-refresh-all
```

Done check:

```sql
SELECT category, count(*) FROM hackcamp.gold.repo_health GROUP BY 1 ORDER BY 2 DESC;

SELECT repo_id, category, vuln_buckets, advisory_count, max_severity, max_cvss
FROM hackcamp.gold.repo_health
WHERE repo_id = 'lodash/lodash';
-- Expect Prototype pollution + Code execution among vuln_buckets.

SELECT count(*) AS no_advisories
FROM hackcamp.gold.repo_health
WHERE array_contains(vuln_buckets, 'No GitHub advisories');

SELECT count(*) AS other_unclassified
FROM hackcamp.gold.repo_health
WHERE array_contains(vuln_buckets, 'Other / unclassified');
```

Fallback: if `other` is too high after classify, add a short README excerpt to the scrape (#31 note) and re-run classify.

## Run log (2026-11-07 / `school`)

| Step | Result |
|------|--------|
| `classify_categories` (`ai_query`) | SUCCESS (~90s, `308082001623690`) |
| `repo_health --full-refresh-all` | COMPLETED (`d1d2c51c-4f74-4e69-834f-9fff53057b1b`) |

| Metric | Value |
|--------|-------|
| gold rows / with category | 1000 / 1000 |
| category=`other` | 38 (no README fallback needed) |
| `No GitHub advisories` | 717 |
| `Other / unclassified` | 245 |
| empty `vuln_buckets` | 0 |

Category mix: Back-end 284, Front-end 246, DevOps & infra 199, Machine learning 181, Database 43, other 38, Hardware/embedded 9.

`lodash/lodash`: category Front-end; vuln_buckets **Code execution** + **Prototype pollution**; advisory_count 3; max_severity high; max_cvss 8.1.
