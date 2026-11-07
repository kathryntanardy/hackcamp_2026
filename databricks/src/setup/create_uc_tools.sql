-- Agent tools as Unity Catalog SQL functions (hackcamp.tools)
-- Return JSON strings so Mosaic AI / Python agents can parse tool results uniformly.

CREATE OR REPLACE FUNCTION hackcamp.tools.get_repo_metrics(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Baseline metrics and health score for a repo from gold + silver'
RETURN (
  SELECT to_json(
    named_struct(
      'repo_id', g.repo_id,
      'name', g.name,
      'owner', g.owner,
      'language', g.language,
      'health_score', g.health_score,
      'status', g.status,
      'importance', g.importance,
      'stars', g.stars,
      'dependents', g.dependents,
      'is_archived', g.is_archived,
      'days_since_release', g.days_since_release,
      'commit_trend_pct', g.commit_trend_pct,
      'commits_90d', s.commits_90d,
      'commits_prev_90d', s.commits_prev_90d,
      'open_issues', s.open_issues,
      'open_prs', s.open_prs,
      'contributors', s.contributors,
      'maintainer_reply_rate', s.maintainer_reply_rate,
      'top_contributor_share', s.top_contributor_share,
      'pushed_at', cast(s.pushed_at AS STRING),
      'last_release_at', cast(s.last_release_at AS STRING),
      'scored_at', cast(g.scored_at AS STRING)
    )
  )
  FROM hackcamp.gold.repo_health g
  INNER JOIN hackcamp.silver.repos s ON g.repo_id = s.repo_id
  WHERE g.repo_id = repo
  LIMIT 1
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_commit_trend(repo STRING, weeks INT)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Commit trend for a repo; derived from 90d windows until weekly history is ingested'
RETURN (
  SELECT to_json(
    named_struct(
      'repo_id', s.repo_id,
      'weeks_requested', weeks,
      'commits_90d', s.commits_90d,
      'commits_prev_90d', s.commits_prev_90d,
      'avg_commits_per_week_recent',
        round(s.commits_90d / 12.0, 2),
      'avg_commits_per_week_previous',
        round(s.commits_prev_90d / 12.0, 2),
      'trend_pct',
        CASE
          WHEN s.commits_prev_90d > 0
            THEN round(
              100.0 * (s.commits_90d - s.commits_prev_90d) / s.commits_prev_90d,
              2
            )
          WHEN s.commits_90d > 0 THEN 100.0
          ELSE 0.0
        END,
      'estimated_weekly',
        transform(
          sequence(1, greatest(least(coalesce(weeks, 12), 52), 1)),
          i -> named_struct(
            'week_offset', i,
            'commits',
              CASE
                WHEN i <= greatest(least(coalesce(weeks, 12), 52), 1) / 2
                  THEN cast(round(s.commits_prev_90d / 12.0) AS INT)
                ELSE cast(round(s.commits_90d / 12.0) AS INT)
              END
          )
        ),
      'source', 'derived_from_90d_windows'
    )
  )
  FROM hackcamp.silver.repos s
  WHERE s.repo_id = repo
  LIMIT 1
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_release_history(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Release snapshot and gap since last release (full history when ingested)'
RETURN (
  SELECT to_json(
    named_struct(
      'repo_id', s.repo_id,
      'last_release_at', cast(s.last_release_at AS STRING),
      'days_since_release',
        datediff(current_date(), to_date(s.last_release_at)),
      'releases',
        CASE
          WHEN s.last_release_at IS NULL THEN cast(array() AS ARRAY<STRUCT<released_at: STRING, days_since_previous: INT>>)
          ELSE array(
            named_struct(
              'released_at', cast(s.last_release_at AS STRING),
              'days_since_previous', cast(NULL AS INT)
            )
          )
        END,
      'source', 'last_release_snapshot'
    )
  )
  FROM hackcamp.silver.repos s
  WHERE s.repo_id = repo
  LIMIT 1
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_issue_backlog(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Open issues/PRs and maintainer response signals for a repo'
RETURN (
  SELECT to_json(
    named_struct(
      'repo_id', s.repo_id,
      'open_issues', s.open_issues,
      'open_prs', s.open_prs,
      'maintainer_reply_rate', s.maintainer_reply_rate,
      'estimated_unanswered',
        cast(round((1.0 - coalesce(s.maintainer_reply_rate, 0.0)) * s.open_issues) AS INT),
      'median_first_response_hours',
        CASE
          WHEN s.maintainer_reply_rate >= 0.8 THEN 12
          WHEN s.maintainer_reply_rate >= 0.5 THEN 48
          WHEN s.maintainer_reply_rate >= 0.2 THEN 120
          ELSE 336
        END,
      'source', 'silver_metrics'
    )
  )
  FROM hackcamp.silver.repos s
  WHERE s.repo_id = repo
  LIMIT 1
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_contributor_concentration(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Bus-factor proxy: top contributor share of recent commits'
RETURN (
  SELECT to_json(
    named_struct(
      'repo_id', s.repo_id,
      'top_contributor_share', s.top_contributor_share,
      'bus_factor_score', round(1.0 - coalesce(s.top_contributor_share, 1.0), 3),
      'contributors', s.contributors,
      'window', 'last_100_commits_proxy',
      'source', 'silver_metrics'
    )
  )
  FROM hackcamp.silver.repos s
  WHERE s.repo_id = repo
  LIMIT 1
);

CREATE OR REPLACE FUNCTION hackcamp.tools.get_previous_finding(repo STRING)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Most recent agent verdict for a repo, if any'
RETURN (
  SELECT coalesce(
    (
      SELECT to_json(
        named_struct(
          'repo_id', f.repo_id,
          'run_id', f.run_id,
          'risk_level', f.risk_level,
          'confidence', f.confidence,
          'headline', f.headline,
          'explanation', f.explanation,
          'changed_since_last', f.changed_since_last,
          'alternatives', f.alternatives,
          'tool_calls', f.tool_calls,
          'trace_id', f.trace_id,
          'investigated_at', cast(f.investigated_at AS STRING)
        )
      )
      FROM hackcamp.agent.findings f
      WHERE f.repo_id = repo
      ORDER BY f.investigated_at DESC NULLS LAST
      LIMIT 1
    ),
    to_json(
      named_struct(
        'repo_id', repo,
        'risk_level', cast(NULL AS STRING),
        'found', false,
        'message', 'no previous finding'
      )
    )
  )
);
