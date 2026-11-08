"""Selection and count checks for bounded production investigation coverage."""


def coverage_plan(available, requested="500"):
    """At most 500 model investigations; the remainder may need a partial batch."""
    if type(available) is not int or available < 0:
        raise ValueError("Available count must be a nonnegative integer")
    if requested == "remaining":
        target = min(available, 500)
    else:
        target = int(requested)
        if not 1 <= target <= 500 or available < target:
            raise ValueError("Requested target must be 1–500 and fit available uninvestigated repos")
    return target, [max(0, min(50, target - i * 50)) for i in range(10)]


def triage_sql(budget, uninvestigated_only=False, *, status_filter=None,
               gold_table="hackcamp.gold.repo_health",
               findings_table="hackcamp.agent.findings"):
    if type(budget) is not int or not 1 <= budget <= 500:
        raise ValueError("Investigation budget must be between 1 and 500")
    allowed = {None, "", "at_risk", "watchlist", "healthy", "inconclusive"}
    if status_filter not in allowed:
        raise ValueError(f"status_filter must be one of {sorted(s for s in allowed if s)}")
    unseen = f"AND NOT EXISTS (SELECT 1 FROM {findings_table} f WHERE lower(f.repo_id)=lower(g.repo_id))" if uninvestigated_only else ""
    status_clause = (
        f"AND g.status = '{status_filter}'" if status_filter else "AND g.status <> 'ignored'"
    )
    return f"""SELECT g.repo_id, g.language, g.health_score, g.status, g.importance,
        g.importance * (100.0 - coalesce(g.health_score, 50.0)) AS priority,
        g.days_since_release, g.commit_trend_pct
        FROM {gold_table} g WHERE 1=1
        {status_clause}
        AND NOT EXISTS (SELECT 1 FROM {findings_table} f
                        WHERE lower(f.repo_id)=lower(g.repo_id) AND f.risk_level='ignored')
        {unseen}
        ORDER BY priority DESC, g.repo_id LIMIT {budget}"""


def check_coverage(rows, baseline_ids, expected):
    ids = [r["repo_id"].lower() for r in rows]
    if len(ids) != expected or len(set(ids)) != expected:
        raise ValueError(f"Expected {expected} unique new findings, got {len(ids)} rows / {len(set(ids))} unique")
    if set(ids) & {r.lower() for r in baseline_ids}:
        raise ValueError("Coverage includes repositories investigated before this run")
    traces = [r["trace_id"] for r in rows]
    if not all(traces) or len(set(traces)) != expected:
        raise ValueError("Every investigation must have a distinct trace")
    counts = {}
    for row in rows:
        counts[row["risk_level"]] = counts.get(row["risk_level"], 0) + 1
    return {"new_repositories": expected, "unique_trace_ids": expected, "risk_counts": counts}
