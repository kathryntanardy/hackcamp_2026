-- Ticket #30: eligible-only source table for the repo Vector Search index (shared with #18).
-- One row per repo_id. Change Data Feed on so the Delta Sync index picks up edits/deletes.
-- Safe to re-run: MERGE updates changed docs and deletes repos that are no longer eligible.

CREATE TABLE IF NOT EXISTS hackcamp.gold.repo_search_docs (
  repo_id STRING NOT NULL,
  language STRING,
  category STRING,
  status STRING,
  search_text STRING,
  updated_at TIMESTAMP
) USING DELTA
COMMENT 'Embedding source for hackcamp.gold.repo_search_index: name, description, topics, advisory summaries'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

MERGE INTO hackcamp.gold.repo_search_docs AS t
USING (
  WITH gold AS (
    SELECT * FROM hackcamp.gold.repo_health
    QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY scored_at DESC) = 1
  ),
  adv AS (
    SELECT repo_id, concat_ws(' ', slice(collect_list(summary), 1, 20)) AS advisory_text
    FROM hackcamp.silver.repo_advisories WHERE summary IS NOT NULL GROUP BY repo_id
  )
  SELECT g.repo_id, g.language, g.category, g.status,
    concat_ws('\n',
      concat('Repository: ', g.repo_id, ' (', coalesce(g.name, ''), ')'),
      concat('Language: ', coalesce(g.language, 'unknown')),
      concat('Category: ', coalesce(g.category, 'other')),
      concat('Description: ', coalesce(s.description, '')),
      concat('Topics: ', coalesce(array_join(s.topics, ', '), '')),
      concat('Security advisories: ', coalesce(a.advisory_text, 'none'))
    ) AS search_text
  FROM gold g
  LEFT JOIN hackcamp.silver.repos s ON s.repo_id = g.repo_id
  LEFT JOIN adv a ON a.repo_id = g.repo_id
  WHERE g.status <> 'ignored'  -- eligibility: excluded/deprecated repos never enter the index
) AS src
ON t.repo_id = src.repo_id
WHEN MATCHED AND (t.search_text IS DISTINCT FROM src.search_text OR t.status IS DISTINCT FROM src.status
  OR t.category IS DISTINCT FROM src.category OR t.language IS DISTINCT FROM src.language) THEN UPDATE SET
  language = src.language, category = src.category, status = src.status,
  search_text = src.search_text, updated_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (repo_id, language, category, status, search_text, updated_at)
  VALUES (src.repo_id, src.language, src.category, src.status, src.search_text, current_timestamp())
WHEN NOT MATCHED BY SOURCE THEN DELETE;
