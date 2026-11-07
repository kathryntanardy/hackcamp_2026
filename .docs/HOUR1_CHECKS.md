# Hour-1 workspace checks

Checked: 2026-11-07 against profile `school` (`https://dbc-a0a04386-0e40.cloud.databricks.com`).

## Results

| Check | Result |
| --- | --- |
| Catalog `hackcamp` + schemas `raw`, `bronze`, `silver`, `gold`, `agent`, `tools` | **Pass** — all present |
| UC Volume `/Volumes/hackcamp/raw/github/` | **Pass** — managed volume `hackcamp.raw.github` |
| Secret scope + GitHub token | **Partial** — scope `hackcamp` exists; secret `github_token` **not stored yet** (no token in local env). Put it with [`../databricks/scripts/put_github_token.sh`](../databricks/scripts/put_github_token.sh) |
| Workspace type | **Not Free Edition** (API does not expose SKU name). Classic cluster list empty; serverless SQL warehouse present. Treat as **trial / organiser-provided full workspace** |
| Model Serving | **Available** — Foundation Model endpoints ready |
| Vector Search | **Available** — created probe endpoint `hackcamp-vs-probe` (ONLINE) |
| Databricks Apps | **Available** — created probe app `hackcamp-probe-app` |
| FM models + best tool calling | **Pass** — see below |
| UC Python outbound HTTP | **Pass** — `hackcamp.tools.http_probe()` returned `ok status=200` from `https://httpbin.org/get` → live-fetch tools **may be UC Python functions** |

## Foundation Model bakeoff (tool calling)

All of the following accepted `tools=` and emitted an `add_numbers` tool call:

- `databricks-meta-llama-3-3-70b-instruct` ← **recommended / locked for agent**
- `databricks-llama-4-maverick`
- `databricks-meta-llama-3-1-8b-instruct`
- `databricks-gpt-oss-20b`
- `databricks-qwen3-next-80b-a3b-instruct`
- `databricks-qwen35-122b-a10b` (works; returns reasoning blocks + stringified args)
- `databricks-gemma-3-12b`

Also present (embeddings / not used for agent tools): `databricks-bge-large-en`, `databricks-gte-large-en`, `databricks-qwen3-embedding-0-6b`, `databricks-gpt-oss-120b`.

**Decision:** keep agent on `databricks-meta-llama-3-3-70b-instruct` (strong tool calling, already proven in investigation runs). Fallback: `databricks-llama-4-maverick`.

## Implications for the PRD

- Live GitHub fetch tools (`fetch_recent_issues`, `fetch_readme_signals`) can be UC Python functions **or** plain Python tools; UC HTTP works in this workspace.
- Find-alternatives (Vector Search) and Databricks Apps hosting are on the table — not blocked by edition.
- Secrets: until `hackcamp/github_token` is set, keep using seeded Volume JSON (already in place).

## Artifacts

- Probe notebook/job: `databricks/src/setup/hour1_probes.py`, job `hackcamp-hour1-probes`
- Summary table: `hackcamp.agent.hour1_checks`
- Summary file: `/Volumes/hackcamp/raw/github/hour1_probe_summary.json`
- Secret helper: `databricks/scripts/put_github_token.sh`

## Remaining manual step

```sh
export GITHUB_TOKEN=ghp_your_token_here
export DATABRICKS_CONFIG_PROFILE=school
bash databricks/scripts/put_github_token.sh
```

Then verify in a notebook:

```python
dbutils.secrets.get("hackcamp", "github_token")  # do not print
```
