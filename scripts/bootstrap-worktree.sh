#!/usr/bin/env bash
# Bootstrap a fresh git worktree: copy the ignored .env from the main checkout
# and install Python + npm dependencies so pre-commit/pre-push hooks can run.
# Safe to re-run: existing .env, .venv, and node_modules are left alone.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

main_checkout=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
if [ ! -f .env ] && [ "$main_checkout" != "$PWD" ] && [ -f "$main_checkout/.env" ]; then
  cp "$main_checkout/.env" .env
  echo "Copied .env from $main_checkout"
fi

# uv sync --frozen (not `make install`'s pip install -e) keeps uv.lock untouched.
[ -d .venv ] || uv sync --frozen --all-extras
[ -d node_modules ] || npm ci

for var in DATABASE_URL TEST_DATABASE_URL; do
  if [ ! -f .env ] || ! grep -q "^${var}=" .env; then
    echo "ERROR: ${var} is not set in .env — backend tests cannot reach PostgreSQL." >&2
    exit 1
  fi
done

echo "Worktree ready. Keep .venv/bin on PATH so pre-commit hooks find their tools."
