# Ticket #14 evaluation rerun

Completed November 7, 2026, Vancouver time. This reruns the existing 50 labelled
repository-health cases with the current agent, including its three SDK retries
for retryable model requests. It does not test natural-language map search.

- [Databricks job run](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/252164496996214/runs/761823254245760): evaluation and automatic verification both succeeded.
- [MLflow run](https://dbc-a0a04386-0e40.cloud.databricks.com/ml/experiments/3876070005521687/runs/e15997c8b71642a4a611b6f2a31895bb).
- Evaluation ID: `eval-20261108010636-6f9fb59c`.
- Model: `databricks-meta-llama-3-3-70b-instruct`; tool budget eight; configured per-repo deadline 180 seconds; memory prompt disabled for evaluation.
- Prompt SHA-256: `32eed32c5c6fd43a8e5d5f5b084a1588dde59fa4f84d2c7def59e6cccf7ed138`.

## Measured comparison

| Metric | Previous agent run | This agent run | Current formula |
| --- | ---: | ---: | ---: |
| Binary flag accuracy | 88% | **82% (41/50)** | 94% (47/50) |
| Correct-category verdict accuracy | 68% | **76% (38/50)** | 90% (45/50) |
| Flag precision | 50% | **40%** | 66.7% |
| Flag recall | 100% | 100% | 100% |
| Hard-case false-alarm rate | 7.7% | **23.1% (3/13)** | 7.7% (1/13) |
| Inconclusive rate | 18% (9/50) | **0%** | 0% |
| Ignored recall | 100% | 80% (4/5) | 100% |
| Living at-risk recall | 100% | 100% (1/1) | 100% (1/1) |
| Median tool calls | 4 | 5 | — |
| Judge-rated groundedness | 62% | **66% (33/50)** | — |

Binary flag metrics treat both `at_risk` and `ignored` as flagged, and an
inconclusive verdict as not flagged. Correct-category accuracy penalizes
abstentions and confusing ignored with living risk; hard cases accept healthy or
watchlist. The earlier run's nine inconclusive cases were negative labels, so
binary accuracy credited those abstentions. This is why correct-category accuracy
can rise while binary accuracy falls. All cases are retained in both runs.

All 50 investigations produced verdicts this time, with no inconclusive cases.
The rerun still trails the formula by **12 percentage points** in binary accuracy
and **14 points** in correct-category accuracy. Precision, positive gain over the
formula, and 90% groundedness targets remain unmet. These runs are stochastic and
used current runtime/data; the comparison does not isolate the causal effect of
the retry change.

## Grounding and verification

All **50/50 judge assessments** were valid on the initial pass: 33 supported and
17 unsupported explanations, with no judge errors or recovery calls. The
evaluator checks case-level coverage, preserves valid negative assessments, and
retries only failed judge calls at most twice. Both initial and final means were
66%; canonical grounding metrics are kept consistent after any future recovery.

Automatic verification confirmed:

- 50 rows and 50 unique repository IDs, with no missing labels silently skipped.
- Recomputed agent/formula metrics exactly match the saved summary.
- The weight-comparison formula reproduces the live baseline.
- `hackcamp.agent.runs.eval_score = 0.82` on investigation run `20261108005020-757c652c`.
- Evaluation wrote **zero production findings**.

The saved score is this model's labelled-set binary benchmark, not ground-truth
accuracy on that production batch. It is not the 76% correct-category score.

The first 20 investigations took **316.01 seconds (5m16s)**; all 50 took
**728.18 seconds (12m08s)**. The longest case took 46.21 seconds. These durations
exclude setup, judge calls, and verification. The complete job ran from
approximately 18:06 to 18:22 Vancouver time (16 minutes).

## Remaining quality problems

Nine repositories were falsely flagged against the curated labels: axios,
httpx, jQuery, lodash, chi, Guava, Vue 2, Faker, and Cobra. Several healthy projects
were marked ignored. This remains consistent with the previously observed
problem of interpreting generic README deprecation keywords as repository-wide
deprecation; the per-case explanations and judge rationales are retained for
review. The next agent-quality work should address deprecation scope, mature
projects with low activity, and explanations that overstate unavailable evidence.

The set contains 31 healthy, 13 hard-case, five ignored, and **only one living
at-risk case**. These existing curated labels are not a fresh independent audit
of every project's current status. A one-case living-risk recall result must not
be generalized to the 1,000-repository corpus.

Five fixed weight configurations were compared on the same labels. The PRD
release/commit/activity weights **30/25/10** are retained so the deployed baseline
and comparison stay consistent. Candidate configurations reached 96% binary
accuracy on these same labels; that exploratory result needs independent
validation before changing production scoring.

## Reproducible evidence

Root: `/Volumes/hackcamp/raw/github/evaluations/eval-20261108010636-6f9fb59c/`.

- `summary.json` and `verification.json`.
- `eval_results.json`: all per-case verdicts, evidence, durations, tool counts and trace IDs.
- `eval_labels_snapshot.json`: the exact labels, sources and baseline inputs.
- `weight_sensitivity.json`: weight trials and the retention decision.
- `grounding_assessments.json`: judge inputs, outputs, rationales and coverage.

The current checkout had reverted to the older evaluator. This work restored the
previously verified coverage/score safeguards from the workspace, preserved the
latest agent code, and added the retry configuration and prompt fingerprint to
the run evidence. Future runs include verification automatically.

Validation: **80 local tests passed**, with one Spark-dependent module skipped
locally. Bundle validation/deployment, Python compilation and diff checks passed;
the live Databricks verification checked baseline reproduction and persisted data.
