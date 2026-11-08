# Production investigations: 500 additional repositories

**Status: COMPLETED AND VERIFIED.** The original 500-repository workflow finished
successfully on November 7, 2026, Vancouver time. Its final summary verifies 500
new unique repositories and 500 distinct trace IDs, with no overlap with the
starting findings. Outcomes: 278 at risk, 57 ignored, 81 watchlist, 84 healthy,
and zero inconclusive. Verification timestamp: `2026-11-08T04:25:14.326895+00:00`.

- [Live job run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/1030892989404703/runs/373128971260925).
- Job: `1030892989404703`; run / coverage ID: `373128971260925`.
- Target: **500 additional unique eligible repositories**, ten sequential batches
  of 50, using the existing model and eight-tool budget.
- Starting corpus: 1,000 repositories; 12 distinct repositories already have
  production findings; 962 are uninvestigated and not marked ignored in gold.
- With no other changes, successful completion would bring distinct corpus
  investigation coverage to 512. This does not mean all verdicts are correct or
  conclusive; the final summary reports the actual risk/inconclusive counts.

## Original checks at initial handoff (historical)

The trace-table setup and coverage preflight tasks succeeded. The first batch is
running, and its saved selection manifest contains **50 distinct repositories,
zero overlaps with the starting findings, and zero gold-ignored repositories**.
At that initial handoff, the first batch and full 500 had not yet completed.

Every completed batch writes to `hackcamp.agent.findings`,
`hackcamp.agent.trace_steps`, and `hackcamp.agent.runs`; the backend can read those
results immediately. Each subsequent batch excludes all existing findings, so
completed batches are not selected again. The ordinary agent job still supports
revisits and memory by default; coverage mode is opt-in.

## Monitor progress

```sql
SELECT count(*) AS finding_rows,
       count(DISTINCT lower(repo_id)) AS new_repositories,
       count_if(risk_level = 'inconclusive') AS inconclusive
FROM hackcamp.agent.findings
WHERE startswith(run_id, 'coverage-373128971260925-');
```

Results appear after each batch of 50 finishes, rather than after every individual
repository. Open the live job's active batch output to see individual progress.
The remaining batches continue automatically after successful predecessors.

Evidence root:
`/Volumes/hackcamp/raw/github/coverage/373128971260925/`.

- `baseline.json`: target, starting investigated IDs, start time and batch plan.
- `selection_coverage-373128971260925-<application-run-id>.json`: each batch's
  selected repositories, baseline status and priority.
- `summary.json`: produced by the final verifier after all ten batches. A
  successful summary requires 500 unique new repositories, no overlap with the
  starting IDs, distinct trace IDs, and matching saved app trace payloads/tool counts.

Expected runtime is roughly two to three hours based on recent measurements;
rate limits and model latency can extend it. No scheduler was added. The
six-hour job timeout bounds a stalled run. Completed batches remain saved if a
later task fails; use **Repair run** for failed tasks rather than starting a
second full coverage job. An investigation that returns `inconclusive` remains
visible and is included in the outcome counts.

Implementation: `agent_coverage.job.yml`, opt-in `uninvestigated_only` selection in
`run_investigation.py`, and preparation/final verification notebooks. Scraping,
baseline scoring and their schemas are unchanged. Local validation: **82 tests
passed, one Spark-dependent module skipped**; bundle validation/deployment,
compilation and diff checks passed.
