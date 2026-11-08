# Open-Source Corpus Explorer — Project Status

Updated: November 7, 2026 (America/Vancouver).

This summary combines the current repository implementation, checked-in run reports, and results previously verified in the project conversation. It is a dated snapshot, not a fresh live Databricks audit. GitHub statuses below are from the last ticket review in that conversation.

## What the project does

The project collects public GitHub repository data, calculates maintenance-health scores, and uses an AI investigator to examine selected repositories. It stores findings and evidence in Databricks and exposes them through a backend API. The planned frontend is a searchable galaxy map with repository details and investigation traces.

## Completed foundation

| Area | What has been implemented or recorded as complete |
| --- | --- |
| Workspace and governance | Databricks workspace, Unity Catalog schemas, raw Volume, tables and access checks. |
| Scraping | A Databricks-hosted GitHub scraper with a 1,000-repository target, canonical-ID deduplication, bounded retries, summaries and archived snapshots. |
| Ingestion | Bronze, silver and gold processing through the existing Lakeflow pipeline. The initial expanded snapshot verified 1,000 rows and 1,000 unique repositories in each layer. |
| Enrichment | Repository descriptions, topics and security advisories, including explicit fetch status. |
| Scoring | Baseline maintenance-health score, importance, status and language-cluster coordinates. Missing signals remain unknown rather than fabricated worst-case values. |
| Categories and vulnerabilities | Repository categories, CWE-based vulnerability buckets, advisory counts, severity/CVSS summaries and category-cluster coordinates. |
| Investigation | Repository prioritization, model-selected tool calls, structured verdicts, persisted findings and evidence. |
| Tracing | MLflow traces and app-readable trace steps linked to findings. |
| Backend | FastAPI endpoints for repositories, details, findings, traces and the latest run; Databricks Apps deployment was recorded as complete. |
| Summaries | AI-generated one-line summaries for repositories without investigator findings. |
| Automation and lineage | A successful pipeline-to-agent scheduled workflow and captured Unity Catalog lineage. Scraping remains a separate on-demand job. |

The collected corpus is a bounded, largely star-ranked sample with curated controls. It is not a representative survey of all open-source software.

## Recorded data coverage

The enrichment run report records:

| Measurement | Result |
| --- | ---: |
| Repositories | 1,000 |
| Non-empty descriptions | 996 |
| Repositories with topics | 862 |
| Advisory fetches marked successful | 1,000 |
| Advisory rows | 3,682 |
| Gold rows with a category | 1,000 |
| Category `other` | 38 |
| Repositories in the `No GitHub advisories` bucket | 717 |

An empty advisory result means no advisories were returned by the source. It does not establish that a repository is safe. Fetch failures must remain distinguishable from successful empty results.

Evidence: [1,000-repository ingestion report](.docs/CORPUS1000_RUN.md), [enrichment report](.docs/TICKET31_RUN.md), and [category/vulnerability report](.docs/TICKET32_RUN.md).

## AI components and supporting jobs

There is one tool-calling investigator, alongside other AI-assisted jobs:

| Component | Job | Responsibility |
| --- | --- | --- |
| Repository investigator | `hackcamp-agent-run` | Investigate selected repositories using tools; save a verdict, confidence, explanation, evidence and trace. |
| Evaluation and grounding judge | `hackcamp-eval-run` | Compare investigator predictions with labelled examples and the formula; assess explanation grounding. |
| Category classifier | `hackcamp-classify-categories` | Classify description/topic text into project categories using `ai_query()`. |
| Summary generator | `hackcamp-repo-summaries` | Produce short maintenance summaries for repositories without investigator findings. |

Supporting jobs include `hackcamp-github-scrape`, the `hackcamp-repo-health` pipeline, `hackcamp-scheduled-autonomy`, UC tool registration, setup checks, lineage capture and trace verification. These are data-processing or orchestration jobs, not additional independent AI investigators.

Triage uses a coded priority calculation based on importance and baseline risk. Memory helpers and trace verification are parts of the investigation workflow. The current checkout contains memory implementation; its ticket was still open at the last review.

The investigator can return `healthy`, `watchlist`, `at_risk`, `ignored`, or `inconclusive`. It investigates only the configured budget, not automatically all 1,000 repositories. Already ignored repositories are excluded from normal triage.

## Evaluation results and quality gaps

A previously recorded evaluation ran on 50 labelled repositories:

| Metric | Investigator | Baseline formula |
| --- | ---: | ---: |
| Binary flag accuracy | 88% | 94% |
| Correct-category verdict accuracy | 68% | 90% |
| Flag precision | 50% | 66.7% |
| Flag recall | 100% | 100% |
| Inconclusive rate | 18% | 0% |
| Grounded explanations, after judge-timeout recovery | 62% (31/50) | — |

