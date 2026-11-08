# Ticket #19 — run-over-run memory (F13)

## Implementation (on `main`)

- UC tool `hackcamp.tools.get_previous_finding(repo)` returns the latest prior verdict.
- Each investigation run loads priors **through that UC function**, injects them into
  the prompt (`memory_prompt`), then **recomputes** `changed_since_last` in code
  (`memory.apply_memory`) so the model cannot invent the badge:
  `first_seen` | `newly_at_risk` | `recovered` | `unchanged` | `newly_ignored`.
- When the risk moves, the explanation is prefixed with
  `Changed since <date>: <old> → <new>.`
- Eval runs keep `use_memory=False` (always `first_seen`, no prior in the prompt).
- API: `/api/repos` exposes `changed_since_last` for map/list badges;
  finding payloads already include the column.

Local unit coverage: `databricks/tests/test_memory.py` (two-run label matrix).

## Live proof (`school` workspace)

Second+ runs already write non-`first_seen` labels:

| repo | prev → new | `changed_since_last` | run |
|------|------------|----------------------|-----|
| `fighting41love/funNLP` | inconclusive → at_risk | **newly_at_risk** | `20261108004145-90d3afee` |
| `ryanmcdermott/clean-code-javascript` | at_risk → at_risk | **unchanged** | same |
| `vuejs/vue` | at_risk → ignored | **newly_ignored** | `20261107230633-7aa20878` |
| `nvbn/thefuck` / `funNLP` / `clean-code-javascript` | same risk again | **unchanged** | `20261108005020-757c652c` (after UC load path) |

Earlier corpus run `20261107235620-29b18199` was all **first_seen** (3/3); later overlapping runs flip to **unchanged** / transitions — done-when for a second run.

Note: a `budget_n=3` smoke at ~00:45 UTC hit Foundation Model **429 rate limits**; `verify_traces` then failed a tool-count assert on thin traces. Memory labels on successful repos in that window still showed **unchanged** when a prior finding existed (`nvbn/thefuck`).

## Re-verify

```sh
cd databricks
databricks bundle deploy -t dev --profile school
databricks bundle run agent_run -t dev --profile school --params budget_n=3,max_tool_calls=4
```

```sql
SELECT repo_id, risk_level, changed_since_last, left(explanation, 120) AS explanation
FROM hackcamp.agent.findings
WHERE run_id = '<latest_run_id>'
ORDER BY investigated_at;
```
