# Ticket #3 deployment and run check

Latest result: **full collection and publication passed: 100 real repos,
0 failures**, covering all five intended languages (plus Kotlin and TypeScript
reported by GitHub). The active Volume contains 100 JSON files and the previous
input was archived. The full job completed successfully in about 2.5 minutes.

[Successful full run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/883270202697096)

- Snapshot: `/Volumes/hackcamp/raw/github/snapshots/20261107T210629_7224773d/repos/`
- Summary: `/Volumes/hackcamp/raw/github/snapshots/20261107T210629_7224773d/summary.json`
- Active pipeline input: `/Volumes/hackcamp/raw/github/repos/`
- Summary flags: `status=published`, `published=true`, `meets_f1=true` (the
  scraper's 50-repo/five-language collection gate).
- The downstream pipeline was not refreshed during this scraping test. Its
  handoff and nullable-data/scoring changes remain in tickets #4–#6.

The
[five-repo smoke test](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/907010974743154)
passed with 5 successes, 0 failures, all five intended languages and
`published=false`. Its summary is saved at
`/Volumes/hackcamp/raw/github/snapshots/20261107T210524_1892ae74/summary.json`.
Earlier permission failures below are retained as history; Volume access is
now resolved.

Checked November 7, 2026, using the `school` Databricks CLI profile.

- Workspace authentication succeeded as `kathrieynchen@gmail.com`.
- `databricks bundle validate -t dev --profile school` passed.
- The `hackcamp/github_token` secret key exists; its value was not displayed.
- Bundle deployment created the scraping job and uploaded its notebook. Deployment
  was partial: creation of `repo_health` failed because the signed-in principal
  lacks `USE CATALOG` on `hackcamp`.
- The five-repo smoke run (`publish=false`) failed at creation of its snapshot
  directory with the same catalog permission error, before GitHub collection or
  modification of active input. No live snapshot was published. The run terminated;
  a cancellation request found it already in a failed terminal state.

[Scraping job](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489)
· [Smoke run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/875708654549227)

## Required access

Use the account that owns the existing catalog, or ask that owner to grant the
scraping job's run-as account `USE CATALOG` on `hackcamp`, `USE SCHEMA` on
`hackcamp.raw`, and `READ VOLUME` / `WRITE VOLUME` on `hackcamp.raw.github`.
Deploying and operating the downstream pipeline also requires its own catalog,
schema and table permissions; Volume access alone does not establish those.
No permissions have been changed by this implementation.

Once access is fixed, redeploy the latest notebook, rerun the five-repo smoke test,
then run the default 100-repo collection with the 50-repo publication gate.
Follow the README for the manual pipeline handoff. Keep ticket #3 open until a
real workspace collection meets that gate.

## Rerun after reported access fix

The latest notebook was uploaded, but bundle deployment still received
`USE CATALOG` denied for `kathrieynchen@gmail.com` on `hackcamp`. The smoke test
was rerun with five repos and `publish=false` and terminated with the same
Volume-access blocker. It made no GitHub requests or active-input changes.

[Second smoke run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489/runs/334371024416408)

The grant must apply to this exact account in workspace
`https://dbc-a0a04386-0e40.cloud.databricks.com`; the earlier reported fix has
not yet made that account able to use the existing catalog.
