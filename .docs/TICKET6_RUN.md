# Ticket #6 — verified Unity Catalog data tools

Verified November 7, 2026. The implementation is deployed in the existing
Databricks workspace and all verification tasks passed.

[Successful deployment and verification run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/966004980896182/runs/154095681302817)

## Implemented scope

Five active functions in `hackcamp.tools` provide repository metrics, fixed
90-day commit totals, the latest release, issue/PR counts, and the latest prior
finding. Results include explicit JSON nulls and a `found` flag. Missing repos
and first-seen findings return JSON rather than SQL NULL. Repo matching accepts
case differences and surrounding whitespace.

- Weekly histories and inter-release gaps are not fabricated.
- A zero previous commit count yields unknown percentage change.
- Release age uses the collection date, keeping frozen-snapshot replay stable.
- Maintainer-reply rates, unanswered counts, response times, dependents and
  contributor metrics are explicitly unknown, even if upstream rows contain
  legacy defaults/estimates for those deferred fields.
- The contributor function remains a catalog compatibility entry returning
  `available=false` and null metrics. It is excluded from both the agent's
  offered tools and dispatcher registry.
- Function comments and agent descriptions explain the available evidence and
  limitations. The agent prompt permits an inconclusive result when data is
  insufficient.

## Verification

- **20 local tests passed**, including the existing scraping suite, SQL statement
  parsing, bound repository parameters, SQL-null failures, and the agent's tool
  registry excluding the disabled contributor function.
- **12 SQL contract checks passed** against session-local fixture views and
  temporary functions using the same SQL definitions as production. These cover
  known/missing repos, null metrics, zero denominators, legacy estimated values,
  latest-finding selection, and literal repository arguments containing SQL.
- **5 live checks passed**: all six UC entries have descriptions; all five
  active functions were checked for `codehaus/jackson`, `psf/requests`, and
  `request/request`; all active functions handle missing repos explicitly.
- The live silver table contains at least 50 repos (100 at the start of this
  task). Sample outputs agree with their corresponding silver/gold values.
- All three job tasks (`verify_contracts`, `register_tools`, `verify_live`)
  finished with `SUCCESS`.

Saved summaries:

- `/Volumes/hackcamp/raw/github/ticket6_verification/20261107T212943_04554aee/summary.json`
- `/Volumes/hackcamp/raw/github/ticket6_verification/20261107T213011_0a72d2a3/summary.json`

## Handoff

From `databricks/`, run `databricks bundle run uc_tools -t dev --profile school`
to repeat fixture validation, registration and live checks. This job does not
seed or replace the corpus, modify grants, refresh the pipeline, or invoke the
model. Existing gold scores are returned unchanged; upstream normalization and
the scoring formula remain the responsibilities of tickets #4 and #5.

The first verification attempt successfully registered the functions but hit a
runtime restriction when listing functions with a two-part schema name. The
check now selects catalog `hackcamp` before listing schema `tools`; the complete
rerun linked above passed.
