"""Pure-Python eval metrics for the maintainer-risk agent (no Spark/MLflow).

Labels (agent.eval_labels.label): at_risk | healthy | hard_case.
Predictions: healthy | watchlist | at_risk | inconclusive (agent) or gold status (formula).

Scoring is binary on "is this at risk?":
- at_risk label is a positive; healthy and hard_case are negatives
  (hard cases are quiet-but-fine or revived projects, so flagging them is a false alarm).
- inconclusive counts as "not at_risk" (a miss on a positive, fine on a negative).
"""

from statistics import median

POSITIVE = "at_risk"


def _safe_div(num, den):
    return num / den if den else None


def score(rows):
    """rows: iterable of dicts with `label` and `pred`. Optional `tool_calls`."""
    rows = list(rows)
    tp = sum(1 for r in rows if r["label"] == POSITIVE and r["pred"] == POSITIVE)
    fp = sum(1 for r in rows if r["label"] != POSITIVE and r["pred"] == POSITIVE)
    fn = sum(1 for r in rows if r["label"] == POSITIVE and r["pred"] != POSITIVE)
    tn = len(rows) - tp - fp - fn

    hard = [r for r in rows if r["label"] == "hard_case"]
    hard_alarms = sum(1 for r in hard if r["pred"] == POSITIVE)

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
