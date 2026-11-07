-- Sanity checks after a pipeline update
SELECT language, status, count(*) AS n
FROM hackcamp.gold.repo_health
GROUP BY language, status
ORDER BY language, status;

SELECT status, count(*) AS n
FROM hackcamp.gold.repo_health
GROUP BY status
ORDER BY status;

-- Ignored bin: archived or known-deprecated (should not re-enter agent triage)
SELECT repo_id, health_score, status, is_archived
FROM hackcamp.gold.repo_health
WHERE status = 'ignored'
ORDER BY repo_id;

SELECT repo_id, health_score, status, importance, x, y
FROM hackcamp.gold.repo_health
WHERE status <> 'ignored'
ORDER BY health_score ASC
LIMIT 10;
