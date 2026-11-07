#!/usr/bin/env bash
# Print every code change since the last commit that touched PRD.md,
# through the working tree (uncommitted + untracked files included).
# Empty output = nothing to sync (gate 4).
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
base=$(git log -1 --format=%H -- PRD.md 2>/dev/null || true)
if [ -z "$base" ]; then
  echo "ERROR: PRD.md has never been committed; no base to diff from." >&2
  exit 2
fi

# Skip the PRD itself and tooling dirs (not product changes).
git diff "$base" -- . ':(exclude)PRD.md' ':(exclude).claude' ':(exclude).entire'

git ls-files --others --exclude-standard | { grep -Ev '^(PRD\.md$|\.claude/|\.entire/)' || true; } | while read -r f; do
  echo "=== untracked: $f ==="
  cat "$f"
done
