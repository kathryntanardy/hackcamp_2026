#!/usr/bin/env bash
# Store a GitHub PAT in the hackcamp secret scope (never commit the token).
# Usage:
#   export GITHUB_TOKEN=ghp_...
#   ./databricks/scripts/put_github_token.sh
set -euo pipefail
PROFILE="${DATABRICKS_CONFIG_PROFILE:-school}"
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [[ -z "${TOKEN}" ]]; then
  echo "Set GITHUB_TOKEN (or GH_TOKEN) then re-run." >&2
  exit 1
fi
databricks secrets put-secret hackcamp github_token --string-value "${TOKEN}" --profile "${PROFILE}"
echo "Stored secret hackcamp/github_token"
databricks secrets list-secrets hackcamp --profile "${PROFILE}"
