"""Ticket #19: run-over-run memory labels and change notes, no Spark or model calls."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory", ROOT / "src/agent/memory.py")
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


@pytest.mark.parametrize("prev,new,expected", [
    (None, "at_risk", "first_seen"),
    (None, "healthy", "first_seen"),
    ("healthy", "healthy", "unchanged"),
    ("at_risk", "at_risk", "unchanged"),
    ("healthy", "at_risk", "newly_at_risk"),
    ("watchlist", "at_risk", "newly_at_risk"),
    ("inconclusive", "at_risk", "newly_at_risk"),
    ("at_risk", "healthy", "recovered"),
    ("at_risk", "watchlist", "recovered"),
    ("watchlist", "healthy", "recovered"),
    ("healthy", "watchlist", "unchanged"),
    ("at_risk", "ignored", "newly_ignored"),
    ("at_risk", "inconclusive", "unchanged"),
    ("inconclusive", "healthy", "unchanged"),
])
def test_compute_change(prev, new, expected):
    assert memory.compute_change(prev, new) == expected


def verdict(risk, explanation="Evidence summary."):
    return NS(risk_level=risk, explanation=explanation, changed_since_last="first_seen")


def test_two_runs_produce_correct_labels():
    """Done-when for #19: a second run gets the right changed_since_last values."""
    run1 = {"a/flip": "healthy", "b/heal": "at_risk", "c/same": "watchlist"}
    run2 = {"a/flip": "at_risk", "b/heal": "healthy", "c/same": "watchlist", "d/new": "healthy"}

    store = {}  # stands in for agent.findings: latest finding per repo
    labels1 = {}
    for repo, risk in run1.items():
        v = memory.apply_memory(verdict(risk), store.get(repo))
        labels1[repo] = v.changed_since_last
        store[repo] = {"risk_level": risk, "run_id": "r1", "investigated_at": "2026-11-07 10:00:00"}
    assert set(labels1.values()) == {"first_seen"}

    labels2 = {repo: memory.apply_memory(verdict(risk), store.get(repo)).changed_since_last
               for repo, risk in run2.items()}
    assert labels2 == {"a/flip": "newly_at_risk", "b/heal": "recovered",
                       "c/same": "unchanged", "d/new": "first_seen"}


def test_explanation_states_what_changed():
    prev = {"risk_level": "healthy", "investigated_at": "2026-11-07 10:00:00"}
    v = memory.apply_memory(verdict("at_risk", "Releases stopped."), prev)
    assert v.explanation == "Changed since 2026-11-07: healthy → at_risk. Releases stopped."
    # Applying twice doesn't double the note
    assert memory.apply_memory(v, prev).explanation == v.explanation


def test_no_note_when_unchanged_or_first_seen():
    assert memory.apply_memory(verdict("healthy", "x"), None).explanation == "x"
    prev = {"risk_level": "healthy", "investigated_at": "2026-11-07"}
    assert memory.apply_memory(verdict("healthy", "x"), prev).explanation == "x"
    assert memory.apply_memory(verdict("inconclusive", "x"), prev).explanation == "x"


def test_memory_prompt():
    assert "none" in memory.memory_prompt(None)
    line = memory.memory_prompt({"risk_level": "at_risk", "run_id": "r1", "confidence": 0.8,
                                 "headline": "Quiet", "investigated_at": "2026-11-07"})
    assert "risk_level=at_risk" in line and "r1" in line and "what changed" in line
