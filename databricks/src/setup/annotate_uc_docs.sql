-- Unity Catalog documentation for the repo-health data product + hour-1 diagnostics.
-- Safe to re-run. Uses COMMENT ON COLUMN (works for tables, streaming tables, and MVs).
-- Requires tables to already exist (run repo_health pipeline + hour1 probes first).

-- ---------------------------------------------------------------------------
-- Schema-level discovery
-- ---------------------------------------------------------------------------
ALTER SCHEMA hackcamp.bronze SET TAGS ('domain' = 'oss-health', 'tier' = 'bronze');
ALTER SCHEMA hackcamp.silver SET TAGS ('domain' = 'oss-health', 'tier' = 'silver');
ALTER SCHEMA hackcamp.gold SET TAGS ('domain' = 'oss-health', 'tier' = 'gold');
ALTER SCHEMA hackcamp.agent SET TAGS ('domain' = 'oss-health', 'tier' = 'agent');

COMMENT ON SCHEMA hackcamp.bronze IS
  'Landing zone for Auto Loader GitHub JSON. Not for analytics joins; use silver/gold.';
COMMENT ON SCHEMA hackcamp.silver IS
  'Normalized one-row-per-repo metrics from the latest bronze pull.';
COMMENT ON SCHEMA hackcamp.gold IS
  'Scored repo health for the galaxy map, triage, and agent tools.';
COMMENT ON SCHEMA hackcamp.agent IS
  'Agent findings, runs, eval labels, tool cache, and setup diagnostics.';

-- ---------------------------------------------------------------------------
-- bronze.github_repos_raw (streaming table)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE hackcamp.bronze.github_repos_raw IS
  'Raw GitHub API envelopes (one row per repo per pull) landed by Auto Loader from the UC Volume. Prefer silver.repos for metrics.';

ALTER TABLE hackcamp.bronze.github_repos_raw SET TAGS (
  'domain' = 'oss-health',
  'tier' = 'bronze',
  'product' = 'corpus-explorer'
);

COMMENT ON COLUMN hackcamp.bronze.github_repos_raw.repo_id IS 'GitHub owner/name id (e.g. psf/requests). Grain key with pulled_at.';
COMMENT ON COLUMN hackcamp.bronze.github_repos_raw.payload IS 'JSON string of scraped repo metrics for this pull.';
COMMENT ON COLUMN hackcamp.bronze.github_repos_raw.pulled_at IS 'UTC timestamp when the scraper collected this repo payload.';
COMMENT ON COLUMN hackcamp.bronze.github_repos_raw.source_file IS 'UC Volume file path that Auto Loader ingested.';
COMMENT ON COLUMN hackcamp.bronze.github_repos_raw.ingested_at IS 'UTC timestamp when Auto Loader wrote this bronze row.';

-- ---------------------------------------------------------------------------
-- silver.repos (materialized view)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE hackcamp.silver.repos IS
  'Latest normalized GitHub metrics per repo_id. Source for gold scoring and UC agent tools.';

ALTER MATERIALIZED VIEW hackcamp.silver.repos SET TAGS (
  'domain' = 'oss-health',
  'tier' = 'silver',
  'product' = 'corpus-explorer'
);

COMMENT ON COLUMN hackcamp.silver.repos.repo_id IS 'Canonical GitHub owner/name. Primary key (latest pull only).';
COMMENT ON COLUMN hackcamp.silver.repos.pulled_at IS 'Collection time of the winning (latest) bronze payload for this repo.';
COMMENT ON COLUMN hackcamp.silver.repos.name IS 'Repository name without owner.';
COMMENT ON COLUMN hackcamp.silver.repos.owner IS 'GitHub org or user that owns the repository.';
COMMENT ON COLUMN hackcamp.silver.repos.language IS 'Primary language label used for galaxy-map clusters.';
COMMENT ON COLUMN hackcamp.silver.repos.stars IS 'GitHub stargazer count at collection time.';
COMMENT ON COLUMN hackcamp.silver.repos.dependents IS 'Dependents count when collected; 0 if unknown (MVP often 0).';
COMMENT ON COLUMN hackcamp.silver.repos.is_archived IS 'True if GitHub marks the repo archived. Drives gold ignored parking with known deprecations.';
COMMENT ON COLUMN hackcamp.silver.repos.pushed_at IS 'Timestamp of the latest push on the default branch.';
COMMENT ON COLUMN hackcamp.silver.repos.last_release_at IS 'Published time of the latest GitHub release, if any.';
COMMENT ON COLUMN hackcamp.silver.repos.commits_90d IS 'Commit count in the 90 days ending at collection time.';
COMMENT ON COLUMN hackcamp.silver.repos.commits_prev_90d IS 'Commit count in the prior 90-day window (days 91–180).';
COMMENT ON COLUMN hackcamp.silver.repos.open_issues IS 'Open issue count at collection time (not reply latency).';
COMMENT ON COLUMN hackcamp.silver.repos.open_prs IS 'Open pull-request count at collection time.';
COMMENT ON COLUMN hackcamp.silver.repos.contributors IS 'Contributor count when collected; may be sparse in the MVP scrape.';
COMMENT ON COLUMN hackcamp.silver.repos.maintainer_reply_rate IS 'Share of issues/PRs with a maintainer reply when collected; often seeded/unknown in MVP.';
COMMENT ON COLUMN hackcamp.silver.repos.top_contributor_share IS 'Top author share of recent commits when collected; bus-factor signal, often seeded in MVP.';

