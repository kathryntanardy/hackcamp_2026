CREATE TABLE IF NOT EXISTS hackcamp.agent.trace_steps (
  trace_id STRING NOT NULL,
  repo_id STRING NOT NULL,
  run_id STRING NOT NULL,
  payload STRING NOT NULL,
  created_at TIMESTAMP
) USING DELTA
COMMENT 'Ordered public decision summaries and complete tool evidence keyed to an MLflow investigation trace';

-- Agent / scheduled autonomy jobs need SELECT+MODIFY regardless of who created the table.
GRANT SELECT, MODIFY ON TABLE hackcamp.agent.trace_steps TO `account users`;
