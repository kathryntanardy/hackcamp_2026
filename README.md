# Open-Source Corpus Explorer

React + TypeScript + Vite frontend and Python FastAPI backend.

## Requirements

- Node.js 20.19+ or 22.12+
- Python 3.10+

## Backend

From the project root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000/api/health

Interactive API docs: http://127.0.0.1:8000/docs

## Frontend

In a second terminal, from the project root:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The starter page displays the backend connection status.
Vite proxies `/api`, `/openapi.json`, `/docs`, and `/redoc` to `http://127.0.0.1:8000`, so no local CORS configuration is needed.

### SEO / AEO boilerplate

Static discovery files live in `frontend/public/` and ship with the Vite build:

| Path | Purpose |
| --- | --- |
| `/robots.txt` | Crawler allow list + sitemap pointer |
| `/sitemap.xml` | Core URLs for search engines |
| `/llms.txt` | Short machine-readable product + API map for AI agents |
| `/llms-full.txt` | Longer agent context |
| `/site.webmanifest` | PWA/manifest metadata |

The homepage is plain HTML in `frontend/index.html` (no CSS). React under `frontend/src/` is still available for the map later.

Before production, replace every `https://REPLACE_WITH_SITE_ORIGIN` placeholder in those files and in `frontend/index.html` with your real deployed origin (for example your Databricks Apps URL). Keep `lastmod` / "Last updated" dates fresh when claims change.

## Production build

```sh
cd frontend
npm run build
```

The frontend build is written to `frontend/dist`. For deployment, serve these static files
and route `/api` to the FastAPI service on the same origin. `npm run preview` previews
static assets only; its server does not provide the development API proxy.

## Databricks (pipeline + agent)

Bundle lives in [`databricks/`](databricks/). Hour-1 workspace check results: [`.docs/HOUR1_CHECKS.md`](.docs/HOUR1_CHECKS.md).

Includes Unity Catalog setup, Lakeflow `repo_health` pipeline, UC tool functions, and the investigation agent job.

```sh
cd databricks
databricks bundle validate -t dev --profile school
databricks bundle deploy -t dev --profile school
databricks bundle run uc_setup -t dev --profile school
databricks bundle run repo_health -t dev --profile school
databricks bundle run agent_run -t dev --profile school
# F10 / ticket #15 — pipeline then agent on a daily schedule
databricks bundle run scheduled_autonomy -t dev --profile school
```

For ticket #14, run the labelled evaluation with the current agent:

```sh
databricks bundle run eval_run -t dev --profile school
```

This evaluates all 50 current labels and compares the agent with the frozen gold
formula. MLflow retains labels, per-repository results, a weight comparison, timing,
and the prompt fingerprint/retry configuration. The grounding judge must cover
every case; only failed judge calls are retried, preserving valid negative scores.
The verification task reconciles the metrics and saved `agent.runs.eval_score`.
Evaluation writes no production findings. Its score is a labelled-set model
benchmark, not accuracy measured on an unlabelled production batch.

Summaries and verification are saved under
`/Volumes/hackcamp/raw/github/evaluations/<eval-run-id>/`. Binary accuracy treats
both `at_risk` and `ignored` as flagged; `verdict_accuracy` separately penalizes
abstentions and wrong risk bins. See [the rerun report](.docs/TICKET14_REDO_RUN.md).

See [PRD.md](PRD.md) for the product requirements.

## Scheduled autonomy (ticket #15)

Lakeflow Job `hackcamp-scheduled-autonomy` chains `repo_health` (bronze→silver→gold)
into `agent_run` (investigate → findings + traces). Scraping stays a separate
on-demand job so the schedule reuses the frozen Volume snapshot.

Default schedule: daily 10:00 America/Los_Angeles (`UNPAUSED`). Override
`budget_n` / `model_endpoint` / `experiment_path` as job parameters. Pause from
the Jobs UI if you need to stop overnight runs.

```sh
databricks bundle run scheduled_autonomy -t dev --profile school --params budget_n=2,max_tool_calls=4
```

Proof run: [`.docs/TICKET15_RUN.md`](.docs/TICKET15_RUN.md).

## Unity Catalog lineage (ticket #16)

Pipeline lineage is bronze → silver → gold. Agent findings are joined to gold so
Catalog Explorer also shows gold → findings. Demo view:
`hackcamp.gold.verdicts_lineage` (open its **Lineage** tab).

```sh
databricks bundle run lineage_capture -t dev --profile school
```

Links and the confirmed edge list: [`.docs/TICKET16_RUN.md`](.docs/TICKET16_RUN.md).

## GitHub scraping (ticket #3)

One on-demand Databricks notebook collects real metrics for a curated corpus
of 1,000 unique repos. It retains the curated controls, discovers additional
public repos across five languages, and deduplicates canonical IDs. It uses the existing workspace, Volume and bundle, with no
additional Python packages. Setup requires a valid `school` profile and the
Databricks secret `hackcamp/github_token`.

From `databricks/`, validate and deploy the bundle, then run a five-repo smoke
test. The smoke test leaves the current pipeline input untouched.

```sh
databricks bundle validate -t dev --profile school
databricks bundle deploy -t dev --profile school
databricks bundle run github_scrape -t dev --profile school --params repo_limit=5,minimum_repos=5,publish=false
```

Collect and freeze the live snapshot (1,000 unique successful repos across all
five intended languages), then run the existing pipeline manually:

