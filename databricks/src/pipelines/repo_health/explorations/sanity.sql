-- Sanity checks after a pipeline update
SELECT language, status, count(*) AS n
FROM hackcamp.gold.repo_health
GROUP BY language, status
ORDER BY language, status;

SELECT repo_id, health_score, status, importance, x, y
FROM hackcamp.gold.repo_health
ORDER BY health_score ASC
LIMIT 10;
