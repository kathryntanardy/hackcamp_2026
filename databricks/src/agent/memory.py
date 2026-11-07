# Databricks notebook source
"""Ticket #19 (F13): run-over-run memory. Pure helpers, no Spark, so they test locally."""

RANK = {"healthy": 0, "watchlist": 1, "at_risk": 2}


def compute_change(prev_risk, new_risk):
    """Label the move from the previous verdict to this one. Code decides, not the model."""
    if not prev_risk:
        return "first_seen"
    if new_risk == prev_risk or new_risk == "inconclusive":
        return "unchanged"
    if new_risk == "ignored":
        return "newly_ignored"
    if new_risk == "at_risk":
        return "newly_at_risk"
    if prev_risk in RANK and new_risk in RANK and RANK[new_risk] < RANK[prev_risk]:
        return "recovered"
    return "unchanged"


def memory_prompt(prev):
    """Line for the investigation prompt so the model can say what changed."""
    if not prev:
        return "Previous finding: none (first time this repo is investigated)."
    return (
        f"Previous finding ({prev.get('investigated_at')}, run {prev.get('run_id')}): "
        f"risk_level={prev.get('risk_level')} confidence={prev.get('confidence')} "
        f"headline={prev.get('headline')!r}. "
        "If your verdict differs, say in the explanation what changed since then."
    )


def change_note(prev, new_risk):
    """Short deterministic sentence stating what changed, or None when nothing did."""
    if not prev or not prev.get("risk_level") or prev["risk_level"] == new_risk or new_risk == "inconclusive":
        return None
    when = str(prev.get("investigated_at") or "")[:10] or "last run"
    return f"Changed since {when}: {prev['risk_level']} → {new_risk}."


def apply_memory(verdict, prev):
    """Set changed_since_last and prefix the explanation with what changed."""
    verdict.changed_since_last = compute_change(prev.get("risk_level") if prev else None, verdict.risk_level)
    note = change_note(prev, verdict.risk_level)
    if note and not verdict.explanation.startswith(note):
        verdict.explanation = f"{note} {verdict.explanation}"
    return verdict
