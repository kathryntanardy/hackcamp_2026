-- Ticket #20: one-line ai_query() summaries for repos the agent never investigated.
-- Safe to re-run: only repos with no finding and no summary yet are sent to the model.

CREATE TABLE IF NOT EXISTS hackcamp.gold.repo_summaries (
  repo_id STRING NOT NULL,
  summary STRING,
  model STRING,
  summarized_at TIMESTAMP
) USING DELTA
COMMENT 'One-line LLM summaries (ai_query) for repos without an agent finding';

MERGE INTO hackcamp.gold.repo_summaries AS t
USING (
  SELECT
    g.repo_id,
    ai_query(
      'databricks-meta-llama-3-3-70b-instruct',
      format_string(
        'In one sentence of at most 25 words, summarise the maintenance health of the '
        'open-source repo %s for a developer deciding whether to depend on it. Use only '
        'these facts and do not invent others. Language: %s. Stars: %s. Baseline health '
        'score (0-100): %s. Status: %s. Days since last release: %s. Commit trend vs the '
        'previous 90 days: %s%%. Archived: %s. Reply with the sentence only.',
        g.repo_id, coalesce(g.language, 'unknown'), coalesce(cast(g.stars AS STRING), 'unknown'),
        coalesce(cast(g.health_score AS STRING), 'unknown'), g.status,
        coalesce(cast(g.days_since_release AS STRING), 'unknown'),
        coalesce(cast(g.commit_trend_pct AS STRING), 'unknown'),
        cast(g.is_archived AS STRING)
      )
    ) AS summary,
    'databricks-meta-llama-3-3-70b-instruct' AS model,
    current_timestamp() AS summarized_at
  FROM (
    SELECT * FROM hackcamp.gold.repo_health
    QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY scored_at DESC) = 1
  ) g
  LEFT ANTI JOIN hackcamp.agent.findings f ON f.repo_id = g.repo_id
  LEFT ANTI JOIN hackcamp.gold.repo_summaries s ON s.repo_id = g.repo_id AND s.summary IS NOT NULL
) AS src
ON t.repo_id = src.repo_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
