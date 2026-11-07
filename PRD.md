# Open-Source Corpus Explorer PRD

Nov 6, 2026 · @Hi

An interactive galaxy map of GitHub repositories where an autonomous Databricks agent finds critical open-source packages that are quietly dying, investigates them with governed tools, and shows its evidence. Built in 20 hours for HackCamp, targeting the Best Use of Databricks track.

## Problem and goal

The question: **which open-source packages that many people depend on are losing their maintainers?** GitHub shows stars and commits per repo, but nobody watches thousands of repos for the slow signs of abandonment: releases stopping, issues piling up, one maintainer left.

**Product goal:** an AI agent that watches a corpus of repos on its own, picks which ones look worrying, investigates them with real tools, and records a verdict with evidence. People explore the results on a galaxy map, with no chatbot.

**Hackathon goal:** win Best Use of Databricks. That means Databricks has to be the engine of the product, not just hosting: ingestion, governance, the agent's tools, tracing, evaluation and scheduling all run on the platform, and the demo shows each of them working.

**Not the goal:** a complete or real-time picture of all of GitHub. About 500 repos across 4–5 languages is enough to make the point.

## Users and judges

| Who | What they want | What we show them |
| --- | --- | --- |
| Engineering lead picking dependencies | "Is this library safe to bet on?" | The repo's health, the agent's verdict, a healthier alternative |
| Open-source program office or security team | A watchlist of risky dependencies | The Findings page, sorted by severity, with what changed since the last run |
| Funders and maintainers | Which important projects need help | Critical, at-risk stars on the map |
| **Hackathon judges (Best Use of Databricks)** | Deep, essential use of the platform | Live traces, Unity Catalog lineage, the eval score, the scheduled job |

