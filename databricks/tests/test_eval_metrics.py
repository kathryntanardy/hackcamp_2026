import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src/agent/eval_metrics.py"
SPEC = importlib.util.spec_from_file_location("eval_metrics", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_inconclusive_and_wrong_ignored_bin_are_not_correct_verdicts():
    s = m.score([{"label": "healthy", "pred": "inconclusive"},
                 {"label": "at_risk", "pred": "ignored"}])
    assert s["accuracy"] == 1.0
    assert s["verdict_accuracy"] == 0.0


def row(label, pred, tool_calls=None):
    return {"label": label, "pred": pred, "tool_calls": tool_calls}


def test_mixed_set():
    rows = [
        row("at_risk", "at_risk", 3),       # TP
        row("at_risk", "watchlist", 4),     # FN
        row("at_risk", "inconclusive", 8),  # FN (inconclusive is not a flag)
        row("healthy", "healthy", 2),       # TN
        row("healthy", "at_risk", 5),       # FP
        row("hard_case", "watchlist", 6),   # TN
        row("hard_case", "at_risk", 3),     # FP + hard-case false alarm
    ]
    s = m.score(rows)
    assert s["n"] == 7
    assert s["accuracy"] == 3 / 7
    assert s["at_risk_precision"] == 1 / 3
    assert s["at_risk_recall"] == 1 / 3
    assert s["hard_case_false_alarm_rate"] == 0.5
    assert s["inconclusive_rate"] == 1 / 7
    assert s["median_tool_calls"] == 4.0


def test_perfect_formula_style_rows_without_tool_calls():
    rows = [{"label": "at_risk", "pred": "at_risk"}, {"label": "healthy", "pred": "healthy"}]
    s = m.score(rows)
    assert s["accuracy"] == 1.0
    assert s["at_risk_precision"] == 1.0
    assert s["at_risk_recall"] == 1.0
    assert s["hard_case_false_alarm_rate"] is None  # no hard cases
    assert "median_tool_calls" not in s


def test_no_positive_predictions_gives_none_precision_not_crash():
    s = m.score([row("at_risk", "healthy"), row("healthy", "healthy")])
    assert s["at_risk_precision"] is None
    assert s["at_risk_recall"] == 0.0
    assert s["accuracy"] == 0.5


def test_empty():
    s = m.score([])
    assert s["n"] == 0 and s["accuracy"] is None


def test_ignored_counts_as_flagged():
    s = m.score([row("at_risk", "ignored"), row("hard_case", "ignored"), row("healthy", "healthy")])
    assert s["at_risk_recall"] == 1.0
    assert s["hard_case_false_alarm_rate"] == 1.0
    assert s["at_risk_precision"] == 0.5


def test_ignored_label_is_a_positive():
    # PRD relabelled deprecated repos as ignored; catching them is a hit, not a false alarm
    s = m.score([row("ignored", "ignored"), row("ignored", "at_risk"), row("ignored", "healthy")])
    assert s["at_risk_precision"] == 1.0
    assert s["at_risk_recall"] == 2 / 3
