CREATE TABLE IF NOT EXISTS hackcamp.agent.trace_steps (
  trace_id STRING NOT NULL,
  repo_id STRING NOT NULL,
  run_id STRING NOT NULL,
  payload STRING NOT NULL,
  created_at TIMESTAMP
) USING DELTA
COMMENT 'Ordered public decision summaries and complete tool evidence keyed to an MLflow investigation trace';
