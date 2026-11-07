-- Ticket #16 / F11 — stamp UC lineage edges for the demo graph.
-- Safe to re-run. Requires gold + findings to already exist.

-- Retroactively connect gold → findings (agent MERGEs used to write Python-only rows).
MERGE INTO hackcamp.agent.findings AS t
USING (
  SELECT
    f.repo_id,
    f.run_id,
    g.health_score
  FROM hackcamp.agent.findings f
  INNER JOIN hackcamp.gold.repo_health g
    ON f.repo_id = g.repo_id
) AS s
ON t.repo_id = s.repo_id AND t.run_id = s.run_id
WHEN MATCHED THEN UPDATE SET t.tool_calls = t.tool_calls;

-- Demo-facing join: Catalog Explorer lineage shows gold + findings as upstream.
CREATE OR REPLACE VIEW hackcamp.gold.verdicts_lineage AS
SELECT
  g.repo_id,
  g.health_score,
  g.status AS gold_status,
  g.importance,
  g.language,
  f.run_id AS finding_run_id,
  f.risk_level,
  f.confidence,
  f.headline,
  f.trace_id,
  f.investigated_at
FROM hackcamp.gold.repo_health g
LEFT JOIN (
  SELECT *
  FROM hackcamp.agent.findings
  QUALIFY row_number() OVER (PARTITION BY repo_id ORDER BY investigated_at DESC NULLS LAST) = 1
) f
  ON g.repo_id = f.repo_id;

COMMENT ON VIEW hackcamp.gold.verdicts_lineage IS
  'F11 demo view: latest agent finding joined to gold health. Open Lineage tab to show gold + findings upstream (pipeline is bronze→silver→gold; volume feeds bronze via Auto Loader).';

ALTER VIEW hackcamp.gold.verdicts_lineage SET TAGS (
  'domain' = 'oss-health',
  'tier' = 'gold',
  'product' = 'corpus-explorer'
);
