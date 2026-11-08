# Ticket #15 — scheduled end-to-end autonomy (F10)

Verified November 7, 2026, on the existing Databricks workspace (`school`).

[Successful end-to-end run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/413550507495536/runs/1114743628619428?o=7474652966987564)

## Result

- Job: `[dev philip03ho] hackcamp-scheduled-autonomy` (job id `413550507495536`)
- Graph: `refresh_pipeline` (repo_health bronze→silver→gold) → `run_agent` (nested `hackcamp-agent-run`)
- Both tasks **SUCCESS**; no manual handoff between pipeline and agent
- Schedule: daily **10:00 America/Los_Angeles** (`UNPAUSED`)
- Smoke params for the proof run: `budget_n=2`, `max_tool_calls=4`

Scraping stays a separate on-demand job (`github_scrape`); the scheduled path reuses the frozen Volume snapshot.

## Deploy / rerun

```sh
cd databricks
databricks bundle deploy -t dev --profile school
databricks bundle run scheduled_autonomy -t dev --profile school
```

## Note

An earlier attempt failed on `hackcamp.agent.trace_steps` privileges for the
run-as user. `create_trace_steps.sql` now grants `SELECT, MODIFY` to
`account users` so the agent MERGE does not depend on who created the table.
