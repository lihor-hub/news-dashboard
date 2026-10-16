#!/usr/bin/env bash
set -euo pipefail
cd /workspace

# These named volumes keep container dependencies off the host checkout.
# Refuse to clear a host venv when invoked outside the configured container.
mountpoint -q .venv
mountpoint -q node_modules
sudo chown -R "$(id -u):$(id -g)" .venv node_modules
/usr/local/bin/python -c 'import sys, sysconfig; assert sys.version_info[:2] == (3, 15) and sys.version_info.releaselevel == "final"; assert not sysconfig.get_config_var("Py_GIL_DISABLED")'
/usr/local/bin/python -m venv --clear .venv
.venv/bin/python -m pip install --no-cache-dir -e '.[dev]'
npm ci
.venv/bin/pre-commit install --hook-type pre-commit --hook-type pre-push
.venv/bin/news-dashboard init
