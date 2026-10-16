#!/usr/bin/env bash
# Executed inside the actual devcontainer by the native lifecycle CI jobs.
set -euo pipefail
cd /workspace
test "$(id -u)" -ne 0
test -w /workspace
probe=$(mktemp /workspace/.nd-permissions.XXXXXX)
rm "$probe"
test ! -e .venv/stale-python314-marker
test "$(command -v python)" = /workspace/.venv/bin/python
test "$(node -p 'process.versions.node.split(".")[0]')" = 26
python -VV
node --version
npm --version
rustc --version
cargo --version
cat /etc/os-release
python - <<'PY'
import json
import os
import platform
import sys
import sysconfig

import psycopg

assert sys.version_info[:2] == (3, 15)
assert sys.version_info.releaselevel == 'final'
assert not sysconfig.get_config_var('Py_GIL_DISABLED')
for key, database in [('DATABASE_URL', 'news_dashboard'), ('TEST_DATABASE_URL', 'news_dashboard_test')]:
    with psycopg.connect(os.environ[key]) as conn:
        row = conn.execute("SELECT current_database(), current_user, current_setting('max_parallel_workers_per_gather')").fetchone()
        assert row == (database, 'news_dashboard', '0'), row
        if key == 'DATABASE_URL':
            assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] > 0
print(json.dumps({'python': sys.version, 'machine': platform.machine(), 'os': platform.platform(), 'gil_disabled': sysconfig.get_config_var('Py_GIL_DISABLED')}))
PY
python -m pip check
python -m pip freeze
for tool in git make gcc cargo rustc psql ruff mypy ty pyrefly pre-commit news-dashboard; do
    command -v "$tool"
done
test -x "$(git rev-parse --git-path hooks/pre-commit)"
test -x "$(git rev-parse --git-path hooks/pre-push)"
# Exercise the editor-selected interpreter and real development servers.
python -m uvicorn news_dashboard.main:app --host 127.0.0.1 --port 8080 > /tmp/nd-backend.log 2>&1 &
backend_pid=$!
npm run dev -- --host 127.0.0.1 > /tmp/nd-frontend.log 2>&1 &
frontend_pid=$!
trap 'kill "$backend_pid" "$frontend_pid" 2>/dev/null || true' EXIT
for endpoint in http://127.0.0.1:8080/api/ready http://127.0.0.1:5173; do
    curl --retry 30 --retry-delay 2 --retry-connrefused --fail --silent "$endpoint" > /dev/null
done
