-- F15 / #32: one-shot ai_query classification → silver.repo_categories
-- Run on a Serverless/Pro SQL warehouse. Gold prefers these labels.

CREATE OR REPLACE TABLE hackcamp.silver.repo_categories AS
WITH prompted AS (
  SELECT
    repo_id,
    concat(
      'Classify this GitHub repository into exactly one of these labels ',
      'and reply with only that label: Front-end, Back-end, Machine learning, ',
      'Database, Hardware/embedded, DevOps & infra, other.\n',
      'Repo description: ', coalesce(description, ''),
      '\nTopics: ', coalesce(array_join(topics, ', '), '')
    ) AS prompt
  FROM hackcamp.silver.repos
),
queried AS (
  SELECT
    repo_id,
    ai_query(
      'databricks-meta-llama-3-3-70b-instruct',
      prompt,
      failOnError => false
    ) AS ai
  FROM prompted
)
SELECT
  repo_id,
  coalesce(
    CASE lower(trim(ai.result))
      WHEN 'front-end' THEN 'Front-end'
      WHEN 'frontend' THEN 'Front-end'
      WHEN 'front end' THEN 'Front-end'
      WHEN 'back-end' THEN 'Back-end'
      WHEN 'backend' THEN 'Back-end'
      WHEN 'back end' THEN 'Back-end'
      WHEN 'machine learning' THEN 'Machine learning'
      WHEN 'machine-learning' THEN 'Machine learning'
      WHEN 'ml' THEN 'Machine learning'
      WHEN 'database' THEN 'Database'
      WHEN 'hardware/embedded' THEN 'Hardware/embedded'
      WHEN 'hardware' THEN 'Hardware/embedded'
      WHEN 'embedded' THEN 'Hardware/embedded'
      WHEN 'devops & infra' THEN 'DevOps & infra'
      WHEN 'devops' THEN 'DevOps & infra'
      WHEN 'other' THEN 'other'
      ELSE NULL
    END,
    'other'
  ) AS category,
  trim(ai.result) AS raw_category,
  ai.errorMessage AS error_message,
  'databricks-meta-llama-3-3-70b-instruct' AS model_endpoint,
  current_timestamp() AS classified_at
FROM queried;
