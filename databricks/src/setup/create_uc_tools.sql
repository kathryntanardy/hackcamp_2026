-- Ticket #6: truthful snapshot-backed Unity Catalog SQL tools.
-- Keep JSON nulls explicit so the agent can distinguish unknown from zero.

CREATE OR REPLACE FUNCTION hackcamp.tools.get_repo_metrics(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Baseline score from the latest gold row and collected silver metrics. Deferred maintainer, contributor and dependents metrics are unknown.'
RETURN (
  SELECT coalesce(
    (SELECT to_json(named_struct(
      'repo_id', s.repo_id,
      'found', true,
      'name', s.name,
      'owner', s.owner,
      'language', s.language,
      'health_score', g.health_score,
      'status', g.status,
      'importance', g.importance,
      'stars', s.stars,
      'is_archived', s.is_archived,
      'pushed_at', cast(s.pushed_at AS STRING),
      'last_release_at', cast(s.last_release_at AS STRING),
      'days_since_release', datediff(to_date(s.pulled_at), to_date(s.last_release_at)),
      'commits_90d', s.commits_90d,
      'commits_prev_90d', s.commits_prev_90d,
      'open_issues', s.open_issues,
      'open_prs', s.open_prs,
      'dependents', cast(NULL AS BIGINT),
      'contributors', cast(NULL AS INT),
      'maintainer_reply_rate', cast(NULL AS DOUBLE),
      'top_contributor_share', cast(NULL AS DOUBLE),
      'unavailable_metrics', array('dependents', 'contributors', 'maintainer_reply_rate', 'top_contributor_share'),
      'data_as_of', cast(s.pulled_at AS STRING),
      'scored_at', cast(g.scored_at AS STRING),
      'source', 'gold_and_silver_snapshot'
    ), map('ignoreNullFields', 'false'))
    FROM hackcamp.silver.repos s
    INNER JOIN hackcamp.gold.repo_health g ON s.repo_id = g.repo_id
    WHERE lower(s.repo_id) = lower(trim(repo))
    ORDER BY g.scored_at DESC NULLS LAST, g.run_id DESC
    LIMIT 1),
    to_json(named_struct('repo_id', repo, 'found', false,
      'message', 'repository not found in the required snapshot tables'), map('ignoreNullFields', 'false'))
  )
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_commit_trend(repo STRING, weeks INT)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Real recent and previous 90-day commit totals and percentage change. No weekly history is available. weeks is retained for compatibility and does not alter the fixed windows. A zero previous count leaves percentage change unknown.'
RETURN (
  SELECT coalesce(
    (SELECT to_json(named_struct(
      'repo_id', s.repo_id,
      'found', true,
      'weeks_requested', weeks,
      'window_days', 90,
      'commits_90d', s.commits_90d,
      'commits_prev_90d', s.commits_prev_90d,
      'trend_pct', CASE WHEN s.commits_prev_90d > 0 AND s.commits_90d IS NOT NULL
        THEN round(100.0 * (s.commits_90d - s.commits_prev_90d) / s.commits_prev_90d, 2)
        ELSE cast(NULL AS DOUBLE) END,
      'weekly_history_available', false,
      'data_as_of', cast(s.pulled_at AS STRING),
      'source', 'silver_90_day_snapshot'
    ), map('ignoreNullFields', 'false'))
    FROM hackcamp.silver.repos s
    WHERE lower(s.repo_id) = lower(trim(repo))
    LIMIT 1),
    to_json(named_struct('repo_id', repo, 'found', false,
      'message', 'repository not found in the required snapshot tables'), map('ignoreNullFields', 'false'))
  )
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_release_history(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Latest release only, dated against the frozen collection time. Full release history and inter-release gaps are unavailable. Missing release data is not evidence of abandonment.'
RETURN (
  SELECT coalesce(
    (SELECT to_json(named_struct(
      'repo_id', s.repo_id,
      'found', true,
      'last_release_at', cast(s.last_release_at AS STRING),
      'days_since_release', datediff(to_date(s.pulled_at), to_date(s.last_release_at)),
      'full_history_available', false,
      'releases', CASE WHEN s.last_release_at IS NULL
        THEN cast(array() AS ARRAY<STRUCT<released_at: STRING, days_since_previous: INT>>)
        ELSE array(named_struct('released_at', cast(s.last_release_at AS STRING),
          'days_since_previous', cast(NULL AS INT))) END,
      'data_as_of', cast(s.pulled_at AS STRING),
      'source', 'silver_latest_release_snapshot'
    ), map('ignoreNullFields', 'false'))
    FROM hackcamp.silver.repos s
    WHERE lower(s.repo_id) = lower(trim(repo))
    LIMIT 1),
    to_json(named_struct('repo_id', repo, 'found', false,
      'message', 'repository not found in the required snapshot tables'), map('ignoreNullFields', 'false'))
  )
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_issue_backlog(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Collected open issue and PR counts only. Maintainer reply rates, unanswered counts and first-response times were not collected and remain null. Backlog size alone does not establish maintainer silence.'
RETURN (
  SELECT coalesce(
    (SELECT to_json(named_struct(
      'repo_id', s.repo_id,
      'found', true,
      'open_issues', s.open_issues,
      'open_prs', s.open_prs,
      'maintainer_reply_rate', cast(NULL AS DOUBLE),
      'unanswered_count', cast(NULL AS INT),
      'estimated_unanswered', cast(NULL AS INT),
      'median_first_response_hours', cast(NULL AS DOUBLE),
      'response_metrics_available', false,
      'data_as_of', cast(s.pulled_at AS STRING),
      'source', 'silver_backlog_counts'
    ), map('ignoreNullFields', 'false'))
    FROM hackcamp.silver.repos s
    WHERE lower(s.repo_id) = lower(trim(repo))
    LIMIT 1),
    to_json(named_struct('repo_id', repo, 'found', false,
      'message', 'repository not found in the required snapshot tables'), map('ignoreNullFields', 'false'))
  )
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_previous_finding(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Most recent persisted agent finding and date, with found=false when no prior verdict exists. Historical findings retain their investigation time and are not current snapshot metrics.'
RETURN (
  SELECT coalesce(
    (SELECT to_json(named_struct(
      'repo_id', f.repo_id,
      'found', true,
      'run_id', f.run_id,
      'risk_level', f.risk_level,
      'confidence', f.confidence,
      'headline', f.headline,
      'explanation', f.explanation,
      'changed_since_last', f.changed_since_last,
      'alternatives', f.alternatives,
      'tool_calls', f.tool_calls,
      'trace_id', f.trace_id,
      'investigated_at', cast(f.investigated_at AS STRING),
      'source', 'agent_findings'
    ), map('ignoreNullFields', 'false'))
    FROM hackcamp.agent.findings f
    WHERE lower(f.repo_id) = lower(trim(repo))
    ORDER BY f.investigated_at DESC NULLS LAST, f.run_id DESC
    LIMIT 1),
    to_json(named_struct('repo_id', repo, 'found', false,
      'message', 'no previous finding'), map('ignoreNullFields', 'false'))
  )
);

-- Preserve this catalog entry for compatibility, but do not offer it to the model.
CREATE OR REPLACE FUNCTION hackcamp.tools.get_contributor_concentration(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Disabled for the hackathon MVP: real contributor history was not collected. Returns unavailable and explicit nulls, never a bus-factor estimate.'
RETURN to_json(named_struct(
  'repo_id', repo,
  'available', false,
  'top_contributor_share', cast(NULL AS DOUBLE),
  'bus_factor_score', cast(NULL AS DOUBLE),
  'contributors', cast(NULL AS INT),
  'message', 'contributor history was not collected; this tool is disabled',
  'source', 'unavailable_in_mvp'
), map('ignoreNullFields', 'false'));
