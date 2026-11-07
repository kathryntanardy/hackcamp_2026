# Ticket #11 — investigation tracing verified

Verified November 7, 2026, on the existing Databricks workspace.

[Successful end-to-end run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/738063920946188/runs/575682166888223)

## Result

- All three job tasks passed: `prepare_trace_steps`, `investigate`, and
  `verify_traces`.
- Investigation run ID: `20261107214610-41139bba`.
- Repository: `vuejs/vue`.
- Persisted MLflow trace ID: `tr-b0c3dd08d313820144aa3298c2bef91e`.
- The trace contains **4 executed tool steps and 5 model-decision steps**.
- A separate verification task fetched the stored trace from MLflow, looked up
  the saved finding, and confirmed that the exported ordered steps match it.
- **32 offline tests passed**, including model/tool failures, validation retries,
  budget finalization, distinct trace IDs, complete large tool outputs, privacy
  of the app export, and missing/mismatched finding lookups.

[MLflow experiment and traces](https://dbc-a0a04386-0e40.cloud.databricks.com/ml/experiments/3876070005521687/traces)

Verification summary:
`/Volumes/hackcamp/raw/github/ticket11_verification/20261107214610-41139bba/summary.json`.

## Implementation

`run_investigation.py` now captures each investigation's own root trace ID
instead of querying a global last-active trace. Every model invocation is
instrumented, including retries and budget finalization. Each executed tool has
its inputs, full output, call ID and status recorded. A model failure still
produces an inconclusive verdict on that same trace. The decision limit also
bounds repeated model replies that never call tools.

`trace_steps.py` projects the trace into chronological decisions and tool steps.
Display summaries are shortened while complete tool outputs remain available.
The app receives public decision summaries and verdict explanations, never
hidden provider reasoning or system prompts. When no public rationale was
provided, `reasoning_available=false` is explicit.

Exports are merged into `hackcamp.agent.trace_steps` before findings are linked
to them. The lookup joins on trace ID, repo ID and investigation run ID. Missing
findings return `found=false`; historical findings without an export return
`status=not_ready`; mismatched exports fail validation.

The agent job creates the export table without resetting existing findings or
the scraped corpus. The default MLflow experiment is in the signed-in user's
workspace folder. Permissions were not changed by the implementation.

## App handoff

Ticket #12 can query the JSON payload through the existing SQL warehouse; the
HTTP endpoint and visual trace tab remain in #12 and #26. The SQL lookup and
payload fields are documented in the README's Investigation traces section.
No new backend service or MLflow package is required just to read saved steps.

The verification used `budget_n=1,max_tool_calls=4`. It did not run a full
20-repository investigation batch or an evaluation run. Existing ticket #6
changes in the working tree were preserved; source changes remain uncommitted.