-- ---------------------------------------------------------------------------
-- gold.repo_health (materialized view, 16 columns)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE hackcamp.gold.repo_health IS
  'Baseline maintainer-risk scores and galaxy-map coordinates. status bins: healthy, watchlist, at_risk, ignored. Ignored = deprecated/archived; excluded from living agent triage.';

ALTER MATERIALIZED VIEW hackcamp.gold.repo_health SET TAGS (
  'domain' = 'oss-health',
  'tier' = 'gold',
  'product' = 'corpus-explorer'
);

COMMENT ON COLUMN hackcamp.gold.repo_health.repo_id IS 'GitHub owner/name. Joins to silver.repos and agent.findings.';
COMMENT ON COLUMN hackcamp.gold.repo_health.run_id IS 'Pipeline score batch id (yyyyMMddHHmmss of scored_at). Not the agent investigation run_id.';
COMMENT ON COLUMN hackcamp.gold.repo_health.health_score IS 'Weighted 0–100 baseline from release freshness, commit trend, activity (and MVP maintainer/bus terms when present). Higher = healthier. Distinct from importance.';
COMMENT ON COLUMN hackcamp.gold.repo_health.status IS 'Map/triage bin: healthy (>=70), watchlist (40–69), at_risk (<40), or ignored (archived or known-deprecated — park, no future PR-review budget).';
COMMENT ON COLUMN hackcamp.gold.repo_health.importance IS 'Star size / triage weight: log10(dependents+1) if dependents>0 else log10(stars+1). How much the ecosystem cares — not the risk score.';
COMMENT ON COLUMN hackcamp.gold.repo_health.days_since_release IS 'Whole days from last_release_at to score date; 999 when no release was collected.';
COMMENT ON COLUMN hackcamp.gold.repo_health.commit_trend_pct IS 'Percent change of commits_90d vs commits_prev_90d: ((recent-previous)/previous)*100. Null when previous window is 0.';
COMMENT ON COLUMN hackcamp.gold.repo_health.x IS 'Galaxy-map X coordinate: language cluster centre + seeded hash offset so positions stay stable across reloads.';
COMMENT ON COLUMN hackcamp.gold.repo_health.y IS 'Galaxy-map Y coordinate: language cluster centre + seeded hash offset so positions stay stable across reloads.';
COMMENT ON COLUMN hackcamp.gold.repo_health.scored_at IS 'UTC timestamp when this gold row was computed.';
COMMENT ON COLUMN hackcamp.gold.repo_health.language IS 'Primary language for map clustering (Python, JavaScript, Go, Rust, Java, …).';
COMMENT ON COLUMN hackcamp.gold.repo_health.stars IS 'GitHub stars copied from silver at score time (drives importance when dependents missing).';
COMMENT ON COLUMN hackcamp.gold.repo_health.dependents IS 'Dependents copied from silver; 0/unknown falls importance back to stars.';
COMMENT ON COLUMN hackcamp.gold.repo_health.is_archived IS 'Archived flag from silver; true forces status=ignored.';
COMMENT ON COLUMN hackcamp.gold.repo_health.name IS 'Repository short name for UI labels.';
COMMENT ON COLUMN hackcamp.gold.repo_health.owner IS 'GitHub owner for UI labels and links.';

-- ---------------------------------------------------------------------------
-- agent.hour1_checks — diagnostics only (not analytical)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE hackcamp.agent.hour1_checks IS
  'Environment self-check from hour-1 setup (HTTP probe, recommended FM model, summary JSON). One-row diagnostics artifact — not part of the repo-health analytical data product; do not join for map/findings.';

ALTER TABLE hackcamp.agent.hour1_checks SET TAGS (
  'domain' = 'oss-health',
  'tier' = 'diagnostics',
  'product' = 'corpus-explorer'
);

COMMENT ON COLUMN hackcamp.agent.hour1_checks.checked_at IS 'When the hour-1 probe notebook wrote this row.';
COMMENT ON COLUMN hackcamp.agent.hour1_checks.http_probe_result IS 'Result of UC Python outbound HTTP probe (e.g. ok status=200 …).';
COMMENT ON COLUMN hackcamp.agent.hour1_checks.recommended_model IS 'Foundation Model endpoint locked for the agent after the tool-calling bakeoff.';
COMMENT ON COLUMN hackcamp.agent.hour1_checks.summary_json IS 'Full probe summary blob (models tried, VS/Apps availability, etc.).';

-- Agent analytical tables (short descriptions for Discover)
COMMENT ON TABLE hackcamp.agent.findings IS
  'Agent investigation verdicts keyed by (repo_id, run_id), including ignored for parked deprecations.';
COMMENT ON TABLE hackcamp.agent.runs IS
  'One summary row per agent investigation batch.';
COMMENT ON TABLE hackcamp.agent.eval_labels IS
  'Ground-truth labels (healthy, hard_case, at_risk, ignored) for eval.';
COMMENT ON TABLE hackcamp.agent.tool_cache IS
  'Cached live GitHub tool responses for demo replay without re-hitting the API.';

ALTER TABLE hackcamp.agent.findings SET TAGS ('domain' = 'oss-health', 'tier' = 'agent', 'product' = 'corpus-explorer');
ALTER TABLE hackcamp.agent.runs SET TAGS ('domain' = 'oss-health', 'tier' = 'agent', 'product' = 'corpus-explorer');
ALTER TABLE hackcamp.agent.eval_labels SET TAGS ('domain' = 'oss-health', 'tier' = 'agent', 'product' = 'corpus-explorer');
ALTER TABLE hackcamp.agent.tool_cache SET TAGS ('domain' = 'oss-health', 'tier' = 'agent', 'product' = 'corpus-explorer');
