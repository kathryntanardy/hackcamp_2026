# Ticket #15 — scheduled Lakeflow Job (F10)

Verified November 7, 2026, profile `school`.

[Successful end-to-end run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/413550507495536/runs/262131822189504?o=7474652966987564)

[Scheduled job](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/413550507495536?o=7474652966987564)

## Result

- Job `hackcamp-scheduled-autonomy` chains **`refresh_pipeline`** (`repo_health`
  bronze→silver→gold) then **`run_agent`** (nested `hackcamp-agent-run`).
- Schedule: daily **10:00 America/Los_Angeles**, `UNPAUSED`.
- Scraping stays on-demand (`github_scrape`); the schedule reuses the frozen Volume.
- Proof run: `budget_n=2`, `max_tool_calls=4` → **TERMINATED SUCCESS**
  (~3.5 minutes after deploy).
- Earlier failure was UC privileges on `hackcamp.agent.trace_steps` for
  `philip03ho@gmail.com` (table owned by `kathrieynchen@gmail.com`). Fixed via
  `grant_team_access.sql` and ad-hoc GRANTs.

## Implementation

- Bundle resource: `databricks/resources/scheduled_autonomy.job.yml`
- Team grants: `databricks/src/setup/grant_team_access.sql` (uc_setup task
  `grant_team_access`)

```sh
cd databricks
databricks bundle deploy -t dev --profile school
databricks bundle run scheduled_autonomy -t dev --profile school --params budget_n=2,max_tool_calls=4
```
