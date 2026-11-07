# Open-Source Corpus Explorer PRD

Nov 6, 2026 · @Hi · Updated Nov 7, 2026

An interactive galaxy map of GitHub repositories where an autonomous Databricks agent finds critical open-source packages that are quietly dying, investigates them with governed tools, and shows its evidence. Built in 20 hours for HackCamp, targeting the Best Use of Databricks track.

## Problem and goal

The question: **which open-source packages that many people depend on are losing their maintainers?** GitHub shows stars and commits per repo, but nobody watches thousands of repos for the slow signs of abandonment: releases stopping, issues piling up, one maintainer left.

**Product goal:** an AI agent that watches a corpus of repos on its own, picks which ones look worrying, investigates them with real tools, and records a verdict with evidence. People explore the results on a galaxy map, with no chatbot.

**Hackathon goal:** win Best Use of Databricks. That means Databricks has to be the engine of the product, not just hosting: ingestion, governance, the agent's tools, tracing, evaluation and scheduling all run on the platform, and the demo shows each of them working.

**Not the goal:** a complete or real-time picture of all of GitHub. Track a frozen snapshot of 1,000 unique public GitHub repositories across the five core languages. This is a bounded sample, not all-of-GitHub coverage.

**Why scan obviously fine open-source repos?** The corpus is not only dying packages. Famous, intentional OSS projects (React, Vue, Flask, …) are **controls and hard cases**. Scanning them proves the agent does not cry wolf: a quiet mature line is not the same as abandonment. Example: [`vuejs/vue`](https://github.com/vuejs/vue) is the Vue 2 line (maintenance / successor elsewhere); [`vuejs/core`](https://github.com/vuejs/core) is where Vue 3 lives. Both belong in the map — one teaches “migrate / follow the successor,” the other “healthy, keep watching.” Without healthy and hard-case stars, the product is just a red-flag list with no calibration.

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

- 1,000 unique real repos scraped from GitHub by one Databricks-hosted Python notebook task in Lakeflow Jobs, then ingested through the existing Lakeflow pipeline into Delta, governed in Unity Catalog
- A baseline health score for every repo
- A tool-calling agent that triages and investigates flagged repos and writes structured verdicts
- Agent tools registered as Unity Catalog functions
- MLflow traces for every investigation, viewable from the app
- A galaxy map, a findings page and a repo drawer, hosted on Databricks Apps
- An eval run on a labelled set with a reported score

**Should-have (P1, once the must-haves work)**

- Repo categories and CWE vulnerability buckets for sorting and filtering the map and findings
- Natural-language map search that zooms to matching stars, powered by Vector Search

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
| F1 | Data scraping and repo ingestion | P0 must | One on-demand Databricks notebook retains curated controls and discovers additional public repos through paginated language searches, collects exactly 1,000 unique canonical repo IDs with real metrics, writes compatible JSON Lines chunks to the UC Volume, and feeds the existing bronze/silver/gold pipeline. Default publication requires all 1,000 successes and coverage of the five intended languages; failed attempts retain the previous active snapshot. The agent investigation budget remains separate |
| F2 | Baseline health score | P0 must | Gold rows use the MVP release/commit/activity formula below, with healthy, watchlist, at risk, or **ignored** status; uncollected signals remain unknown and are excluded from the score. Officially deprecated or archived-as-deprecated repos land in **ignored** (not scored as living risk). No maintainer-reply or contributor-history scrape is needed |
| F3 | Agent triage | P0 must | Given a budget N (default 20), the agent picks which repos to investigate and logs why it chose them. **Skip repos already marked `ignored`** — deprecated lines get no future PR-review / investigation budget |
| F4 | Agent investigation | P0 must | The agent calls at least 2 tools per repo, chosen by the model rather than a fixed sequence, and stops when it is confident or reaches 8 calls |
| F5 | Structured verdict | P0 must | Each investigation writes one `findings` row matching the schema in Agent design, with every evidence item pointing to a tool result |
| F6 | Reasoning trace | P0 must | Every investigation has an MLflow trace, and the repo drawer shows its tool calls and results in order |
| F7 | Galaxy map | P0 must | Renders all repos as stars clustered by language, sized by importance and coloured by health (**including gray ignored**); hover shows the name and score; click opens the drawer; 1,000 stars render smoothly |
| F8 | Findings page | P0 must | Lists findings sorted by severity, then importance; filters by language and risk **including an Ignored bin**; a row click opens that repo on the map |
| F9 | Evaluation | P1 should | The agent runs on 30–50 labelled repos; accuracy and false-positive rate are logged in MLflow and shown in the pitch |
| F10 | Scheduled autonomy | P2 stretch | After the demo works, optionally chain the existing scraping, pipeline and agent tasks in a Lakeflow Job, reusing frozen data for the demo. Recurring scraping is not required within the 20-hour build |
| F11 | Lineage view | P1 should | A Unity Catalog lineage screenshot or link from the raw volume to `findings` |
| F12 | Find alternatives | P2 if time | For an at-risk repo, the agent returns up to 3 similar healthy repos from Vector Search |
| F13 | Run-over-run memory | P2 if time | The agent reads its previous finding for each repo; the UI shows newly at risk and recovered badges |
| F14 | Natural-language map search | P1 should | The user types a natural-language query on the galaxy map; Databricks Vector Search matches it against repo name, description and topics, within the active filters. One match zooms to that star and opens the drawer; several matches zoom to fit them and dim the rest; zero matches shows "no matches" and leaves the map unchanged. Clearing the query restores the full map |
| F15 | Categories and vulnerability buckets | P1 should | Every repo has one of 6 categories (Front-end, Back-end, Machine learning, Database, Hardware/embedded, DevOps & infra) or `other`, and a list of CWE vulnerability buckets from its GitHub security advisories (see Pages and UX). The map and Findings sort and filter by both |

## Pages and UX

Two pages plus a slide-out drawer. Dark space theme, built in React with ECharts.

**Galaxy Map (`/`)**: the hero screen

- Full-screen star field. Each language gets a fixed cluster centre, and repos are scattered around it with a seeded random offset so positions stay the same between reloads.
- Star size = importance, the log of dependents (or stars if dependents are missing). Star colour = status: green healthy, amber watchlist, red at risk, **gray ignored**. A pulsing ring marks repos the agent investigated in the latest run. Ignored stars stay on the map for context but are visually de-emphasized (dim / no pulse).
- Top bar: repos tracked, healthy, watchlist, at risk, **ignored**, last agent run time.
- Filters: language, category, vulnerability bucket, status (including **Ignored**), "investigated only". Default map filter can hide ignored if cluttered; keep the bin available.
- Cluster toggle: group stars by programming language (default) or by category.
- Search box (F14): a natural-language query zooms to the repos Vector Search matches (one star: zoom and open the drawer; several: zoom to fit, dim the rest). It is a search, not a chatbot.
- Hover shows a tooltip with the name, score and status. Click opens the drawer.

**Findings (`/findings`)**: the agent's output

- One row per finding: repo, risk level, confidence, a one-line headline, investigated time, a "new" badge.
- Sorted by severity, then importance by default; other sorts: health score, importance, days since release, advisory count / max severity, programming language. Filters for language, category, vulnerability bucket and risk, including an **Ignored** bin. Default list focuses on healthy / watchlist / at risk; ignored is a separate filter tab or chip so judges can still open a deprecated example.
- Clicking a row jumps to the map with that star selected and the drawer open.
- Header strip: latest run stats, i.e. repos triaged, investigated, tool calls made, **ignored count**, and eval score.

**Repo drawer**: opens from either page

- Header: name, GitHub link, language, stars, dependents.
- Health gauge plus the collected metrics: days since last release, commits in the last 90 days vs the previous 90, and open issues/PR counts. Unanswered PRs, maintainer-response and contributor-share metrics show as unavailable until collected; missing data is not evidence of abandonment.
- Agent verdict: risk level, confidence, a short explanation, an evidence list, **recommended actions** (see below), and a successor/alternative repo if one applies.
- **"How the agent decided" tab:** the MLflow trace as a step list showing tool name, inputs, a result summary and a brief public decision summary when the model supplies one. Missing summaries are explicit; hidden provider reasoning is not shown.
- Previous verdict and its date, if one exists.
- Security advisories: GHSA ID, severity and vulnerability bucket for each. With none, show "No GitHub advisories", never "safe".

**Vulnerability buckets (F15)**: each advisory's CWE IDs map to one bucket; a repo carries every bucket its advisories hit. Buckets do not change the health score or the agent's verdict.

| # | Bucket | CWEs | Example |
| --- | --- | --- | --- |
| 1 | Code execution | 94, 77, 78 | Log4Shell |
| 2 | Unsafe deserialization | 502 | Python pickle or Java object loading |
| 3 | Memory safety | 787, 125, 416, 119 | Heartbleed |
| 4 | Injection | 89, 79, 91 | SQLi in an ORM, XSS in a template engine |
| 5 | Path traversal & file access | 22, 434, 59 | `../../` in archive extractors |
| 6 | Prototype pollution | 1321 | lodash, minimist |
| 7 | Denial of service | 1333, 400, 770 | Regex hangs in a parser |
| 8 | Data exposure | 200, 532, 312 | requests proxy header leak |
| 9 | Network & TLS | 918, 295, 601 | HTTP clients |
| 10 | Auth & access control | 287, 285, 862, 352 | Web frameworks, auth middleware |
| — | Other / unclassified | Anything unmapped or with no CWE | — |
| — | No GitHub advisories | Repo has no advisories published on GitHub | — |

**Recommended actions (by verdict)** — the point of investigating is a next step for the dependency owner, not a binary “alive/dead” stamp:

| Verdict | Typical situation | Actions the UI / agent should surface |
| --- | --- | --- |
| `healthy` | Active OSS the team already bets on (e.g. `vuejs/core`, `facebook/react`) | **No change.** Keep on the watchlist; re-score on the next scheduled run. Do not invent alternatives. |
| `watchlist` | Slowing cadence, aging releases, or rising concentration | **Monitor.** Pin a version policy, subscribe to releases, re-check after the next agent run; optional soft alternatives only if a clear successor exists. |
| `hard_case` / mature-quiet (eval label; often maps to `healthy` or `watchlist` in the agent) | Project is intentional OSS but quiet because it is “done,” in maintenance, or development moved (e.g. `vuejs/vue` → Vue 3 in `vuejs/core`) | **Clarify, don’t panic.** Prefer a **successor / migration** action over “abandonment.” For Vue 2: plan migration to Vue 3 (`vuejs/core`), not a random alternative framework. Not the same as deprecated → ignored. |
| `at_risk` | Still in use but maintainer exit, long silence, or thinning ownership — **not** an official deprecation | **Remediate.** Prefer official successor; else up to 3 healthier similar repos (`find_alternatives`); freeze upgrades until a replacement is chosen. Keep in triage for follow-up runs. |
| `ignored` | Officially **deprecated** (README / project status / archive-with-deprecation). Maintainers will not do future PR reviews on that line | **Park it.** One-time note + optional successor link, then **drop from future investigation and PR-review attention**. Frontend copy: “Deprecated — ignored for ongoing review.” Gray star; Ignored filter bin. |
| `inconclusive` | Conflicting tools / missing signals | **Gather more.** Do not recommend migration or ignore; flag for human review or a live-fetch stretch tool. |

**Deprecated → ignored rule:** if evidence shows the repo is deprecated (or archived *because* it is deprecated), the verdict is `ignored`, not `at_risk`. Rationale: there is nothing useful to keep reviewing — no future maintainer PR reviews — so the product stops spending agent budget on it. Still show the star once so the map explains why it left the living watchlist. Hard cases like `vuejs/vue` (successor-moved, not necessarily “deprecated, stop watching”) stay watchlist / migrate, not ignored, unless an explicit deprecation notice is found.

## Agent design

One tool-calling agent, built with Mosaic AI Agent Framework on a Foundation Model API model, makes its own decisions in two places: **which repos to investigate** and **which evidence to gather**. A fixed scoring pipeline feeds it, and it writes structured verdicts back to Delta.

**Loop for each run**

1. **Triage.** Read `gold_repo_health` plus the previous `findings`. **Exclude** repos whose latest finding or gold status is `ignored` (deprecated). Pick up to N remaining repos (default 20) by importance × risk, favouring repos whose score changed since the last run. Log the chosen list and a one-line reason for each.
2. **Investigate each pick.** Start from the repo's baseline metrics. Call tools in whatever order the model chooses. Dig deeper when signals conflict: low commits but steady releases may just mean the project is mature. Early-exit if tools show official deprecation → verdict `ignored`.
3. **Stop.** Stop when confidence is at least 0.7, after a deprecation/`ignored` decision, or after 8 tool calls, whichever comes first.
4. **Verdict.** Emit JSON matching the schema below. Code validates it, and an invalid output gets one retry before the repo is marked `inconclusive`.
5. **Persist.** `MERGE` into `findings`, keyed on (repo\_id, run\_id). The trace id is stored on the row. Writing `ignored` also sets gold `status = ignored` for that repo so later triage skips it.
6. **Memory.** On the next run, step 1 reads the previous verdicts, skips ignored repos, and the agent states what changed only for living bins.

**Tools**

| Tool | Type | Returns |
| --- | --- | --- |
| `get_repo_metrics(repo)` | UC SQL function over gold | Baseline metrics and score |
| `get_commit_trend(repo, weeks)` | UC SQL function over silver | Two 90-day commit totals and their change; actual weekly history is deferred; no invented weekly series |
| `get_release_history(repo)` | UC SQL function | Latest release date and days since it; full release history and inter-release gaps are deferred |
| `get_issue_backlog(repo)` | UC SQL function | Open issues and PR counts; response time and unanswered counts are unknown in the MVP |
| `get_contributor_concentration(repo)` (stretch) | UC SQL function | Disabled until real contributor data is collected |
| `fetch_recent_issues(repo, n)` (stretch) | GitHub fetch, cached to Delta | At most 5 issue titles; maintainer-reply analysis is deferred |
| `fetch_readme_signals(repo)` (stretch) | GitHub fetch, cached to Delta | README flags for "deprecated", "unmaintained", "archived", "use X instead"; at most 5 demo repos. A clear **deprecated** hit is enough to emit `ignored` and stop further tool spend |
| `get_previous_finding(repo)` | UC SQL function over findings | Last verdict and date |
| `find_alternatives(repo)` (P2) | Vector Search | Up to 3 similar healthy repos |

The required agent tools read the frozen snapshot and still support model-selected investigations with at least two tools. Live-fetch tools are optional: use Python inside the existing Databricks-hosted agent if attempted, without new serving infrastructure or an outbound-HTTP setup project.

**Ticket #6 implementation:** `databricks/src/setup/create_uc_tools.sql` registers five active snapshot tools plus an explicitly unavailable contributor-function compatibility entry. All results preserve JSON nulls; missing repos/findings return `found=false`. Release age is measured at collection time, commit percentage change is unknown when the previous count is zero, and unavailable response/contributor metrics are never estimated. The agent does not offer the contributor tool. Bundle job `uc_tools` checks the actual SQL against temporary edge-case fixtures before registration, then verifies registered functions against the live silver/gold tables. See the [README tool run instructions](README.md#agent-data-tools-ticket-6).

**Ticket #11 implementation:** each finding stores the trace ID captured from its own MLflow root span. All model calls (including retries/finalization) and full tool inputs/results are traced. `agent.trace_steps` stores the same trace as ordered JSON so the app can read it through the SQL warehouse; `get_finding_trace` provides the lookup contract. Public decision summaries and the verdict explanation support the UI; private provider reasoning is not exported. The `agent_run` job verifies MLflow retrieval and the persisted finding-to-steps link after investigation. The HTTP endpoint remains in ticket #12.

**Verdict schema**

```json
{
  "repo_id": "psf/requests",
  "risk_level": "healthy | watchlist | at_risk | ignored | inconclusive",
  "confidence": 0.0,
  "headline": "one line for the findings list",
  "explanation": "2-4 sentences",
  "evidence": [{"signal": "no release in 410 days", "tool": "get_release_history", "value": 410}],
  "changed_since_last": "newly_at_risk | recovered | unchanged | first_seen | newly_ignored",
  "recommended_actions": ["monitor_on_schedule"],
  "alternatives": ["org/repo"],
  "tool_calls": 5
}
```

`recommended_actions` is a short list of action codes the UI can render as chips/copy. Allowed codes for the hackathon:

| Code | When |
| --- | --- |
| `no_change` | Healthy control; stay on current major |
| `monitor_on_schedule` | Healthy or watchlist; wait for the next run |
| `pin_and_watch_releases` | Watchlist; tighten version policy |
| `migrate_to_successor` | Hard case / at-risk with a known successor (e.g. `vuejs/vue` → `vuejs/core`) |
| `replace_dependency` | At-risk with no single official successor; use `alternatives` |
| `ignore_deprecated` | Deprecated → `ignored`; stop future PR-review / agent attention |
| `human_review` | Inconclusive |

`alternatives` stays empty for healthy controls. For successor moves, put the official next repo first (prefer `vuejs/core` over unrelated frameworks when investigating `vuejs/vue`). For `ignored`, `alternatives` may still list a documented successor once; the primary action is still `ignore_deprecated`.

**Guardrails**

- Every evidence item must name a tool that was actually called in the trace. Code checks this, and unsupported claims are stripped before saving.
- A tool budget and a timeout per repo, so one repo can't burn the run.
- Low temperature for verdicts. The system prompt includes the scoring rubric so the LLM and the formula agree on what each level means.
- Do not recommend replacing a healthy or mature-quiet control with a random “similar” repo. Alternatives are for remediation or documented successors only.
- **Deprecated ≠ at-risk.** Once deprecated evidence is confirmed, emit `ignored` + `ignore_deprecated`, and never re-triage that repo for “is it dying?” — maintainers will not review future PRs there.
- The agent is read-only towards GitHub. It never opens issues or comments anywhere.

## Data sources and ingestion

The hackathon scrape runs on Databricks using the existing workspace, catalog, Volume and bundle. Use GitHub APIs rather than building a browser crawler. The target is a working frozen dataset early in the 20-hour project, with minimal new infrastructure.

**Fast setup and time budget (estimates, assuming workspace access)**

- **Setup: 30–60 minutes**, included in the scraping budget: confirm the existing workspace profile, reuse `hackcamp.raw.github`, store one GitHub token in the existing `hackcamp/github_token` secret, deploy and run one notebook job. If access or token setup is blocked, continue integration with clearly labelled sample data while fixing access; do not claim it is a real scrape.
- **Expanded scraping target: 1,000 repos**, reusing the existing notebook, token and workspace. Run a 5-repo smoke test before the full collection. Keep metrics limited to the existing scalar snapshot fields plus description, topics and the F15 advisory pass; file writes are batched to keep setup and execution small.
- **Pipeline, scoring and tools (#4–#6): 2 hours total** of incremental integration using the existing implementation. Do not rebuild already working setup or tables.
- **Data gate: by hour 5**, one data owner should have a real snapshot in gold and working snapshot tools. This is a planning budget, not a guaranteed runtime; the rest of the team's 20-hour build remains for the agent, app, evaluation, integration and demo.
- Keep the previously validated snapshot available until the expanded 1,000-repo run passes. A failed expanded run must not silently publish a smaller corpus. Keep optional enrichment and full histories out of the 20-hour build.

**Layer 1: one notebook and a frozen snapshot (P0)**

- **Execution:** one Python notebook under `databricks/src/ingest/`, one on-demand Lakeflow Job in the existing bundle. Actual requests execute on Databricks. Reuse the current Python environment and existing libraries or the standard library; no new crawler framework, service or cluster-management layer.
- **Repo list:** preserve the 100 curated at-risk, healthy and hard-case examples, then add public, non-fork repos from paginated searches for Python, JavaScript, Go, Rust and Java (`stars:>=100`, sorted by stars). Interleave languages and deduplicate both requested IDs and canonical IDs returned by GitHub. Discover a spare candidate pool (default 1,200 IDs for a 1,000-repo run) so redirects/unavailable repos can be replaced without lowering the publication target. This is a star-ranked sample, not a representative prevalence study. Keep successor examples such as `vuejs/vue` available for the risk/ignored-bin behavior elsewhere in this PRD.
- **Metrics:** use small GitHub GraphQL batches (start with 5–10 repos) for name, owner, language, stars, archive flag, last push, latest release, commit totals since 90 and 180 days, open issue/PR counts, description and topics. Derive `commits_prev_90d` as the 180-day total minus the 90-day total using a fixed collection timestamp. Do not fetch per-commit or per-comment histories.
- **Advisories (F15):** one REST call per repo to `GET /repos/{owner}/{repo}/security-advisories`, keeping GHSA ID, severity, CWE IDs and published date (about 1,000 calls, within the token's hourly limit). Run it as a separate pass with bounded retries. This covers only advisories published through GitHub, so projects that report elsewhere (e.g. Django) show none; matching repos to packages in GitHub's global advisory database is deferred.
- **Category (F15):** a one-time `ai_query()` over description and topics, constrained to the 6 fixed categories plus `other`.
- **Importance:** use `log10(stars + 1)` for the MVP. deps.dev, dependents mapping, OpenSSF and Criticality Score are deferred; no second source or credential is required.
- **Auth:** read the GitHub token from `dbutils.secrets.get("hackcamp", "github_token")`. Never print or save the token.
- **Landing:** keep the existing `repo_id`, `payload`, `pulled_at` envelope under `/Volumes/hackcamp/raw/github/repos/`. Write newline-delimited JSON chunks with up to 100 records per file (10 files for 1,000 repos), compatible with the existing Auto Loader JSON reader. Stage a frozen copy and per-file record manifest, retain the previous input, then publish only the validated dataset. Keep summaries outside `repos/`, including target, candidate/attempt counts, canonical successes, failures and collection time. Rerunning may refetch the corpus; durable checkpoints remain deferred.
- **Failures:** sequential metric batches of 10 repos, request timeouts and at most 3 attempts per batch; pace discovery requests separately. Honour retry/reset headers within a bounded wait. The default run must collect 1,000 unique real repos across the intended languages before publishing; authentication failures, rate-limit exhaustion or fewer than 1,000 successes leave the old active snapshot unchanged and save a failure summary. The five-repo smoke mode always uses `publish=false`.
- **Handoff:** manually run the existing `repo_health` pipeline after a successful scrape; automatic chaining is optional. Expectations and latest-per-repo selection stay in the existing pipeline. Ensure the real run does not mix generated seed payloads into its final demo snapshot.
- **Freeze and verify:** retain the real snapshot, notebook/job run and summary, and verify bronze/silver/gold counts reconcile with successes and dropped rows. Run the demo from frozen data. Seeded JSON is a clearly labelled development fallback, never evidence of a successful real scrape.

**Scraping implementation:** `databricks/src/ingest/scrape_github_repos.py`, bundle job `github_scrape`, now defaults to `repo_limit=1000`, `minimum_repos=1000`, and `batch_size=10`. A 5-repo smoke run skips discovery and leaves active input untouched. Expanded runs retain curated IDs, discover spare candidates, refill unavailable/redirected IDs until 1,000 distinct successes, and write JSON Lines chunks plus a record-count manifest under `snapshots/<run_id>/`. Archive the previous input before publication. Verify actual record counts and unique IDs, rather than equating file count with repo count. Refresh the existing ingestion pipeline after publication; stable filenames require a full refresh on subsequent replacement snapshots. See the [README run instructions](README.md#github-scraping-ticket-3).

**Layer 2: targeted fetches (stretch only, ticket #7)**

- Required investigations use the snapshot-backed UC tools; they do not depend on live HTTP.
- Only after the full demo works, spend at most 30 minutes adding README retrieval for up to 5 demo repos inside the Databricks-hosted agent, cached in the existing `agent.tool_cache` table.
- Recent issue titles (at most 5 per repo) are a further stretch. Maintainer-reply classification, contributor concentration and comprehensive histories are deferred. Cached-only demo playback must work without GitHub access.

**Deferred scraping work:** external enrichment, full release/weekly commit/contributor/comment histories, worker pools, durable resume/checkpoint frameworks, recurring scraping, coverage beyond 1,000 repos and production monitoring. These are not acceptance gates for the hackathon.

**If the hackathon provides a usable corpus,** load it with the same notebook/Volume contract and record its provenance; keep downstream schemas and tools unchanged.

## Data model

Everything lives in catalog `hackcamp`, in schemas `raw`, `bronze`, `silver`, `gold`, `agent` and `tools`.

| Table | Grain | Key columns |
| --- | --- | --- |
| `bronze.github_repos_raw` | One API response per repo per pull | `repo_id`, `payload` (JSON), `pulled_at` |
| `silver.repos` | One row per repo | `repo_id`, `name`, `owner`, `language`, `stars`, `is_archived`, `pushed_at`, `last_release_at`, `commits_90d`, `commits_prev_90d`, `open_issues`, `open_prs`, `contributors`, `dependents`, `description`, `topics` |
| `silver.repo_advisories` | One row per GitHub security advisory per repo | `repo_id`, `ghsa_id`, `severity`, `cwes`, `published_at` |
| `gold.repo_health` | One row per repo per run | `repo_id`, `run_id`, `health_score`, `status` (`healthy` \| `watchlist` \| `at_risk` \| `ignored`), `importance`, `days_since_release`, `commit_trend_pct`, `category`, `vuln_buckets` (array), `advisory_count`, `max_severity`, `x`, `y`, `scored_at` |
| `agent.findings` | One row per investigated repo per run | `repo_id`, `run_id`, `risk_level` (includes `ignored`), `confidence`, `headline`, `explanation`, `evidence` (array of structs), `changed_since_last`, `recommended_actions`, `alternatives`, `tool_calls`, `trace_id`, `investigated_at` |
| `agent.runs` | One row per agent run | `run_id`, `started_at`, `repos_triaged`, `repos_investigated`, `tool_calls_total`, `model`, `eval_score` |
| `agent.trace_steps` | One app-readable trace per investigation | `trace_id`, `repo_id`, `run_id`, `payload` (ordered decision/tool steps as JSON), `created_at` |
| `agent.tool_cache` | One row per live fetch | `tool`, `args_hash`, `response`, `fetched_at` |
| `agent.eval_labels` | One row per labelled repo | `repo_id`, `label`, `label_source`, `notes` |

The Vector Search index for F12 and F14 syncs from a source table keyed on `repo_id` with Change Data Feed enabled, embedding name, description and topics.

`x` and `y` are precomputed in gold (the language's cluster centre plus a seeded offset), so the frontend draws them as they are.

## Health scoring

The baseline score is a simple weighted formula computed in the gold layer. It decides star colour and feeds triage. The agent's verdict can override it, and the drawer shows both.

For the hackathon, use only the three cheap signals already collected. With all three available:

```latex
\text{health} = 100\,\frac{30\,s_{\text{release}} + 25\,s_{\text{commits}} + 10\,s_{\text{activity}}}{65}
```

Exclude unavailable signals and renormalize over the weights actually present. Keep missing metrics nullable rather than converting them to zero, 999 days, a reply-rate estimate or a bus-factor estimate. If no signal is available, return a null score and a watchlist status with an explicit insufficient-data explanation; the agent must be inconclusive without evidence. A zero previous commit count makes the trend unavailable; it does not establish decline. The original issue-response and bus-factor terms below are deferred until measured data exists, and do not contribute to the MVP score.

Each sub-score runs from 0 to 1:

| Sub-score | Signal | 1.0 when | 0.0 when |
| --- | --- | --- | --- |
| s\_release | Days since last release | 90 days or less | 540 days or more (linear in between) |
| s\_commits | commits\_90d ÷ commits\_prev\_90d | 1.0 or more | 0.2 or less |
| s\_issues (deferred) | Share of PRs and issues with a maintainer reply | 80% or more | 20% or less |
| s\_bus (deferred) | 1 − top contributor's share of the last 100 commits | 0.6 or more | 0.1 or less |
| s\_activity | Days since last push | 30 days or less | 365 days or more |

- **Thresholds:** 70 or more is healthy, 40 to 69 is watchlist, below 40 is at risk. **Ignored overrides the formula:** if the repo is officially deprecated (README/project-status evidence, or archived *as* a deprecated line), set `status = ignored`, leave or null the numeric score for display, and exclude it from living triage. A bare archive without a deprecation story may still be `at_risk` until the agent confirms deprecate-and-park.
- **Importance** (star size and triage weight) = log10(stars + 1) in the MVP. Dependents-based importance is deferred. Ignored repos keep importance for map sizing but get **zero triage priority**.
- **Triage priority** = importance × (100 − health) for non-ignored rows only, boosted when the score dropped by 10 or more points since the last run.
- The weights are a first guess. Tune them against the labelled eval set in hour 15, and note the final weights in the pitch.

## Databricks services

The core services carry the Best Use of Databricks story; additional services support hosting, scheduling and optional features. Service names are from memory as of mid-2026, so check them against current docs.

**Workspace:** trial / organiser-provided full workspace (profile `school`), confirmed in hour-1 probes — not Free Edition. Model Serving (Foundation Model endpoints), Vector Search, Databricks Apps, UC outbound HTTP, and serverless SQL warehouse are all available. Plan to host the React app + thin API on Databricks Apps and keep Apps / Vector Search / Model Serving in scope; do not design around Free Edition limits.

| Service | Role in this product | Why judges care | Priority |
| --- | --- | --- | --- |
| Lakeflow Declarative Pipelines (formerly DLT) | Bronze to silver to gold, with Auto Loader and expectations | Managed incremental ETL with data-quality metrics built in | Core |
| Delta Lake | Every table; `MERGE` for findings; time travel to compare runs | Agent memory is just Delta history | Core |
| Unity Catalog | Namespace, permissions, lineage across tables, functions and models | One governed lineage from raw API JSON to an AI verdict | Core |
| UC functions | The agent's data tools | The agent's tools are governed, discoverable catalog objects | Core |
| Foundation Model APIs | The model behind the agent (`databricks-meta-llama-3-3-70b-instruct`; fallback `databricks-llama-4-maverick`) | No model hosting to manage | Core |
| Mosaic AI Agent Framework | Agent loop, logged as an MLflow model | Platform-native agent rather than a script calling an API | Core |
| MLflow Tracing and GenAI evaluation | Per-investigation traces; eval on the labelled set with LLM judges and custom metrics | Shows how the agent reasons and how well it performs | Core |
| Lakeflow Jobs | Runs one on-demand scraping notebook; pipeline runs may be started manually | Source collection runs on Databricks, with visible task history | Core for F1 notebook; Stretch for F10 chaining/scheduling |
| Databricks Apps + SQL warehouse | Hosts the React app and a thin Python API querying gold and findings | The whole product lives inside the workspace | Should |
| Model Serving | Agent as an endpoint, for the live demo investigation | One-click "investigate now" from the UI | If time |
| Vector Search | Index over repo descriptions for find\_alternatives and natural-language map search | Retrieval as an agent tool and a map filter, not a chatbot | If time |
| `ai_query()` | Classify each repo into one of 6 categories (F15); batch one-liners for repos not investigated (if time) | LLM inference in plain SQL at table scale | Should |

**Skipped on purpose:** Genie (a chatbot, out of scope), Lakebase (Delta through a SQL warehouse is fast enough), AI/BI dashboards (the custom UI covers it).

## Architecture

&#91;embedded content: architecture · data, agent and app inside one workspace\]

GitHub API → Databricks scraping task (Lakeflow Jobs) → frozen JSON in a UC Volume → Auto Loader / Lakeflow pipeline → bronze → silver → gold. The agent reads gold, calls governed UC tools and Databricks-hosted live-fetch tools, and writes findings and traces, which the app reads. Unity Catalog governs the stored data and tools. Demo runs reuse the frozen snapshot and cached tool responses.

## Evaluation and success metrics

The pitch includes one measured number: how often the agent's verdict matches ground truth on repos whose status we already know.

**Labelled set (30–50 repos, built in hours 9–10)**

- **At risk:** thinning maintenance or silence without an official “stop using this” notice — still worth remediating if you depend on it.
- **Ignored:** official deprecation / unmaintained notices where maintainers will not review future PRs (e.g. `request/request`, Moment’s legacy status). Ground truth expects `ignored`, not endless `at_risk` re-investigation.
- **Healthy:** well-known projects with releases in the last 90 days and several active maintainers (controls — scanning them is intentional so false-positive rate is measurable).
- **Hard cases:** mature or "done" projects that are quiet but fine, successor-moved lines (e.g. `vuejs/vue` while Vue 3 continues in `vuejs/core`), and projects that recently revived. Ground truth is **not** “at risk” or “ignored” solely because commit volume dropped.
- **Label source** goes in `eval_labels.label_source`, for example a link to the deprecation notice or the successor repo README. Eval `label` values: `at_risk`, `ignored`, `healthy`, `hard_case`.

**How to score**

- The `eval_run` job runs the same agent on every labelled repo that has a gold row. Eval runs don't write to `findings`, so they never show up on the map.
- Custom metrics, logged to MLflow: verdict accuracy, at-risk precision and recall, a false-alarm rate on the hard cases, the inconclusive rate and median tool calls. Scoring is binary on "is it at risk?": hard cases count as negatives, and an `inconclusive` verdict counts as not at risk.
- An MLflow GenAI LLM judge checks that each explanation is grounded in the trace's tool outputs.
- The baseline formula alone is scored too, and the gap is logged as `agent_minus_formula_accuracy`, so the pitch can say how much the agent adds over the formula.

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

1. **Hook (0:00–0:20).** "Your app depends on hundreds of packages. Which ones are dying?" Open the galaxy map with the verified collected repo count (target 1,000), with red ones scattered through the clusters.
2. **The map (0:20–0:50).** Type "unmaintained Python HTTP clients" and the map zooms to the matches; filter by the Injection bucket. Filter to at-risk. Hover a big red star and click it. The drawer shows the score, the agent's verdict and the evidence.
3. **How the agent decided (0:50–1:30).** Open the trace tab and walk through its steps: the agent checked releases, saw conflicting commit data, compared archive status and last push, and concluded at risk using the collected evidence. Live README or issue fetches are only shown if the stretch work was completed. Point out that it chose those steps itself.
4. **Live run (1:30–2:00).** Hit "Investigate now" on a repo not yet investigated, or show the Lakeflow Job's last run graph if serving isn't ready. Show the new finding appear.
5. **Platform (2:00–2:30).** Show the successful Databricks scraping task and its raw Volume output, Unity Catalog lineage from the raw volume to findings, and the UC functions list showing the agent's tools. Show the Lakeflow Job schedule if implemented.
6. **Proof (2:30–2:50).** The MLflow eval run, with at-risk recall and the improvement over the baseline formula.
7. **Close (2:50–3:00).** "An autonomous maintainer-risk analyst, built entirely on Databricks."

Record a backup video of the full demo by hour 19 in case the venue's wifi or the workspace fails.

## Risks and fallbacks

| Risk | Likelihood | Impact | Fallback |
| --- | --- | --- | --- |
| Databricks Apps deploy or auth hiccup during the demo | Low | Medium | Keep a local Vite + FastAPI fallback against the same SQL warehouse; show Apps URL when healthy |
| UC live-fetch tools fail under load or rate limits | Low | Medium | Fall back to cached Volume JSON / plain Python tools; data tools stay UC functions |
| GitHub rate limits or a slow pull | Medium | High | Run a 5-repo smoke test, pace discovery, use bounded retries and a failure summary; retain the previous validated snapshot unless all 1,000 unique repos are collected; replay frozen data for the demo |
| Agent output fails the schema or hallucinates evidence | Medium | Medium | Structured output plus validation, one retry, then `inconclusive`; strip evidence that has no matching tool call |
| The agent is too slow for a live demo | Medium | Medium | Pre-run the full batch and keep one live investigation; show the job graph instead |
| Eval numbers come out bad | Low–Medium | Medium | Report them honestly next to the formula baseline, and show one fix made because of them |
| GitHub advisory coverage is partial | High | Medium | Label the gap as "No GitHub advisories", never "safe"; package matching against the global advisory database stays a stretch |
| Advisory pass slows the scrape (1,000 extra calls) | Medium | Medium | Separate pass with bounded retries; keep the previous snapshot if it fails |
| Map is slow with 1,000 glowing points | Low | Low | ECharts canvas renderer; turn off glow effects past 300 points |
| Running out of the 20 hours | High | High | Cut in this order: F13, F12, F11, Model Serving, F10. Never cut traces or eval |

## Open questions

- [x] Workspace edition — **trial / full workspace** (`school`). Model Serving, Vector Search, Apps, and UC outbound HTTP all confirmed (see `.docs/HOUR1_CHECKS.md`).
- [x] Foundation Model tool calling — lock agent on `databricks-meta-llama-3-3-70b-instruct`; fallback `databricks-llama-4-maverick`.
- [x] UC Python outbound HTTP — works (`http_probe` → 200); live-fetch tools may be UC Python functions.
- [ ] Does the hackathon provide a dataset or corpus? If so, it replaces Layer 1 ingestion.
- [ ] What are the official judging criteria for Best Use of Databricks? Check them against the Users and judges assumption.
- [ ] Team size and who owns each workstream.
- [ ] Exact start time, deadline, and demo length and format.
