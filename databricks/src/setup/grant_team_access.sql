-- Team UC grants so Jobs / notebooks can read-write agent + gold tables.
-- Idempotent. Add teammates as needed for the hackathon workspace.

-- Catalog / schema use
GRANT USE CATALOG ON CATALOG hackcamp TO `philip03ho@gmail.com`;
GRANT USE SCHEMA ON SCHEMA hackcamp.agent TO `philip03ho@gmail.com`;
GRANT USE SCHEMA ON SCHEMA hackcamp.gold TO `philip03ho@gmail.com`;
GRANT USE SCHEMA ON SCHEMA hackcamp.silver TO `philip03ho@gmail.com`;
GRANT USE SCHEMA ON SCHEMA hackcamp.bronze TO `philip03ho@gmail.com`;
GRANT USE SCHEMA ON SCHEMA hackcamp.tools TO `philip03ho@gmail.com`;

GRANT SELECT, MODIFY, CREATE TABLE ON SCHEMA hackcamp.agent TO `philip03ho@gmail.com`;
GRANT SELECT ON SCHEMA hackcamp.gold TO `philip03ho@gmail.com`;
GRANT SELECT ON SCHEMA hackcamp.silver TO `philip03ho@gmail.com`;
GRANT SELECT ON SCHEMA hackcamp.bronze TO `philip03ho@gmail.com`;
GRANT EXECUTE ON SCHEMA hackcamp.tools TO `philip03ho@gmail.com`;

-- Critical tables used by agent_run / scheduled_autonomy
GRANT SELECT, MODIFY ON TABLE hackcamp.agent.findings TO `philip03ho@gmail.com`;
GRANT SELECT, MODIFY ON TABLE hackcamp.agent.runs TO `philip03ho@gmail.com`;
GRANT SELECT, MODIFY ON TABLE hackcamp.agent.trace_steps TO `philip03ho@gmail.com`;
GRANT SELECT, MODIFY ON TABLE hackcamp.agent.tool_cache TO `philip03ho@gmail.com`;
GRANT SELECT ON TABLE hackcamp.agent.eval_labels TO `philip03ho@gmail.com`;
GRANT SELECT ON TABLE hackcamp.gold.repo_health TO `philip03ho@gmail.com`;
GRANT SELECT ON TABLE hackcamp.silver.repos TO `philip03ho@gmail.com`;
