# Remaining production investigation coverage

**Status at handoff: RUNNING, not complete.**

[Live Databricks run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/621511209741818/runs/881668484000697).

The original 500-repository job completed and passed its final verification.
The new preflight, captured at `2026-11-08T05:14:10.412388+00:00`, found:

| Coverage at start | Repositories |
| --- | ---: |
| Corpus | 1,000 |
| Already have findings | 512 |
| Eligible and uninvestigated | **462** |
| Uninvestigated, excluded as gold ignored | 26 |

The continuation targets exactly **462 additional repositories**, in nine batches
of 50 and one final batch of 12. Preflight succeeded and the first batch started.
If the corpus remains unchanged, successful completion will bring distinct
investigation coverage to 974; 26 already-ignored repositories remain excluded.
The baseline snapshot records all 512 prior IDs, and final verification must
prove no overlap with those IDs and reconcile every saved finding-to-trace link.

## Compute retry and deployment

The SQL warehouse still returned a serverless-eligibility error after the limits
change. A direct notebook-only submission successfully started using working job
compute. It reuses the existing trace table, whose setup and population were
verified by the first 500 run, so no SQL warehouse setup task is needed here.
This run has no hourly retry or schedule; the earlier plan to wait for a daily
quota reset was superseded by the successful direct retry.

Only the four coverage-related workspace files were uploaded. A full bundle
deployment was not performed because an unrelated local App resource points to
the missing staged directory `apps/corpus-explorer`. No frontend changes were
modified. The remaining-work configuration is also present in the local bundle
for its next normal deployment.

## Monitor saved progress

```sql
SELECT count(*) AS rows,
       count(DISTINCT lower(repo_id)) AS new_repositories,
       count_if(risk_level='inconclusive') AS inconclusive
FROM hackcamp.agent.findings
WHERE startswith(run_id, 'coverage-881668484000697-');
```

Results are saved after each batch. Individual in-flight verdicts appear in the
active notebook output before the batch is saved. Model classifications are not
verified ground truth; the final summary reports their actual outcome counts.

Evidence root: `/Volumes/hackcamp/raw/github/coverage/881668484000697/`.
`baseline.json` contains the exact starting counts and budgets
`[50,50,50,50,50,50,50,50,50,12]`. Selection manifests record each batch. The final
verification task writes `summary.json`; it has not run at this handoff.

Local checks: **83 tests passed**, one Spark-dependent module skipped, compilation
and diff checks passed. The exact-count preflight has also passed on live
Databricks job compute. Expected runtime is roughly two to three hours; rate
limits and compute availability can change that estimate.
