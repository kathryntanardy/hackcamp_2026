# Open-Source Corpus Explorer PRD

Nov 6, 2026 · @Hi · Updated Nov 7, 2026

An interactive galaxy map of GitHub repositories where an autonomous Databricks agent finds critical open-source packages that are quietly dying, investigates them with governed tools, and shows its evidence. Built in 20 hours for HackCamp, targeting the Best Use of Databricks track.

## Problem and goal

The question: **which open-source packages that many people depend on are losing their maintainers?** GitHub shows stars and commits per repo, but nobody watches thousands of repos for the slow signs of abandonment: releases stopping, issues piling up, one maintainer left.

**Product goal:** an AI agent that watches a corpus of repos on its own, picks which ones look worrying, investigates them with real tools, and records a verdict with evidence. People explore the results on a galaxy map, with no chatbot.

**Hackathon goal:** win Best Use of Databricks. That means Databricks has to be the engine of the product, not just hosting: ingestion, governance, the agent's tools, tracing, evaluation and scheduling all run on the platform, and the demo shows each of them working.

**Not the goal:** a complete or real-time picture of all of GitHub. Track a frozen snapshot of 1,000 unique public GitHub repositories across the five core languages. This is a bounded sample, not all-of-GitHub coverage.

**Why scan obviously fine open-source repos?** The corpus is not only dying packages. Famous, intentional OSS projects (React, Vue, Flask, …) are **controls and hard cases**. Scanning them proves the agent does not cry wolf: a quiet mature line is not the same as abandonment. Example: [`vuejs/vue`](https://github.com/vuejs/vue) is the Vue 2 line (maintenance / successor elsewhere); [`vuejs/core`](https://github.com/vuejs/core) is where Vue 3 lives. Healthy and mature-quiet repos belong in the map only while they remain eligible for monitoring. A documented successor can guide migration, but confirmed deprecated lines are filtered out even when they were curated controls. Without healthy and hard-case stars, the product is just a red-flag list with no calibration.

## Users and judges

| Who | What they want | What we show them |
| --- | --- | --- |
| Engineering lead picking dependencies | "Is this library safe to bet on?" | The repo's health, the agent's verdict, a healthier alternative |
| Open-source program office or security team | A watchlist of risky dependencies | The Findings drawer, sorted by severity, with what changed since the last run |
| Funders and maintainers | Which important projects need help | Critical, at-risk stars on the map |
| **Hackathon judges (Best Use of Databricks)** | Deep, essential use of the platform | Live traces, Unity Catalog lineage, the eval score, the scheduled job |

Assumption about judging (to confirm against the track's rules): judges reward Databricks being essential to the product, native AI and agent features used properly, and evidence that the system works. They don't reward a long list of services.

## Scope

**Must-have (the demo fails without these)**

- 1,000 unique eligible real repos, after confirmed deprecation exclusions, scraped from GitHub by one Databricks-hosted Python notebook task in Lakeflow Jobs, then ingested through the existing Lakeflow pipeline into Delta, governed in Unity Catalog
- A baseline health score for every eligible repo; confirmed deprecated repos are excluded from the active product corpus
- A tool-calling agent that triages and investigates flagged repos and writes structured verdicts
- Agent tools registered as Unity Catalog functions
- MLflow traces for every investigation, viewable from the app
- A galaxy map with a Findings drawer and a repo drawer, hosted on Databricks Apps
- An eval run on a labelled set with a reported score

**Should-have (P1, once the must-haves work)**

- Repo categories and CWE vulnerability buckets for sorting the map and filtering findings
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
| F1 | Data scraping and repo ingestion | P0 must | One on-demand Databricks notebook retains curated controls and discovers additional public repos through paginated language searches, collects exactly 1,000 unique eligible canonical repo IDs with real metrics after filtering confirmed deprecated repos, writes compatible JSON Lines chunks to the UC Volume, and feeds the existing bronze/silver/gold pipeline. Default publication requires all 1,000 eligible successes and coverage of the five intended languages; excluded candidates are replaced and recorded separately; failed attempts retain the previous active snapshot. The agent investigation budget remains separate |
| F2 | Baseline health score | P0 must | Eligible gold rows use the MVP release/commit/activity formula below, with healthy, watchlist or at risk status; uncollected signals remain unknown and are excluded from the score. Confirmed deprecated repos, including curated entries in `deprecated_repos.py`, are excluded before scoring and serving. Legacy `ignored` rows are internal exclusion records, not a user-facing risk category. Archive status alone is not proof of deprecation. No maintainer-reply or contributor-history scrape is needed |
| F3 | Agent triage | P0 must | Given a budget N (default 10), the agent picks which repos to investigate and logs why it chose them. **Exclude confirmed deprecated repos**, including legacy `ignored` records, before selecting candidates; they receive no future investigation budget |
| F4 | Agent investigation | P0 must | The agent calls at least 2 tools per eligible repo, chosen by the model rather than a fixed sequence, and stops when it is confident or reaches 8 calls. Confirmed deprecation is an early-exit exception: record the exclusion and stop without a public finding |
| F5 | Structured verdict | P0 must | Each investigation writes one `findings` row matching the schema in Agent design, with every evidence item pointing to a tool result |
| F6 | Reasoning trace | P0 must | Every investigation has an MLflow trace, and the repo drawer shows its tool calls and results in order |
| F7 | Galaxy map | P0 must | Renders eligible repos as nodes in vulnerability-bucket flowers, sized by importance; each flower label shows High / Med / Low counts from maintainer health status (`at_risk` / `watchlist` / `healthy`), not advisory severity—High means most vulnerable; hover a level highlights matching nodes, click zooms to fit that flower centered in the visible map (sidebar-aware); the repo drawer starts closed—click a node to open that repo, click a flower category or High/Med/Low chip to open a filtered list for that bucket/band, click empty map (not a drag) to close; deprecated repos have no node; 1,000 nodes render smoothly |
| F8 | Findings drawer | P0 must | The Findings tab opens a slide-out drawer over the map listing findings sorted by severity, then importance; filters by language and risk; the list is server-paginated at 50 rows per page (`limit`/`offset` on `/api/findings`); deprecated repos and historical findings for them are excluded; a row click selects that repo on the map and opens its detail in the drawer |
| F9 | Evaluation | P1 should | The agent runs on 30–50 labelled repos; accuracy and false-positive rate are logged in MLflow and shown in the pitch |
| F10 | Scheduled autonomy | P2 stretch | The `scheduled_autonomy` Lakeflow Job runs daily at 10:00 Pacific: the `repo_health` pipeline refresh, then the agent run, on the frozen snapshot. Scraping stays a separate on-demand job; recurring scraping is not required within the 20-hour build |
| F11 | Lineage view | P1 should | A Unity Catalog lineage screenshot or link from the raw volume to `findings` |
| F12 | Find alternatives | P2 if time | For an at-risk repo, the agent returns up to 3 similar healthy repos from Vector Search |
| F13 | Run-over-run memory | P2 if time | The agent reads its previous finding for each repo; the UI shows newly at risk and recovered badges |
| F14 | Natural-language map search | P1 should | The user types a natural-language query on the galaxy map; Databricks Vector Search matches it against repo name, description, topics and advisory summaries. One match zooms to that star and opens the drawer; several matches zoom to fit them and dim the rest; zero matches shows "no matches" and leaves the map unchanged. Clearing the query restores the full map |
| F15 | Categories and vulnerability buckets | P1 should | Every repo has one of 6 categories (Front-end, Back-end, Machine learning, Database, Hardware/embedded, DevOps & infra) or `other`, and a list of CWE vulnerability buckets from its GitHub security advisories (see Pages and UX). The map lays out flowers by vulnerability bucket by default, with category and bucket facet filters plus a cluster toggle (vulnerabilities / language `x,y` / category `cat_x,cat_y`); Findings filters by category, bucket, language and risk, and sorts by severity, health score, importance, days since release, advisory count / max severity / max CVSS, or language |

## Pages and UX

One map screen plus slide-out drawers. Built in React with a canvas map.

**Galaxy Map (`/`)**: the hero screen

- Full-screen map of vulnerability-bucket flowers. Repos that share a CWE vulnerability bucket sit on one flower; nodes are uniform in that flower's colour until a severity level is focused.
- Node size = importance, the log of dependents (or stars if dependents are missing). Nodes remain steady after investigation. Deprecated repos are absent, including when historical rows still exist.
- Each flower label lists **High / Med / Low** counts from **maintainer health status**, not GitHub advisory severity: High = `at_risk`, Med = `watchlist`, Low = `healthy`. Hovering a level highlights matching nodes on that flower; clicking a level zooms so the whole flower fits the viewport and opens the drawer filtered to that band. Clicking the category name opens the drawer filtered to the whole flower. Users looking for vulnerable packages use High.
- Advisory severity and CVSS stay on the repo drawer and Findings sorts; they do not drive the map High / Med / Low chips.
- The drawer starts closed. Click a node to slide it open on that repo and center the star in the remaining map (not under the drawer); click a flower to open a filtered list and frame that flower the same way. Click empty map whitespace to close it (a pan/drag does not close). The Findings tab keeps the map visible and opens the Findings drawer by default.
- Map facet bar (F15): category and vulnerability-bucket filters, plus a cluster toggle for vulnerability flowers vs language (`x`,`y`) vs category (`cat_x`,`cat_y`) scatter. No corpus totals chrome; the navbar stays brand and page tabs only. Deprecated repos stay out of the map and list by serving rules, with no Ignored tab, chip or opt-in display.
- Search box (F14): a natural-language query zooms to the repos Vector Search matches (one star: zoom and open the drawer; several: zoom to fit, dim the rest). It is a search, not a chatbot.
- Hover shows a tooltip with the name, score and status. Click selects the x and opens that repo in the drawer; selection is indicated by the x itself, without an enclosing circle.
- Manual zoom, node selection, flower focus and search share a maximum scale based on the Figma **Zoomed in** design, reduced to fit the actual map viewport beside the drawer. Selecting a repo frames its whole flower and label; repeated selection cannot zoom further. Flower labels stay compact and move below the flower as the map zooms in. The drawer uses compact spacing and text in smaller windows.

**Findings drawer**: the agent's output over the map

- Opened by the Findings tab; the galaxy map stays underneath.
- One row per finding: repo, risk level, confidence, a one-line headline, investigated time, a "new" badge.
- Server-paginated: the API returns 50 findings per page with a total count; changing page, sort or filters fetches that slice only (`sort`, `category`, `vuln_bucket`, `language`, `risk` on `/api/findings`).
- Sorted by severity, then importance by default; other sorts: health score, importance, days since release, advisory count / max severity / max CVSS, programming language. Filters for language, category, vulnerability bucket and risk. Only eligible repos appear; deprecated repos cannot be restored through a filter, search result or historical finding.
- Clicking a row selects that star on the map and opens its detail in the same drawer stack; back returns to the findings list.
- Header strip: latest run stats, i.e. eligible repos triaged, investigated and tool calls made. Exclusion counts remain in operational logs rather than product risk totals.

**Repo drawer**: opens from the map or from a Findings row

- Header: name, GitHub link, language, stars, dependents.
- Health gauge plus the collected metrics: days since last release, commits in the last 90 days vs the previous 90, and open issues/PR counts. Unanswered PRs, maintainer-response and contributor-share metrics show as unavailable until collected; missing data is not evidence of abandonment.
- Agent verdict: risk level, confidence, a short explanation, an evidence list, **recommended actions** (see below), and a successor/alternative repo if one applies.
- **"How the agent decided" tab:** the MLflow trace as a step list showing tool name, inputs, a result summary and a brief public decision summary when the model supplies one. Missing summaries are explicit; hidden provider reasoning is not shown.
- Previous verdict and its date, if one exists.
- Security advisories: GHSA ID, CVE ID, severity, CVSS, summary and vulnerability bucket for each. With none, show "No GitHub advisories", never "safe"; if the advisory fetch failed, show "Advisories unavailable".

**Vulnerability buckets (F15)**: each advisory's CWE IDs map to one bucket; a repo carries every bucket its advisories hit. Buckets lay out the galaxy map flowers and support Findings filters. They do not change the health score or the agent's verdict, and the flower High / Med / Low chips still count health status within the bucket (`at_risk` / `watchlist` / `healthy`), not advisory severity.

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
| — | No GitHub advisories | Fetch succeeded and the repo has no advisories published on GitHub | — |

**Recommended actions (by verdict)** — the point of investigating is a next step for the dependency owner, not a binary “alive/dead” stamp:

| Verdict | Typical situation | Actions the UI / agent should surface |
| --- | --- | --- |
| `healthy` | Active OSS the team already bets on (e.g. `vuejs/core`, `facebook/react`) | **No change.** Keep on the watchlist; re-score on the next scheduled run. Do not invent alternatives. |
| `watchlist` | Slowing cadence, aging releases, or rising concentration | **Monitor.** Pin a version policy, subscribe to releases, re-check after the next agent run; optional soft alternatives only if a clear successor exists. |
| `hard_case` / mature-quiet (eval label; often maps to `healthy` or `watchlist` in the agent) | Project is intentional OSS but quiet because it is “done,” in maintenance, or development moved (e.g. `vuejs/vue` → Vue 3 in `vuejs/core`) | **Clarify, don’t panic.** Prefer a **successor / migration** action over “abandonment.” For Vue 2: plan migration to Vue 3 (`vuejs/core`), not a random alternative framework. Confirmed deprecated lines are excluded instead of being offered as hard cases. |
| `at_risk` | Still in use but maintainer exit, long silence, or thinning ownership — **not** an official deprecation | **Remediate.** Prefer official successor; else up to 3 healthier similar repos (`find_alternatives`); freeze upgrades until a replacement is chosen. Keep in triage for follow-up runs. |
| Excluded (internal only; legacy `ignored`) | Official deprecation confirmed by a maintainer notice or a curated entry with a source | **Filter out.** Remove from the active map, findings, search, recommendations and displayed counts; retain evidence only for audit. Do not render a gray star, drawer or Ignored bin. |
| `inconclusive` | Conflicting tools / missing signals | **Gather more.** Do not recommend migration or ignore; flag for human review or a live-fetch stretch tool. |

**Deprecated → excluded rule (supersedes #34):** confirmed deprecated repos are outside the active product corpus. Filter them before scoring, triage and serving; do not retain them as visible `ignored` stars or findings. Require a repo-specific maintainer deprecation notice or a curated source-backed entry. A keyword hit, archive flag, low activity, legacy status or successor alone is insufficient. If deprecation is discovered during investigation, stop, retain the source and exclusion reason internally, and suppress that repo and its historical findings from all product surfaces. Quiet but maintained repos remain eligible. Exclusions can be reversed only after verified evidence that the deprecation was withdrawn or recorded incorrectly.

## Agent design

One tool-calling agent, a Databricks notebook loop that calls a Foundation Model API model through its OpenAI-compatible endpoint, makes its own decisions in two places: **which repos to investigate** and **which evidence to gather**. A fixed scoring pipeline feeds it, and it writes structured verdicts back to Delta.

**Loop for each run**

1. **Triage.** Read `gold_repo_health` plus the previous `findings` and source-backed exclusion records. **Exclude** confirmed deprecated repos, including compatible legacy `ignored` records, before selecting candidates. Pick up to N remaining repos (default 10) by importance × risk, favouring repos whose score changed since the last run. Log the chosen list and a one-line reason for each.
2. **Investigate each pick.** Start from the repo's baseline metrics. Call tools in whatever order the model chooses. Dig deeper when signals conflict: low commits but steady releases may just mean the project is mature. Early-exit if tools confirm official deprecation: record an internal exclusion and suppress any public finding.
3. **Stop.** Stop when confidence is at least 0.7, after a confirmed deprecation exclusion, or after 8 tool calls, whichever comes first.
4. **Verdict.** Emit JSON matching the schema below. Code validates it, and an invalid output gets one retry before the repo is marked `inconclusive`.
5. **Persist.** `MERGE` into `findings`, keyed on (repo\_id, run\_id). The trace id is stored on the row. For a deprecated repo, persist only an internal exclusion record with source and reason; existing `ignored` findings can supply that record for compatibility. Serving queries must apply the exclusion to gold and historical findings. The agent never writes to gold.
6. **Memory.** On the next run, step 1 reads the previous verdicts, skips excluded repos, and the agent states what changed only for eligible repos.

**Tools**

| Tool | Type | Returns |
| --- | --- | --- |
| `get_repo_metrics(repo)` | UC SQL function over gold | Baseline metrics and score |
| `get_commit_trend(repo, weeks)` | UC SQL function over silver | Two 90-day commit totals and their change; actual weekly history is deferred; no invented weekly series |
| `get_release_history(repo)` | UC SQL function | Latest release date and days since it; full release history and inter-release gaps are deferred |
| `get_issue_backlog(repo)` | UC SQL function | Open issues and PR counts; response time and unanswered counts are unknown in the MVP |
| `get_contributor_concentration(repo)` (stretch) | UC SQL function | Disabled until real contributor data is collected |
| `fetch_recent_issues(repo, n)` | GitHub fetch, cached to Delta | The last n issue titles (default 5, at most 20), whether a maintainer replied to each, and the unanswered count |
| `fetch_readme_signals(repo)` | GitHub fetch, cached to Delta | README signals for "deprecated", "unmaintained", "archived", "use X instead", with source and context. Confirmed repo-level deprecation triggers an internal exclusion and stops further tool spend; keyword matches alone are insufficient |
| `get_previous_finding(repo)` | UC SQL function over findings | Last verdict and date |
| `find_alternatives(repo)` (P2) | Vector Search | Up to 3 similar healthy repos |

The snapshot tools read the frozen snapshot and support model-selected investigations with at least two tools. The two live-fetch tools are offered on every investigation as Python inside the Databricks-hosted agent; the system prompt tells the model to prefer the UC tools first.

**Ticket #6 implementation:** `databricks/src/setup/create_uc_tools.sql` registers five active snapshot tools plus an explicitly unavailable contributor-function compatibility entry. All results preserve JSON nulls; missing repos/findings return `found=false`. Release age is measured at collection time, commit percentage change is unknown when the previous count is zero, and unavailable response/contributor metrics are never estimated. The agent does not offer the contributor tool. Bundle job `uc_tools` checks the actual SQL against temporary edge-case fixtures before registration, then verifies registered functions against the live silver/gold tables. See the [README tool run instructions](README.md#agent-data-tools-ticket-6).

**Ticket #11 implementation:** each finding stores the trace ID captured from its own MLflow root span. All model calls (including retries/finalization) and full tool inputs/results are traced. `agent.trace_steps` stores the same trace as ordered JSON so the app can read it through the SQL warehouse; `get_finding_trace` provides the lookup contract. Public decision summaries and the verdict explanation support the UI; private provider reasoning is not exported. The `agent_run` job verifies MLflow retrieval and the persisted finding-to-steps link after investigation. The HTTP endpoint remains in ticket #12.

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
| `human_review` | Inconclusive |

`alternatives` stays empty for healthy controls. For successor moves, put the official next repo first (prefer `vuejs/core` over unrelated frameworks when investigating `vuejs/vue`). Deprecated repos are not returned as alternatives or recommendations. Their exclusion records are internal and carry no user-facing action code.

**Guardrails**

- Every evidence item must name a tool that was actually called in the trace. Code checks this, and unsupported claims are stripped before saving.
- A tool budget and a timeout per repo, so one repo can't burn the run.
- Low temperature for verdicts. The system prompt includes the scoring rubric so the LLM and the formula agree on what each level means.
- Do not recommend replacing a healthy or mature-quiet control with a random “similar” repo. Alternatives are for remediation or documented successors only.
- **Deprecated repos are excluded.** Confirmed deprecation removes the repo from all active product queries and future triage. Preserve audit evidence; never surface `ignored` or `ignore_deprecated` as a public verdict/action.
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
- **Repo list:** preserve eligible curated at-risk, healthy and hard-case examples, remove source-confirmed deprecated entries, then add public, non-fork repos from paginated searches for Python, JavaScript, Go, Rust and Java (`stars:>=100`, sorted by stars). Interleave languages and deduplicate both requested IDs and canonical IDs returned by GitHub. Discover a spare candidate pool (default 1,200 IDs for a 1,000-repo run) so redirects/unavailable repos can be replaced without lowering the publication target. This is a star-ranked sample, not a representative prevalence study. Curated controls are subject to the same deprecation filter as discovered repos. Refill excluded candidates until 1,000 unique eligible repos are collected; keep exclusion IDs, reasons and source links in a separate summary.
- **Metrics:** use small GitHub GraphQL batches (start with 5–10 repos) for name, owner, language, stars, archive flag, last push, latest release, commit totals since 90 and 180 days, open issue/PR counts, description and topics. Derive `commits_prev_90d` as the 180-day total minus the 90-day total using a fixed collection timestamp. Do not fetch per-commit or per-comment histories.
- **Advisories (F15):** one REST call per repo to `GET /repos/{owner}/{repo}/security-advisories`, keeping GHSA ID, CVE ID, severity, CVSS score, CWE IDs, summary and published date, plus a per-repo fetch status so a failed call is never read as "no advisories" (about 1,000 calls, within the token's hourly limit). Run it as a separate pass with bounded retries. This covers only advisories published through GitHub, so projects that report elsewhere (e.g. Django) show none; matching repos to packages in GitHub's global advisory database is deferred.
- **Category (F15):** a one-time `ai_query()` over description and topics, constrained to the 6 fixed categories plus `other`. If too many repos land in `other` because descriptions are thin, fall back to adding a short README excerpt to the scrape.
- **Importance:** use `log10(stars + 1)` for the MVP. deps.dev, dependents mapping, OpenSSF and Criticality Score are deferred; no second source or credential is required.
- **Auth:** read the GitHub token from `dbutils.secrets.get("hackcamp", "github_token")`. Never print or save the token.
- **Landing:** keep the existing `repo_id`, `payload`, `pulled_at` envelope under `/Volumes/hackcamp/raw/github/repos/`. Write newline-delimited JSON chunks with up to 100 records per file (10 files for 1,000 repos), compatible with the existing Auto Loader JSON reader. Stage a frozen copy and per-file record manifest, retain the previous input, then publish only the validated dataset. Keep summaries outside `repos/`, including target, candidate/attempt counts, canonical successes, failures and collection time. Rerunning may refetch the corpus; durable checkpoints remain deferred.
- **Failures:** sequential metric batches of 10 repos, request timeouts and at most 3 attempts per batch; pace discovery requests separately. Honour retry/reset headers within a bounded wait. The default run must collect 1,000 unique eligible real repos across the intended languages before publishing; authentication failures, rate-limit exhaustion or fewer than 1,000 successes leave the old active snapshot unchanged and save a failure summary. The five-repo smoke mode always uses `publish=false`.
- **Handoff:** manually run the existing `repo_health` pipeline after a successful scrape; automatic chaining is optional. Expectations and latest-per-repo selection stay in the existing pipeline. Ensure the real run does not mix generated seed payloads into its final demo snapshot.
- **Freeze and verify:** retain the real snapshot, notebook/job run and summary, and verify bronze/silver/gold counts reconcile with successes and dropped rows. Run the demo from frozen data. Seeded JSON is a clearly labelled development fallback, never evidence of a successful real scrape.

**Scraping contract (updated requirements; deprecation filtering must be implemented and verified):** `databricks/src/ingest/scrape_github_repos.py`, bundle job `github_scrape`, now defaults to `repo_limit=1000`, `minimum_repos=1000`, and `batch_size=10`. A 5-repo smoke run skips discovery and leaves active input untouched. Expanded runs must retain eligible curated IDs, discover spare candidates, refill unavailable, redirected or confirmed deprecated IDs until 1,000 distinct eligible successes, and write JSON Lines chunks plus a record-count manifest under `snapshots/<run_id>/`. Archive the previous input before publication. Verify actual record counts and unique IDs, rather than equating file count with repo count. Refresh the existing ingestion pipeline after publication; stable filenames require a full refresh on subsequent replacement snapshots. See the [README run instructions](README.md#github-scraping-ticket-3).

**Layer 2: targeted fetches (ticket #7)**

- `live_fetch_tools.py` gives the agent read-only README-signal and recent-issue fetches for any investigated repo, cached in the existing `agent.tool_cache` table. Fetch errors come back to the model as a tool result rather than failing the run.
- Contributor concentration and comprehensive histories are deferred. Cached-only demo playback must work without GitHub access.

**Deferred scraping work:** external enrichment, full release/weekly commit/contributor/comment histories, worker pools, durable resume/checkpoint frameworks, recurring scraping, coverage beyond 1,000 repos and production monitoring. These are not acceptance gates for the hackathon.

**If the hackathon provides a usable corpus,** load it with the same notebook/Volume contract and record its provenance; keep downstream schemas and tools unchanged.

## Data model

Everything lives in catalog `hackcamp`, in schemas `raw`, `bronze`, `silver`, `gold`, `agent` and `tools`.

| Table | Grain | Key columns |
| --- | --- | --- |
| `bronze.github_repos_raw` | One API response per repo per pull | `repo_id`, `payload` (JSON), `pulled_at` |
| `silver.repos` | One row per repo | `repo_id`, `name`, `owner`, `language`, `stars`, `is_archived`, `pushed_at`, `last_release_at`, `commits_90d`, `commits_prev_90d`, `open_issues`, `open_prs`, `contributors`, `dependents`, `maintainer_reply_rate` and `top_contributor_share` (always NULL; not collected yet), `description`, `topics`, `advisory_fetch_status` (`ok` \| `failed` \| `not_fetched`) |
| `silver.repo_advisories` | One row per GitHub security advisory per repo | `repo_id`, `ghsa_id`, `cve_id`, `severity`, `cvss_score`, `cwes`, `summary`, `published_at` |
| `gold.repo_health` | One row per repo per run | `repo_id`, `run_id`, `health_score`, `status` (`healthy` \| `watchlist` \| `at_risk`; legacy `ignored` rows are internal and excluded from serving), `importance`, `days_since_release`, `commit_trend_pct`, `category`, `vuln_buckets` (array), `advisory_count`, `max_severity`, `max_cvss`, `x`, `y`, `cat_x`, `cat_y`, `scored_at` |
| `agent.findings` | One row per investigated repo per run | `repo_id`, `run_id`, `risk_level` (public: healthy, watchlist, at_risk, inconclusive; legacy `ignored` is internal only), `confidence`, `headline`, `explanation`, `evidence` (array of structs), `changed_since_last`, `recommended_actions`, `alternatives`, `tool_calls`, `trace_id`, `investigated_at` |
| `agent.runs` | One row per agent run | `run_id`, `started_at`, `repos_triaged`, `repos_investigated`, `tool_calls_total`, `model`, `eval_score` (always NULL; eval results live in the MLflow eval run) |
| `agent.trace_steps` | One app-readable trace per investigation | `trace_id`, `repo_id`, `run_id`, `payload` (ordered decision/tool steps as JSON), `created_at` |
| `agent.tool_cache` | One row per live fetch | `tool`, `args_hash`, `response`, `fetched_at` |
| `agent.eval_labels` | One row per labelled repo | `repo_id`, `label`, `label_source`, `notes` |

**Serving contract:** apply a shared eligibility filter to map/list/detail APIs, findings and traces exposed through the app, summary counts, search and alternative recommendations. Direct links to an excluded repo return an unavailable response without exposing a drawer. Keep raw snapshots and historical rows for audit rather than deleting evidence. Store each exclusion with `repo_id`, reason, source URL, confirmation time and active/reversed state. These are required changes, not a claim that the current implementation already enforces them. If a repo is excluded after snapshot publication, displayed eligible counts may fall below 1,000 until the next validated refill; never continue showing it to preserve the target count.

The Vector Search index for F12 and F14 syncs from an eligible-only source table keyed on `repo_id` with Change Data Feed enabled, embedding name, description, topics and the repo's advisory summaries. Remove excluded repos from the index and enforce the same exclusion when serving results so stale index entries cannot leak through.

`x` and `y` are precomputed in gold (the language's cluster centre plus a seeded offset), so the frontend draws them as they are. `cat_x` and `cat_y` work the same way around category cluster centres, for the cluster-by-category toggle.

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

- **Thresholds:** 70 or more is healthy, 40 to 69 is watchlist, below 40 is at risk. **Eligibility precedes scoring:** confirmed deprecated repos, including source-backed entries in `deprecated_repos.py`, are filtered out before computing active scores and counts. Legacy `ignored` rows remain internal. Archive status alone does not establish deprecation; archived repos without confirmed deprecation remain eligible for evidence-based risk assessment.
- **Importance** (star size and triage weight) = log10(stars + 1) in the MVP. Dependents-based importance is deferred. Excluded repos receive no map position or triage priority.
- **Triage priority** = importance × (100 − health) for eligible rows only, boosted when the score dropped by 10 or more points since the last run.
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
| MLflow Tracing and GenAI evaluation | Per-investigation traces; eval on the labelled set with LLM judges and custom metrics | Shows how the agent reasons and how well it performs | Core |
| Lakeflow Jobs | Runs one on-demand scraping notebook; pipeline runs may be started manually | Source collection runs on Databricks, with visible task history | Core for F1 notebook; Stretch for F10 chaining/scheduling |
| Databricks Apps + SQL warehouse | Hosts the React app and a thin Python API querying gold and findings | The whole product lives inside the workspace | Should |
| Model Serving | Agent as an endpoint, for the live demo investigation | One-click "investigate now" from the UI | If time |
| Vector Search | Index over repo descriptions for find\_alternatives and natural-language map search | Retrieval as an agent tool and map search, not a chatbot | If time |
| `ai_query()` | Classify each repo into one of 6 categories (F15); batch one-liners for repos not investigated (if time) | LLM inference in plain SQL at table scale | Should |

**Skipped on purpose:** Genie (a chatbot, out of scope), Lakebase (Delta through a SQL warehouse is fast enough), AI/BI dashboards (the custom UI covers it).

## Architecture

&#91;embedded content: architecture · data, agent and app inside one workspace\]

GitHub API → Databricks scraping task (Lakeflow Jobs) → frozen JSON in a UC Volume → Auto Loader / Lakeflow pipeline → bronze → silver → gold. The agent reads gold, calls governed UC tools and Databricks-hosted live-fetch tools, and writes findings and traces, which the app reads. Unity Catalog governs the stored data and tools. Demo runs reuse the frozen snapshot and cached tool responses.

## Evaluation and success metrics

The pitch includes one measured number: how often the agent's verdict matches ground truth on repos whose status we already know.

**Labelled set (30–50 repos, built in hours 9–10)**

- **At risk:** thinning maintenance or silence without an official “stop using this” notice — still worth remediating if you depend on it.
- **Exclusion fixtures (separate from risk evaluation):** source-confirmed deprecated repos test that ingestion/serving filters remove them, including old findings and stale search entries. Verify they receive no triage budget and do not appear in product counts. Legacy or quiet status alone must not cause exclusion.
- **Healthy:** well-known projects with releases in the last 90 days and several active maintainers (controls — scanning them is intentional so false-positive rate is measurable).
- **Hard cases:** mature or "done" projects that are quiet but fine, successor-moved lines (e.g. `vuejs/vue` while Vue 3 continues in `vuejs/core`), and projects that recently revived. Ground truth is **not** “at risk” or “ignored” solely because commit volume dropped.
- **Label source** goes in `eval_labels.label_source`, for example a link to the deprecation notice or the successor repo README. Active risk-eval `label` values: `at_risk`, `healthy`, `hard_case`. Legacy `ignored` labels belong to the separate exclusion fixtures and are not risk positives.

**How to score**

- The `eval_run` job runs the same agent on every eligible labelled repo that has a gold row; deprecated fixtures are excluded from the agent run. Eval runs don't write to `findings`, so they never show up on the map.
- Custom metrics, logged to MLflow: verdict accuracy, at-risk precision and recall, a false-alarm rate on the hard cases, the inconclusive rate and median tool calls. Scoring is binary on "is it flagged?": only `at_risk` labels are positives; healthy and hard cases are negatives, and an `inconclusive` verdict counts as not flagged. Deprecated fixtures are excluded from risk metric denominators and tested separately for exclusion coverage and false exclusions.
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

1. **Hook (0:00–0:20).** "Your app depends on hundreds of packages. Which ones are dying?" Open the galaxy map with the verified eligible repo count (target 1,000; deprecated repos filtered out), with red ones scattered through the clusters.
2. **The map (0:20–0:50).** Type "unmaintained Python HTTP clients" and the map zooms to the matches. Hover a big red star and click it. The drawer shows the score, the agent's verdict and the evidence.
3. **How the agent decided (0:50–1:30).** Open the trace tab and walk through its steps: the agent checked releases, saw conflicting commit data, compared archive status and last push, and concluded at risk using the collected evidence. If the agent used a live README or issue fetch, show it. Point out that it chose those steps itself.
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
| Map is slow with 1,000 points | Low | Low | Custom canvas renderer; cache flower artwork and draw only visible points |
| Running out of the 20 hours | High | High | Cut in this order: F13, F12, F11, Model Serving, F10. Never cut traces or eval |

## Open questions

- [x] Workspace edition — **trial / full workspace** (`school`). Model Serving, Vector Search, Apps, and UC outbound HTTP all confirmed (see `.docs/HOUR1_CHECKS.md`).
- [x] Foundation Model tool calling — lock agent on `databricks-meta-llama-3-3-70b-instruct`; fallback `databricks-llama-4-maverick`.
- [x] UC Python outbound HTTP — works (`http_probe` → 200); live-fetch tools may be UC Python functions.
- [ ] Does the hackathon provide a dataset or corpus? If so, it replaces Layer 1 ingestion.
- [ ] What are the official judging criteria for Best Use of Databricks? Check them against the Users and judges assumption.
- [ ] Team size and who owns each workstream.
- [ ] Exact start time, deadline, and demo length and format.
