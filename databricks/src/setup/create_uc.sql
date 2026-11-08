-- Unity Catalog namespace for hackcamp corpus explorer
-- Prefer fully-qualified names so this works without USE CATALOG session state.
CREATE CATALOG IF NOT EXISTS hackcamp;

CREATE SCHEMA IF NOT EXISTS hackcamp.raw;
CREATE SCHEMA IF NOT EXISTS hackcamp.bronze;
CREATE SCHEMA IF NOT EXISTS hackcamp.silver;
CREATE SCHEMA IF NOT EXISTS hackcamp.gold;
CREATE SCHEMA IF NOT EXISTS hackcamp.agent;
CREATE SCHEMA IF NOT EXISTS hackcamp.tools;

CREATE VOLUME IF NOT EXISTS hackcamp.raw.github
COMMENT 'Raw GitHub API JSON snapshots for Auto Loader';

CREATE TABLE IF NOT EXISTS hackcamp.agent.findings (
  repo_id STRING NOT NULL,
  run_id STRING NOT NULL,
  risk_level STRING,
  confidence DOUBLE,
  headline STRING,
  explanation STRING,
  evidence ARRAY<STRUCT<signal: STRING, tool: STRING, value: STRING>>,
  changed_since_last STRING,
  alternatives ARRAY<STRING>,
  tool_calls INT,
  trace_id STRING,
  investigated_at TIMESTAMP
) USING DELTA
COMMENT 'Agent investigation verdicts keyed by (repo_id, run_id)';

CREATE TABLE IF NOT EXISTS hackcamp.agent.runs (
  run_id STRING NOT NULL,
  started_at TIMESTAMP,
  repos_triaged INT,
  repos_investigated INT,
  tool_calls_total INT,
  model STRING,
  eval_score DOUBLE
) USING DELTA
COMMENT 'One row per agent run';

CREATE TABLE IF NOT EXISTS hackcamp.agent.tool_cache (
  tool STRING NOT NULL,
  args_hash STRING NOT NULL,
  response STRING,
  fetched_at TIMESTAMP
) USING DELTA
COMMENT 'Cached live GitHub tool responses';

CREATE TABLE IF NOT EXISTS hackcamp.agent.eval_labels (
  repo_id STRING NOT NULL,
  label STRING,
  label_source STRING,
  notes STRING
) USING DELTA
COMMENT 'Ground-truth labels for agent evaluation';

-- On-demand Gemini code scans from the app (POST /api/scans/{repo_id}); files/findings are JSON.
CREATE TABLE IF NOT EXISTS hackcamp.agent.code_scans (
  repo_id STRING NOT NULL,
  commit_sha STRING,
  model STRING,
  files STRING,
  summary STRING,
  findings STRING,
  scanned_at TIMESTAMP
);
