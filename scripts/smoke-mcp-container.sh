#!/usr/bin/env bash
set -euo pipefail

smoke_suffix="${GITHUB_RUN_ID:-local}-$$"
network_name="nd-mcp-smoke-${smoke_suffix}"
postgres_name="nd-mcp-postgres-${smoke_suffix}"
app_name="nd-mcp-app-${smoke_suffix}"
image_name="${MCP_SMOKE_IMAGE:-news-dashboard:mcp-smoke-${smoke_suffix}}"
postgres_password="mcp-smoke-postgres-password"
session_secret="mcp-smoke-session-secret-000000000000000000000000"
app_port=""
smoke_token=""

cleanup() {
  rm -f "/tmp/mcp-smoke-response-$$" "/tmp/mcp-smoke-disabled-$$"
  docker rm -f "${app_name}" "${postgres_name}" >/dev/null 2>&1 || true
  docker network rm "${network_name}" >/dev/null 2>&1 || true
  if [[ -z "${MCP_SMOKE_IMAGE:-}" ]]; then
    docker image rm "${image_name}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

docker network create "${network_name}" >/dev/null
docker run -d --name "${postgres_name}" --network "${network_name}" \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD="${postgres_password}" \
  pgvector/pgvector:pg16 >/dev/null

for _attempt in $(seq 1 60); do
  if docker exec "${postgres_name}" pg_isready -U news_dashboard -d news_dashboard \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${postgres_name}" pg_isready -U news_dashboard -d news_dashboard >/dev/null

if [[ -z "${MCP_SMOKE_IMAGE:-}" ]]; then
  docker build -t "${image_name}" . >/dev/null
fi

docker run --rm "${image_name}" python -c '
import os, shutil, sys, sysconfig
assert sys.version_info[:2] == (3, 15) and sys.version_info.releaselevel == "final"
assert not sysconfig.get_config_var("Py_GIL_DISABLED")
assert os.getuid() != 0
assert all(shutil.which(tool) is None for tool in ("gcc", "cc", "rustc", "cargo"))
print(sys.version)
'
# Dockerfile runs pip check before finalizing the image. Runtime probes must
# also work when the unused package installer is removed by image hardening.
docker run --rm "${image_name}" news-dashboard --help >/dev/null

start_app() {
  local enabled="$1"
  docker run -d --name "${app_name}" --network "${network_name}" \
    -p 127.0.0.1::8080 \
    -e POSTGRES_HOST="${postgres_name}" \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB=news_dashboard \
    -e POSTGRES_USER=news_dashboard \
    -e POSTGRES_PASSWORD="${postgres_password}" \
    -e SESSION_SECRET="${session_secret}" \
    -e BOOTSTRAP_ADMIN_USERNAME=mcp-smoke-admin \
    -e BOOTSTRAP_ADMIN_PASSWORD=mcp-smoke-password \
    -e MCP_SERVER_ENABLED="${enabled}" \
    -e MCP_ALLOWED_HOSTS=localhost:8080 \
    -e MCP_ALLOWED_ORIGINS=http://localhost:8080 \
    "${image_name}" >/dev/null
  app_port="$(docker port "${app_name}" 8080/tcp | sed -n 's/.*://p')"
  test -n "${app_port}"
}

wait_for_app() {
  for _attempt in $(seq 1 90); do
    if curl --fail --silent --show-error \
      -H 'Host: localhost:8080' \
      "http://127.0.0.1:${app_port}/api/ready" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  docker logs "${app_name}" >&2
  return 1
}

start_app true
wait_for_app
docker exec "${app_name}" news-dashboard init
# Execute the compose readiness command inside the image. Helm uses the same
# readiness endpoint and /api/live for liveness; both must work without auth.
docker exec "${app_name}" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/api/ready", timeout=5).read()'
for endpoint in health live ready; do
  response="$(curl --fail --silent --show-error -H 'Host: localhost:8080' \
    "http://127.0.0.1:${app_port}/api/${endpoint}")"
  test "$response" = '{"status":"ok"}'
done
expected_version="$(docker exec "${app_name}" python -c 'from pathlib import Path; print(Path("/app/VERSION").read_text(encoding="utf-8").strip())')"
curl --fail --silent --show-error -H 'Host: localhost:8080' \
  "http://127.0.0.1:${app_port}/api/version" | \
  python -c 'import json, sys; assert json.load(sys.stdin)["version"] == sys.argv[1]' "$expected_version"
echo "Container health/readiness and version ${expected_version} passed"

# Mint inside the container and capture stdout only in memory. The bearer never
# appears in a command argument, image layer, tracked file, or CI log.
smoke_token="$(docker exec "${app_name}" python -c '
from news_dashboard.auth import get_user_by_username
from news_dashboard.db import close_connection_pool
from news_dashboard.mcp.service import create_token
try:
    user = get_user_by_username("mcp-smoke-admin")
    if user is None:
        raise SystemExit("bootstrap user missing")
    print(create_token(int(user["id"]), "container smoke", scopes=("search",))["token"])
finally:
    close_connection_pool()
')"
test -n "${smoke_token}"

MCP_SMOKE_PORT="${app_port}" MCP_SMOKE_TOKEN="${smoke_token}" python - <<'PY'
import asyncio
import os

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def main() -> None:
    port = os.environ["MCP_SMOKE_PORT"]
    token = os.environ["MCP_SMOKE_TOKEN"]
    transport = StreamableHttpTransport(
        f"http://127.0.0.1:{port}/mcp/",
        auth=token,
        headers={"Host": "localhost:8080"},
    )
    async with Client(transport) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert names == {"list_latest_news", "list_news_sources", "search_news"}
        result = await client.call_tool("list_latest_news", {"limit": 1})
        assert result.is_error is False


asyncio.run(main())
PY

initialize='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"container-smoke","version":"1"}}}'
content_type='Content-Type: application/json'
accept='Accept: application/json, text/event-stream'

unauthenticated_code="$(curl --silent --output /tmp/mcp-smoke-response-$$ \
  --write-out '%{http_code}' -H 'Host: localhost:8080' -H "${content_type}" -H "${accept}" \
  --data "${initialize}" "http://127.0.0.1:${app_port}/mcp/")"
test "${unauthenticated_code}" = 401
! grep -qi '<!doctype html' /tmp/mcp-smoke-response-$$

bad_host_code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Host: attacker.example' -H "${content_type}" -H "${accept}" \
  --data "${initialize}" "http://127.0.0.1:${app_port}/mcp/")"
test "${bad_host_code}" = 421

bad_origin_code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Host: localhost:8080' -H 'Origin: https://attacker.example' \
  -H "${content_type}" -H "${accept}" --data "${initialize}" \
  "http://127.0.0.1:${app_port}/mcp/")"
test "${bad_origin_code}" = 403

rm -f /tmp/mcp-smoke-response-$$
docker rm -f "${app_name}" >/dev/null
start_app false
wait_for_app

disabled_code="$(curl --silent --output /tmp/mcp-smoke-disabled-$$ \
  --write-out '%{http_code}' -H 'Host: localhost:8080' -H "${content_type}" -H "${accept}" \
  --data "${initialize}" "http://127.0.0.1:${app_port}/mcp/")"
test "${disabled_code}" = 404
! grep -qi '<!doctype html' /tmp/mcp-smoke-disabled-$$
rm -f /tmp/mcp-smoke-disabled-$$

# PostgreSQL stays private to the Docker network; only the application has a
# host port binding.
test -z "$(docker port "${postgres_name}" 5432/tcp 2>/dev/null || true)"

echo "MCP container smoke passed"