Binary flag metrics combine `at_risk` and `ignored`; an inconclusive answer counts as unflagged. Correct-category accuracy separately penalizes abstentions and confusion between living-risk and ignored categories. Healthy or watchlist is accepted for hard cases.

The labelled set contained 31 healthy, 13 hard-case, five ignored and only one living at-risk example. Recall on living risk therefore has very limited support. These results describe the labelled sample, not all 1,000 repositories.

Nine investigations returned inconclusive results after model endpoint rate-limit errors. Four judge calls initially timed out and were retried; final reported grounding coverage was 50/50. Other observed issues included overstating README deprecation keywords, sampled issue-response evidence and absent release information. The investigator did not beat the formula or meet the precision and grounding targets.

Five weight configurations were compared. The recorded deployed comparison retained release/commits/activity weights of **30/25/10**. Two alternatives reached 96% binary accuracy on the same labels, but that is exploratory rather than independent validation.

The prior evaluation recorded `eval_score=0.88` on a same-model investigation run. That score is a labelled-set model benchmark, not measured accuracy on an unlabelled production batch. These historical results were not rerun for this summary and do not independently verify every evaluation change in the current checkout.

[Recorded evaluation job](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/252164496996214/runs/351283910827240) · [Recorded MLflow run](https://dbc-a0a04386-0e40.cloud.databricks.com/ml/experiments/3876070005521687/runs/6d004f864c8b4676b34f83614afb0a68)

## Data layout

```text
GitHub APIs
  → raw Volume snapshots
  → bronze.github_repos_raw
  → silver.repos + silver.repo_advisories
  → gold.repo_health
  → investigator → agent.findings + agent.trace_steps
  → backend API → planned product frontend
```

All table names above are under the `hackcamp` catalog. Other supporting tables include `silver.repo_categories`, `gold.repo_summaries`, `agent.runs`, `agent.eval_labels` and `agent.tool_cache`.

The table-owning pipeline previously verified for the live corpus is `23564139-0ea8-435b-9a96-dbae9699ce92`. Multiple developer deployments exist; a developer-specific job name alone does not establish ownership of the shared tables.

## What remains

At the last ticket review, **19 of 34 tickets were closed**: #1–#13, #15, #16, #20, #31, #32 and #34. Closed status is a workflow record; the run reports above provide stronger execution evidence.

| Ticket(s) | Remaining work / last known status |
| --- | --- |
| [#14](https://github.com/kathryntanardy/hackcamp_2026/issues/14) | Evaluation was run, but the ticket remained open and model quality targets were missed. |
| [#30](https://github.com/kathryntanardy/hackcamp_2026/issues/30) | Natural-language search index and API, followed by map integration; assigned to Kathryn. Completion has not been established here. |
| [#18](https://github.com/kathryntanardy/hackcamp_2026/issues/18) | Similar healthy alternatives, sharing the search index. |
| [#19](https://github.com/kathryntanardy/hackcamp_2026/issues/19) | Run-over-run memory; code exists, but ticket completion was not established. Last assigned to Pho86. |
| [#21](https://github.com/kathryntanardy/hackcamp_2026/issues/21) | On-demand investigation through a Model Serving/API endpoint. |
| #22–#28 | Product design, frontend scaffold, galaxy map, repository drawer, trace tab, findings page and real API integration. A basic frontend starter exists; the product screens are not established as complete. |
| [#33](https://github.com/kathryntanardy/hackcamp_2026/issues/33) | Frontend category/vulnerability filters, sorting and cluster toggle. |
| [#29](https://github.com/kathryntanardy/hackcamp_2026/issues/29) | Frontend stretch features. |
| [#17](https://github.com/kathryntanardy/hackcamp_2026/issues/17) | Demo preparation, rehearsal and backup video. |

## Recommended next steps

1. Build #30's shared search index and backend API against the enriched corpus. Verify search results directly before frontend integration.
2. Reuse the index for #18's alternatives tool.
3. Address model rate limits and evidence-grounding failures, then repeat the evaluation with results and label limitations reported explicitly.
4. Complete the design/scaffold path and connect the map, findings and trace views to the API.
5. Run a small end-to-end acceptance test: refresh the owning pipeline, investigate three repositories, verify saved findings/traces, and compare API responses with the tables.

## Existing implementation evidence

- [Workspace checks](.docs/HOUR1_CHECKS.md)
- [Scraping implementation/run](.docs/TICKET3_RUN.md)
- [UC tools and contract verification](.docs/TICKET6_RUN.md)
- [Trace verification](.docs/TICKET11_RUN.md)
- [Scheduled workflow](.docs/TICKET15_RUN.md)
- [Unity Catalog lineage](.docs/TICKET16_RUN.md)
- [Product requirements](PRD.md)
- [Setup and run instructions](README.md)

This document does not certify a new end-to-end run, current service availability, or acceptable model quality. No jobs or tests were run and no live resources were changed while writing it.
