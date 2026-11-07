"""Pure-Python eval metrics for the maintainer-risk agent (no Spark/MLflow).

Labels (agent.eval_labels.label): at_risk | ignored | healthy | hard_case.
Predictions: healthy | watchlist | at_risk | ignored | inconclusive (agent) or gold status (formula).

Scoring is binary on "should this repo be flagged?":
- at_risk and ignored (officially deprecated, per PRD) labels are positives;
  healthy and hard_case are negatives (hard cases are quiet-but-fine or revived
  projects, so flagging them is a false alarm).
- at_risk and ignored predictions both count as flagged.
- inconclusive counts as not flagged (a miss on a positive, fine on a negative).
"""

from statistics import median

FLAGGED = {"at_risk", "ignored"}


def _safe_div(num, den):
    return num / den if den else None


def score(rows):
    """rows: iterable of dicts with `label` and `pred`. Optional `tool_calls`."""
    rows = list(rows)
    tp = sum(1 for r in rows if r["label"] in FLAGGED and r["pred"] in FLAGGED)
    fp = sum(1 for r in rows if r["label"] not in FLAGGED and r["pred"] in FLAGGED)
    fn = sum(1 for r in rows if r["label"] in FLAGGED and r["pred"] not in FLAGGED)
    tn = len(rows) - tp - fp - fn

    hard = [r for r in rows if r["label"] == "hard_case"]
    hard_alarms = sum(1 for r in hard if r["pred"] in FLAGGED)

    out = {
        "n": len(rows),
        "accuracy": _safe_div(tp + tn, len(rows)),
        "at_risk_precision": _safe_div(tp, tp + fp),
        "at_risk_recall": _safe_div(tp, tp + fn),
        "hard_case_false_alarm_rate": _safe_div(hard_alarms, len(hard)),
        "inconclusive_rate": _safe_div(
            sum(1 for r in rows if r["pred"] == "inconclusive"), len(rows)
        ),
    }
    calls = [r["tool_calls"] for r in rows if r.get("tool_calls") is not None]
    if calls:
        out["median_tool_calls"] = float(median(calls))
    return out
