import importlib.util
import sqlite3
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("investigation_coverage", Path(__file__).resolve().parents[1] / "src/agent/investigation_coverage.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_remaining_plan_handles_partial_and_empty_batches_without_exceeding_cap():
    assert m.coverage_plan(462, "remaining") == (462, [50] * 9 + [12])
    assert m.coverage_plan(488, "remaining") == (488, [50] * 9 + [38])
    assert m.coverage_plan(0, "remaining") == (0, [0] * 10)
    assert sum(m.coverage_plan(900, "remaining")[1]) == 500
    assert m.coverage_plan(40, "25") == (25, [25] + [0] * 9)
    with pytest.raises(ValueError):
        m.coverage_plan(462, "500")


def test_coverage_skips_existing_case_insensitively_and_parks_ignored():
    db = sqlite3.connect(":memory:")
    db.executescript("""CREATE TABLE gold(repo_id TEXT, language TEXT, health_score REAL, status TEXT,
                       importance REAL, days_since_release INT, commit_trend_pct REAL);
        CREATE TABLE findings(repo_id TEXT, risk_level TEXT);
        INSERT INTO gold VALUES ('existing/repo','Go',10,'at_risk',5,300,-50),
          ('parked/repo','Go',10,'ignored',5,300,-50), ('prior/ignored','Go',10,'at_risk',5,300,-50),
          ('new/low','Go',90,'healthy',2,20,10), ('new/high','Go',20,'at_risk',4,400,-70);
        INSERT INTO findings VALUES ('EXISTING/REPO','watchlist'),('prior/ignored','ignored');""")
    def selected(only_new, budget=50):
        return [r[0] for r in db.execute(m.triage_sql(budget, only_new, gold_table="gold", findings_table="findings"))]
    assert selected(True) == ['new/high', 'new/low']
    assert selected(False)[0] == 'existing/repo'  # normal memory/revisit behavior preserved
    assert selected(True, 1) == ['new/high']
    at_risk = [r[0] for r in db.execute(
        m.triage_sql(50, False, status_filter="at_risk", gold_table="gold", findings_table="findings"))]
    assert at_risk == ['existing/repo', 'new/high']
    with pytest.raises(ValueError):
        m.triage_sql(10, False, status_filter="bogus")


def test_invalid_budget_and_false_coverage_are_rejected():
    for value in [0, 501, -1, True]:
        with pytest.raises(ValueError):
            m.triage_sql(value, True)
    rows = [{"repo_id": "new/a", "trace_id": "tr-a", "risk_level": "healthy"},
            {"repo_id": "new/b", "trace_id": "tr-b", "risk_level": "inconclusive"}]
    assert m.check_coverage(rows, ['old/c'], 2)["risk_counts"] == {"healthy": 1, "inconclusive": 1}
    for baseline, expected in [(['NEW/A'], 2), ([], 3)]:
        with pytest.raises(ValueError):
            m.check_coverage(rows, baseline, expected)
    with pytest.raises(ValueError):
        m.check_coverage([rows[0], rows[0]], [], 2)
