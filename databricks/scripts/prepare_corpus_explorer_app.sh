#!/usr/bin/env bash
# Stage backend + built frontend into databricks/apps/corpus-explorer for Apps deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/backend"
DEST="$ROOT/databricks/apps/corpus-explorer"
FRONT="$ROOT/frontend"

echo "Building frontend…"
(cd "$FRONT" && npm run build)

echo "Staging app at $DEST"
rm -rf "$DEST"
mkdir -p "$DEST/app" "$DEST/tests" "$DEST/static"

cp -a "$SRC/app/." "$DEST/app/"
cp -a "$SRC/app.yaml" "$DEST/app.yaml"
cp -a "$SRC/requirements.txt" "$DEST/requirements.txt"
cp -a "$SRC/run.py" "$DEST/run.py"
cp -a "$SRC/tests/." "$DEST/tests/" 2>/dev/null || true
cp -a "$FRONT/dist/." "$DEST/static/"

# Drop local caches that may have been copied with app/
find "$DEST" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -type d -name '.pytest_cache' -prune -exec rm -rf {} + 2>/dev/null || true

echo "Staged $(find "$DEST" -type f | wc -l) files"
ls -la "$DEST"
