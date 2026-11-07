# Verified 1,000-repository snapshot

Verified on 2026-11-07. The PRD F1 target is now 1,000 unique real GitHub repositories. The existing Databricks workspace, GitHub secret, job and ingestion pipeline were reused; no additional service or Python dependency was needed.

## Collection

- [Successful full scrape](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/1062705753595551): job `185379822037489`, run `1062705753595551`.
- Snapshot: `/Volumes/hackcamp/raw/github/snapshots/20261107T222419_a3811abc`.
- Summary: `snapshots/20261107T222419_a3811abc/summary.json` under the same Volume root.
- Collection window: `2026-11-07T22:24:19.647217Z` to `2026-11-07T22:29:48.697643Z` (5 minutes 29 seconds; whole job approximately 6 minutes including setup/publication).
- Candidate pool: 1,200 IDs. Attempted: 1,001. Published: 1,000 unique canonical IDs in 10 JSON Lines files.
- One rejected candidate, `react/react`, returned an invalid or duplicate canonical payload. A spare candidate replaced it; the publication target remained 1,000.
- All five intended languages are present: Python, JavaScript, Go, Rust and Java. Curated repositories also include TypeScript and Kotlin.
- Summary reports `published=true`, `meets_f1=true`, `source=github_graphql`.
- Previous active input is retained in this snapshot's `previous_repos/` directory.

The curated controls were retained and expanded through public, non-fork, star-ranked language searches. This is a bounded sample, not a representative survey of all open-source repositories.

## Verification

The five-repository smoke test passed without changing active input ([run 920135340754890](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/920135340754890)). SQL `read_files` verified that its batched JSON Lines format contained five distinct records.

After the full collection, SQL `read_files` against `/Volumes/hackcamp/raw/github/repos/` verified 1,000 records, 1,000 case-insensitive distinct repo IDs, and only the `github_graphql` source.

The existing table-owning pipeline `23564139-0ea8-435b-9a96-dbae9699ce92` completed a full refresh, update `7d0a4dbe-828a-494e-a8bf-b9e8a143fdc3`. No agent investigation batch was launched.

| Table | Rows | Distinct repo IDs (case-insensitive) |
| --- | ---: | ---: |
| `hackcamp.bronze.github_repos_raw` | 1,000 | 1,000 |
| `hackcamp.silver.repos` | 1,000 | 1,000 |
| `hackcamp.gold.repo_health` | 1,000 | 1,000 |

Verification SQL statement: `01f1dafa-f209-19a0-a526-01c5d2b7dbaf` on warehouse `61553be907916cd7`.

Local validation: all 42 Databricks tests passed, bundle validation/deployment succeeded, and `git diff --check` passed. The deployed defaults are `repo_limit=1000`, `minimum_repos=1000`, `batch_size=10`. Failed expanded runs retain the previous active dataset rather than publishing fewer than 1,000 repositories.

This verifies scraping and ingestion. It does not establish frontend rendering performance or run 1,000 model investigations; the agent budget remains independent of corpus size.
