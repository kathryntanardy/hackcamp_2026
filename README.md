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
Vite proxies `/api` requests to `http://127.0.0.1:8000`, so no local CORS configuration is needed.

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
```

See [PRD.md](PRD.md) for the product requirements.

## GitHub scraping (ticket #3)

One on-demand Databricks notebook collects real metrics for a curated corpus
of 50–100 repos. It uses the existing workspace, Volume and bundle, with no
additional Python packages. Setup requires a valid `school` profile and the
Databricks secret `hackcamp/github_token`.

From `databricks/`, validate and deploy the bundle, then run a five-repo smoke
test. The smoke test leaves the current pipeline input untouched.

```sh
databricks bundle validate -t dev --profile school
databricks bundle deploy -t dev --profile school
databricks bundle run github_scrape -t dev --profile school --params repo_limit=5,minimum_repos=5,publish=false
```

Collect and freeze the live snapshot (at least 50 successful repos across all
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
`/Volumes/hackcamp/raw/github/repos/`. The previous input is archived under that
snapshot's `previous_repos/` directory; a failed publish attempts to restore it.
Do not run the sample-seeding setup job after publishing a live snapshot.

Missing release/commit data and deferred contributor, reply-rate and dependents
metrics are written as `null`. The downstream nullable-data and MVP scoring/tool
changes belong to tickets #4–#6; the scraper does not invent those metrics.

If CLI login has expired, run `databricks auth login --profile school`.
If the GitHub secret is missing, use the existing token helper described in
[the workspace setup notes](.docs/HOUR1_CHECKS.md). The notebook reports this
without exposing the secret. Long rate-limit waits stop collection rather than
blocking the build; a partial result is publishable only if it still meets the
50-repo/five-language gate and authentication succeeded.

Offline checks require only Python:

```sh
python3 -m unittest discover -s databricks/tests -v
```
