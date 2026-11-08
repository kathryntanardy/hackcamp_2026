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
        # Keep the documented binary metric, but also expose whether parked
        # projects were classified correctly and abstentions were real decisions.
        "verdict_accuracy": _safe_div(sum(
            r["pred"] in ({"healthy", "watchlist"} if r["label"] == "hard_case" else {r["label"]})
            for r in rows
        ), len(rows)),
        "living_at_risk_recall": _safe_div(
            sum(r["label"] == "at_risk" and r["pred"] == "at_risk" for r in rows),
            sum(r["label"] == "at_risk" for r in rows),
        ),
        "ignored_recall": _safe_div(
            sum(r["label"] == "ignored" and r["pred"] == "ignored" for r in rows),
            sum(r["label"] == "ignored" for r in rows),
        ),
    }
    calls = [r["tool_calls"] for r in rows if r.get("tool_calls") is not None]
    if calls:
        out["median_tool_calls"] = float(median(calls))
    return out


def baseline_prediction(row, weights=(30, 25, 10)):
    """Reproduce the MVP formula for a bounded, offline weight sensitivity check."""
    if row.get("formula_status") == "ignored":
        return "ignored"
    def clamp(value):
        return max(0.0, min(1.0, value))
    release, ratio, push = (row.get(k) for k in ("days_since_release", "commit_ratio", "days_since_push"))
    signals = [None if release is None else clamp((540 - release) / 450),
               None if ratio is None else clamp((ratio - .2) / .8),
               None if push is None else clamp((365 - push) / 335)]
    present = [(w, s) for w, s in zip(weights, signals) if s is not None]
    health = round(100 * sum(w * s for w, s in present) / sum(w for w, s in present), 2) if present else None
    return "watchlist" if health is None else "healthy" if health >= 70 else "watchlist" if health >= 40 else "at_risk"


def weight_sensitivity(rows):
    """Exploratory training-set comparison; never silently tune production on test labels."""
    rows = list(rows)
    candidates = [(30, 25, 10), (20, 35, 10), (40, 15, 10), (25, 20, 20), (15, 25, 25)]
    return [{"weights": dict(zip(("release", "commits", "activity"), weights)),
             **score({"label": r["label"], "pred": baseline_prediction(r, weights)} for r in rows)}
            for weights in candidates]