```sh
databricks bundle run github_scrape -t dev --profile school
databricks bundle run repo_health -t dev --profile school --full-refresh-all
```

After each newly published snapshot, `--full-refresh-all` rebuilds the pipeline's
derived tables from the current real input. This both removes historical sample
rows and makes Auto Loader reread the stable filenames used by the scraper.
Run the pipeline only after the scraper reports `published: true`. Keep its
downstream agent job stopped during this handoff. Ordinary pipeline reruns are
fine while reusing the same unchanged frozen snapshot.

The job prints a summary and its Volume path. Every attempt saves
`snapshots/<run_id>/summary.json` outside the Auto Loader input, including counts
and failed repo IDs. Successful snapshots retain their JSON under
`snapshots/<run_id>/repos/`, and the active copy is published to
`/Volumes/hackcamp/raw/github/repos/`. Records are batched into JSON Lines files (up to 100 records each), so 1,000
repos occupy 10 data files. Verify record counts rather than file counts. The
previous input is archived under that snapshot's `previous_repos/` directory; a failed publish attempts to restore it.
Do not run the sample-seeding setup job after publishing a live snapshot.

Missing release/commit data and deferred contributor, reply-rate and dependents
metrics are written as `null`. The downstream nullable-data and MVP scoring/tool
changes belong to tickets #4–#6; the scraper does not invent those metrics.

If CLI login has expired, run `databricks auth login --profile school`.
If the GitHub secret is missing, use the existing token helper described in
[the workspace setup notes](.docs/HOUR1_CHECKS.md). The notebook reports this
without exposing the secret. Long rate-limit waits stop collection rather than
blocking the build; a partial result is publishable only if it still meets the
1,000-repo/five-language gate and authentication succeeded.

Offline checks require only Python:

```sh
python3 -m unittest discover -s databricks/tests -v
```

## Agent data tools (ticket #6)

The agent uses five snapshot-backed Unity Catalog functions in `hackcamp.tools`:
repo metrics, fixed 90-day commit totals, the latest release, issue/PR counts,
and the previous finding. Each returns a JSON object with explicit nulls,
provenance and a `found` flag. Missing rows return `found: false`; missing metrics
do not become evidence of abandonment. Release age is measured at the snapshot's
collection time so replaying frozen data gives the same result.

Weekly histories, inter-release gaps, response times, unanswered counts and
contributor concentration are not inferred. The contributor function remains
registered as an unavailable compatibility entry and is excluded from the
agent's callable tools. Its output contains no bus-factor proxy.

After the real snapshot is loaded through the existing pipeline, deploy and
verify the functions from `databricks/`:

```sh
databricks bundle validate -t dev --profile school
databricks bundle deploy -t dev --profile school
databricks bundle run uc_tools -t dev --profile school
```

This dedicated job first tests the actual SQL definitions against temporary
fixture views/functions, then registers the persistent UC functions, then checks
their outputs against known repos in the live silver/gold tables. It does not
run the sample-seeding setup job or the investigation agent. Registration needs
permission to create/replace functions in `hackcamp.tools` and access to their
source tables. Existing function ownership/management permissions are also
required for replacements; the job does not change grants.

Each verification task prints its result and saves a JSON summary under
`/Volumes/hackcamp/raw/github/ticket6_verification/<run_id>/summary.json`.
The tests include missing repos, null metrics, zero prior commit counts,
historical verdict selection, and ignoring old estimated metrics.

## Investigation traces (ticket #11)

Each investigation captures its own root MLflow trace ID and stores it on the
finding. Model decisions, structured-output retries, budget finalization and
every executed tool call are traced. Tool spans retain their complete inputs and
outputs. Model/tool failures produce a traced inconclusive finding or an explicit
error step rather than silently assigning another investigation's trace.

The same trace is exported to `hackcamp.agent.trace_steps` as a JSON payload,
keyed by `trace_id` and associated with `repo_id` and `run_id`. This lets the app
read traces through the existing SQL warehouse, without an MLflow client in its
backend. `get_finding_trace(spark, repo_id, run_id=None)` in
`databricks/src/agent/trace_steps.py` implements the lookup contract; the HTTP
endpoint belongs to ticket #12.

```sql
SELECT t.payload
FROM hackcamp.agent.findings f
JOIN hackcamp.agent.trace_steps t
  ON f.trace_id = t.trace_id
 AND f.repo_id = t.repo_id AND f.run_id = t.run_id
WHERE f.repo_id = :repo_id AND f.run_id = :run_id;
```

The payload includes the trace ID, experiment link, verdict explanation and
chronological `steps`. Each step includes its kind, tool name, inputs, outputs,
result summary, error status and public decision summary in `reasoning`.
`reasoning_available=false` makes missing explanations explicit. Hidden provider
reasoning and system prompts are not included in the app export. Large tool
outputs remain intact; only the display summary is shortened.

From `databricks/`, validate/deploy as usual, then verify with one real repo:

```sh
databricks bundle run agent_run -t dev --profile school --params budget_n=1,max_tool_calls=4
```

The job prepares the trace-export table, runs the investigation, persists its
trace/finding link, and verifies that fetching MLflow and querying the finding
return the same ordered steps. `experiment_path` defaults to the signed-in
user's own experiment; override it to use an existing shared experiment if you
have access. The verification task saves its summary under
`/Volumes/hackcamp/raw/github/ticket11_verification/<run_id>/summary.json`.
It does not refresh or replace the scraped corpus. Legacy findings without an
export return `status=not_ready`; unknown findings return `found=false`.