Assumption about judging (to confirm against the track's rules): judges reward Databricks being essential to the product, native AI and agent features used properly, and evidence that the system works. They don't reward a long list of services.

## Scope

**Must-have (the demo fails without these)**

- About 500 repos ingested through a Lakeflow pipeline into Delta, governed in Unity Catalog
- A baseline health score for every repo
- A tool-calling agent that triages and investigates flagged repos and writes structured verdicts
- Agent tools registered as Unity Catalog functions
- MLflow traces for every investigation, viewable from the app
- A galaxy map, a findings page and a repo drawer, hosted on Databricks Apps
- An eval run on a labelled set with a reported score

**Nice-to-have (only if ahead of schedule)**

- Scheduled Lakeflow Job running the whole loop end to end
- Vector Search powering a find-alternatives tool
- Memory across runs: "newly at risk" and "recovered" badges
- `ai_query()` one-line summaries for repos the agent did not investigate
- Zoom and pan, pulsing stars, link lines between similar repos

**Out of scope**

- Chatbot or Genie-style Q&A
- Multi-agent orchestration
- A full dependency graph
- Real-time or all-of-GitHub coverage
- Login, user accounts, Terraform, CI/CD

## Features and requirements

| ID | Feature | Priority | Acceptance criteria |
| --- | --- | --- | --- |
| F1 | Repo ingestion | P0 must | About 500 repos across Python, JavaScript, Go, Rust and one more, landed in bronze, silver and gold Delta tables by a Lakeflow pipeline; expectations drop malformed rows and log the counts |
| F2 | Baseline health score | P0 must | Every gold row has a `health_score` from 0 to 100 and a status of healthy, watchlist or at risk, recomputed on each run |
| F3 | Agent triage | P0 must | Given a budget N (default 20), the agent picks which repos to investigate and logs why it chose them |
| F4 | Agent investigation | P0 must | The agent calls at least 2 tools per repo, chosen by the model rather than a fixed sequence, and stops when it is confident or reaches 8 calls |
| F5 | Structured verdict | P0 must | Each investigation writes one `findings` row matching the schema in Agent design, with every evidence item pointing to a tool result |
| F6 | Reasoning trace | P0 must | Every investigation has an MLflow trace, and the repo drawer shows its tool calls and results in order |
| F7 | Galaxy map | P0 must | Renders all repos as stars clustered by language, sized by importance and coloured by health; hover shows the name and score; click opens the drawer; 500 stars render smoothly |
| F8 | Findings page | P0 must | Lists findings sorted by severity, then importance; filters by language and risk; a row click opens that repo on the map |
| F9 | Evaluation | P1 should | The agent runs on 30–50 labelled repos; accuracy and false-positive rate are logged in MLflow and shown in the pitch |
| F10 | Scheduled autonomy | P1 should | One Lakeflow Job runs pipeline, then scoring, then agent, then refreshes findings, end to end with no manual steps |
| F11 | Lineage view | P1 should | A Unity Catalog lineage screenshot or link from the raw volume to `findings` |
| F12 | Find alternatives | P2 if time | For an at-risk repo, the agent returns up to 3 similar healthy repos from Vector Search |
| F13 | Run-over-run memory | P2 if time | The agent reads its previous finding for each repo; the UI shows newly at risk and recovered badges |

## Pages and UX

Two pages plus a slide-out drawer. Dark space theme, built in React with ECharts.

**Galaxy Map (`/`)**: the hero screen

- Full-screen star field. Each language gets a fixed cluster centre, and repos are scattered around it with a seeded random offset so positions stay the same between reloads.
- Star size = importance, the log of dependents (or stars if dependents are missing). Star colour = status: green healthy, amber watchlist, red at risk. A pulsing ring marks repos the agent investigated in the latest run.
- Top bar: repos tracked, healthy, watchlist, at risk, last agent run time.
- Filters: language, status, "investigated only".
- Hover shows a tooltip with the name, score and status. Click opens the drawer.

**Findings (`/findings`)**: the agent's output

- One row per finding: repo, risk level, confidence, a one-line headline, investigated time, a "new" badge.
- Sorted by severity, then importance. Filters for language and risk.
- Clicking a row jumps to the map with that star selected and the drawer open.
- Header strip: latest run stats, i.e. repos triaged, investigated, tool calls made and eval score.

**Repo drawer**: opens from either page

- Header: name, GitHub link, language, stars, dependents.
- Health gauge plus the metrics behind it: days since last release, commits in the last 90 days vs the previous 90, open issues, unanswered PRs, top-contributor share.
- Agent verdict: risk level, confidence, a short explanation, an evidence list, and a recommended alternative if one was found.
- **"How the agent decided" tab:** the MLflow trace as a step list showing tool name, inputs, a result summary and the model's reasoning at each step.
- Previous verdict and its date, if one exists.

## Agent design

One tool-calling agent, built with Mosaic AI Agent Framework on a Foundation Model API model, makes its own decisions in two places: **which repos to investigate** and **which evidence to gather**. A fixed scoring pipeline feeds it, and it writes structured verdicts back to Delta.

**Loop for each run**

1. **Triage.** Read `gold_repo_health` plus the previous `findings`. Pick up to N repos (default 20) by importance × risk, favouring repos whose score changed since the last run. Log the chosen list and a one-line reason for each.
2. **Investigate each pick.** Start from the repo's baseline metrics. Call tools in whatever order the model chooses. Dig deeper when signals conflict: low commits but steady releases may just mean the project is mature.
3. **Stop.** Stop when confidence is at least 0.7, or after 8 tool calls, whichever comes first.
4. **Verdict.** Emit JSON matching the schema below. Code validates it, and an invalid output gets one retry before the repo is marked `inconclusive`.
5. **Persist.** `MERGE` into `findings`, keyed on (repo\_id, run\_id). The trace id is stored on the row.
6. **Memory.** On the next run, step 1 reads the previous verdicts, and the agent states what changed.

**Tools**

| Tool | Type | Returns |
| --- | --- | --- |
| `get_repo_metrics(repo)` | UC SQL function over gold | Baseline metrics and score |
| `get_commit_trend(repo, weeks)` | UC SQL function over silver | Weekly commit counts |
| `get_release_history(repo)` | UC SQL function | Release dates and gaps |
| `get_issue_backlog(repo)` | UC SQL function | Open issues and PRs, median first-response time, unanswered count |
| `get_contributor_concentration(repo)` | UC SQL function | Top contributor's share of the last 100 commits (bus factor) |
| `fetch_recent_issues(repo, n)` | Live GitHub fetch, cached to Delta | Last n issue titles and whether a maintainer replied |
| `fetch_readme_signals(repo)` | Live GitHub fetch, cached to Delta | Flags for "deprecated", "unmaintained", "archived", "use X instead" |
| `get_previous_finding(repo)` | UC SQL function over findings | Last verdict and date |
| `find_alternatives(repo)` (P2) | Vector Search | Up to 3 similar healthy repos |

The live-fetch tools may need to be plain Python tools inside the agent instead of UC functions if UC functions can't make outbound HTTP calls. Check this in hour 1.

**Verdict schema**

```json
{
  "repo_id": "psf/requests",
  "risk_level": "healthy | watchlist | at_risk | inconclusive",
  "confidence": 0.0,
  "headline": "one line for the findings list",
  "explanation": "2-4 sentences",
  "evidence": [{"signal": "no release in 410 days", "tool": "get_release_history", "value": 410}],
  "changed_since_last": "newly_at_risk | recovered | unchanged | first_seen",
  "alternatives": ["org/repo"],
  "tool_calls": 5
}
```

**Guardrails**

- Every evidence item must name a tool that was actually called in the trace. Code checks this, and unsupported claims are stripped before saving.
- A tool budget and a timeout per repo, so one repo can't burn the run.
- Low temperature for verdicts. The system prompt includes the scoring rubric so the LLM and the formula agree on what each level means.
- The agent is read-only towards GitHub. It never opens issues or comments anywhere.

## Data sources and ingestion

There are two layers. The bulk pull is a deterministic pipeline that gives every star a baseline. The targeted fetches are agentic: the agent decides which ones to make.

**Layer 1: bulk ingest (pipeline)**

- **Repo list:** GitHub search API, top repos per language (for example `language:python stars:>1000`), around 100 per language. Search returns at most 1,000 results per query.
- **Metrics:** GitHub GraphQL API, about 50 repos per query. Fields: `stargazerCount`, `isArchived`, `pushedAt`, `primaryLanguage`, `releases(last:1)`, `defaultBranchRef.target.history(since: 90d)` and `(since: 180d)` totals, open `issues` and `pullRequests` counts, `mentionableUsers` total.
- **Importance:** dependents counts from deps.dev for packages that map to a repo. As a cross-check, OpenSSF Scorecard and Criticality Score where they're available.
- **Auth:** the GitHub token goes in a Databricks secret scope and is read with `dbutils.secrets.get`, never in code.
- **Landing:** a Python notebook task writes raw JSON to a UC Volume (`/Volumes/hackcamp/raw/github/`). The Lakeflow pipeline reads it with Auto Loader into bronze.
- **Freeze:** pull once, early, and keep the snapshot. The demo never depends on live GitHub.

**Layer 2: targeted fetches (agent tools)**

- Only made for repos the agent chose to investigate: recent issues with maintainer replies, README signals, recent commit authors.
- Every response is cached in `tool_cache` (Delta), so repeat runs and the demo don't hit the API.

**If the hackathon provides a corpus,** it replaces Layer 1. Keep the same gold schema so nothing downstream changes.

## Data model

Everything lives in catalog `hackcamp`, in schemas `raw`, `bronze`, `silver`, `gold`, `agent` and `tools`.

| Table | Grain | Key columns |
| --- | --- | --- |
| `bronze.github_repos_raw` | One API response per repo per pull | `repo_id`, `payload` (JSON), `pulled_at` |
| `silver.repos` | One row per repo | `repo_id`, `name`, `owner`, `language`, `stars`, `is_archived`, `pushed_at`, `last_release_at`, `commits_90d`, `commits_prev_90d`, `open_issues`, `open_prs`, `contributors`, `dependents` |
| `gold.repo_health` | One row per repo per run | `repo_id`, `run_id`, `health_score`, `status`, `importance`, `days_since_release`, `commit_trend_pct`, `x`, `y`, `scored_at` |
| `agent.findings` | One row per investigated repo per run | `repo_id`, `run_id`, `risk_level`, `confidence`, `headline`, `explanation`, `evidence` (array of structs), `changed_since_last`, `alternatives`, `tool_calls`, `trace_id`, `investigated_at` |
| `agent.runs` | One row per agent run | `run_id`, `started_at`, `repos_triaged`, `repos_investigated`, `tool_calls_total`, `model`, `eval_score` |
| `agent.tool_cache` | One row per live fetch | `tool`, `args_hash`, `response`, `fetched_at` |
| `agent.eval_labels` | One row per labelled repo | `repo_id`, `label`, `label_source`, `notes` |

`x` and `y` are precomputed in gold (the language's cluster centre plus a seeded offset), so the frontend draws them as they are.

## Health scoring

The baseline score is a simple weighted formula computed in the gold layer. It decides star colour and feeds triage. The agent's verdict can override it, and the drawer shows both.

```latex
\text{health} = 30\,s_{\text{release}} + 25\,s_{\text{commits}} + 20\,s_{\text{issues}} + 15\,s_{\text{bus}} + 10\,s_{\text{activity}}
```

Each sub-score runs from 0 to 1:

| Sub-score | Signal | 1.0 when | 0.0 when |
| --- | --- | --- | --- |
| s\_release | Days since last release | 90 days or less | 540 days or more (linear in between) |
| s\_commits | commits\_90d ÷ commits\_prev\_90d | 1.0 or more | 0.2 or less |
| s\_issues | Share of PRs and issues with a maintainer reply | 80% or more | 20% or less |
| s\_bus | 1 − top contributor's share of the last 100 commits | 0.6 or more | 0.1 or less |
| s\_activity | Days since last push | 30 days or less | 365 days or more |

- **Thresholds:** 70 or more is healthy, 40 to 69 is watchlist, below 40 is at risk. An archived repo is always at risk.
- **Importance** (star size and triage weight) = log10(dependents + 1), falling back to log10(stars + 1).
- **Triage priority** = importance × (100 − health), boosted when the score dropped by 10 or more points since the last run.
- The weights are a first guess. Tune them against the labelled eval set in hour 15, and note the final weights in the pitch.

## Databricks services

Seven services are core and carry the Best Use of Databricks story. Four more are optional. Service names are from memory as of mid-2026, so check them against current docs.

| Service | Role in this product | Why judges care | Priority |
| --- | --- | --- | --- |
| Lakeflow Declarative Pipelines (formerly DLT) | Bronze to silver to gold, with Auto Loader and expectations | Managed incremental ETL with data-quality metrics built in | Core |
| Delta Lake | Every table; `MERGE` for findings; time travel to compare runs | Agent memory is just Delta history | Core |
| Unity Catalog | Namespace, permissions, lineage across tables, functions and models | One governed lineage from raw API JSON to an AI verdict | Core |
| UC functions | The agent's data tools | The agent's tools are governed, discoverable catalog objects | Core |
| Foundation Model APIs | The model behind the agent | No model hosting to manage | Core |
| Mosaic AI Agent Framework | Agent loop, logged as an MLflow model | Platform-native agent rather than a script calling an API | Core |
| MLflow Tracing and GenAI evaluation | Per-investigation traces; eval on the labelled set with LLM judges and custom metrics | Shows how the agent reasons and how well it performs | Core |
| Lakeflow Jobs | Scheduled end-to-end run | This is what makes "autonomous" true | Should |
| Databricks Apps + SQL warehouse | Hosts the React app and a thin Python API querying gold and findings | The whole product lives inside the workspace | Should |
| Model Serving | Agent as an endpoint, for the live demo investigation | One-click "investigate now" from the UI | If time |
| Vector Search | Index over repo descriptions for find\_alternatives | Retrieval as an agent tool, not a chatbot | If time |
| `ai_query()` | Batch one-liners for repos not investigated | LLM inference in plain SQL at table scale | If time |

**Skipped on purpose:** Genie (a chatbot, out of scope), Lakebase (Delta through a SQL warehouse is fast enough), AI/BI dashboards (the custom UI covers it).

## Architecture

&#91;embedded content: architecture · data, agent and app inside one workspace\]

GitHub data comes in once through the pipeline. The agent reads gold, calls governed UC tools and writes findings and traces, which the app reads. Unity Catalog governs all of it.

## Evaluation and success metrics

The pitch includes one measured number: how often the agent's verdict matches ground truth on repos whose status we already know.

**Labelled set (30–50 repos, built in hours 9–10)**

- **At risk:** repos that are archived, carry an official "unmaintained" or "deprecated" notice, or whose maintainers announced they're stepping down.
- **Healthy:** well-known projects with releases in the last 90 days and several active maintainers.
- **Hard cases:** mature or "done" projects that are quiet but fine, and projects that recently revived.
- **Label source** goes in `eval_labels.label_source`, for example a link to the deprecation notice.

**How to score**

- MLflow GenAI evaluation runs the agent on the set.
- Custom metrics: verdict accuracy, at-risk precision and recall, and a false-alarm rate on the hard cases.
- An LLM judge checks that each explanation is grounded in the trace's tool outputs.
- The baseline formula alone is scored too, so the pitch can say how much the agent adds over the formula.

**Targets**

| Metric | Target |
| --- | --- |
| At-risk recall | 80% or more |
| At-risk precision | 75% or more |
| Agent accuracy minus formula accuracy | Positive; show the gap |
| Groundedness (LLM judge) | 90% or more of explanations pass |
| Median tool calls per investigation | 3–6 (shows real choice without thrashing) |
| Full run, 20 investigations | Under 10 minutes |

Targets are first guesses. Report whatever the real numbers are.

## Build plan

&#91;embedded content: build plan · 4 workstreams, 3 gates, hours from kickoff\]

The frontend works against mock data until hour 9, so the data and agent workstreams never block it. If a gate slips by more than 2 hours, cut features in the order listed under Risks.

## Demo script

A 3-minute walkthrough. Every Databricks claim is shown on screen, not just said.

1. **Hook (0:00–0:20).** "Your app depends on hundreds of packages. Which ones are dying?" Open the galaxy map: 500 stars, with red ones scattered through the clusters.
2. **The map (0:20–0:50).** Filter to at-risk. Hover a big red star and click it. The drawer shows the score, the agent's verdict and the evidence.
3. **How the agent decided (0:50–1:30).** Open the trace tab and walk through its steps: the agent checked releases, saw conflicting commit data, pulled recent issues, found unanswered maintainer pings and concluded at risk. Point out that it chose those steps itself.
4. **Live run (1:30–2:00).** Hit "Investigate now" on a repo not yet investigated, or show the Lakeflow Job's last run graph if serving isn't ready. Show the new finding appear.
5. **Platform (2:00–2:30).** Unity Catalog lineage from the raw volume to findings. The UC functions list showing the agent's tools. The Lakeflow Job schedule.
6. **Proof (2:30–2:50).** The MLflow eval run, with at-risk recall and the improvement over the baseline formula.
7. **Close (2:50–3:00).** "An autonomous maintainer-risk analyst, built entirely on Databricks."

Record a backup video of the full demo by hour 19 in case the venue's wifi or the workspace fails.

## Risks and fallbacks

| Risk | Likelihood | Impact | Fallback |
| --- | --- | --- | --- |
| Workspace is Free Edition and lacks Model Serving, Vector Search or Apps | Medium | High | Run the agent from a notebook or job, drop find\_alternatives, and serve the frontend locally while reading the SQL warehouse |
| UC functions can't make outbound HTTP calls | Medium | Medium | Live-fetch tools become plain Python tools in the agent; data tools stay UC functions |
| GitHub rate limits or a slow pull | Medium | High | Pull in hour 2 and freeze; cut to 300 repos; cache every live fetch |
| Agent output fails the schema or hallucinates evidence | Medium | Medium | Structured output plus validation, one retry, then `inconclusive`; strip evidence that has no matching tool call |
| The agent is too slow for a live demo | Medium | Medium | Pre-run the full batch and keep one live investigation; show the job graph instead |
| Eval numbers come out bad | Low–Medium | Medium | Report them honestly next to the formula baseline, and show one fix made because of them |
| Map is slow with 500 glowing points | Low | Low | ECharts canvas renderer; turn off glow effects past 300 points |
| Running out of the 20 hours | High | High | Cut in this order: F13, F12, F11, Model Serving, F10. Never cut traces or eval |

## Open questions

- [ ] Does the hackathon provide a dataset or corpus? If so, it replaces Layer 1 ingestion.
- [ ] Which workspace do we get: Free Edition, a trial, or an organizer-provided full workspace? This decides whether Model Serving, Vector Search and Apps are available.
- [ ] What are the official judging criteria for Best Use of Databricks? Check them against the Users and judges assumption.
- [ ] Which Foundation Model API models are available in the workspace, and which handles tool calling best?
- [ ] Can UC Python functions make outbound HTTP calls in our workspace? Test this in hour 1.
- [ ] Team size and who owns each workstream.
- [ ] Exact start time, deadline, and demo length and format.
