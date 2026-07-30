#!/usr/bin/env bash
# Manual deploy to the production single-node Kubernetes cluster.
# CI runs the equivalent steps automatically on push to main.
#
# Usage:
#   IMAGE_DIGEST=sha256:<digest> ./scripts/deploy-local-k8s.sh
#   ./scripts/deploy-local-k8s.sh --render
#
# Required environment:
#   INGRESS_CUTOVER_ENABLED
#                        must be exactly "true" before a live apply
#   SESSION_SECRET       long random session-signing value
#   POSTGRES_PASSWORD    password for the bundled PostgreSQL role
#   POSTGRES_HOST_PATH   existing host-backed PostgreSQL data path
#   IMAGE_DIGEST         exact sha256 digest of the already-published image
#
# Optional environment:
#   OPENAI_API_KEY       enables Ask AI
#   ADDITIONAL_EGRESS_VALUES_FILE
#                        persistent non-secret Helm values for private/custom
#                        networkPolicy.additionalEgress destinations
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck disable=SC1091 # Resolved from this script's absolute directory.
source "${SCRIPT_DIR}/production-deploy-lib.sh"
cd "${ROOT}"

if [[ "${1:-}" == "--render" ]]; then
  SESSION_SECRET="render-only-session-secret"
  POSTGRES_PASSWORD="render-only-postgres-password"
  IMAGE_DIGEST="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  prepare_production_helm_secret_files
  helm template news-dashboard ./helm/news-dashboard \
    --values ./helm/news-dashboard/values-production.yaml \
    --set-string "image.digest=${IMAGE_DIGEST}" \
    --set-string postgresql.persistence.hostPath= \
    "${PRODUCTION_HELM_SECRET_ARGS[@]}"
  exit 0
fi

if ! production_cutover_enabled; then
  echo "Set INGRESS_CUTOVER_ENABLED=true only after completing human rollout issue #1302." >&2
  exit 2
fi

if [[ -z "${SESSION_SECRET:-}" ]]; then
  echo "SESSION_SECRET is required for production auth." >&2
  exit 1
fi

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "POSTGRES_PASSWORD is required for production PostgreSQL." >&2
  exit 1
fi

if [[ -z "${POSTGRES_HOST_PATH:-}" ]]; then
  echo "POSTGRES_HOST_PATH is required to preserve production data." >&2
  exit 1
fi
if [[ -z "${IMAGE_DIGEST:-}" ]]; then
  echo "IMAGE_DIGEST is required for a production deployment." >&2
  exit 1
fi
if [[ ! "${IMAGE_DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "IMAGE_DIGEST must be sha256:<64 lowercase hex characters>." >&2
  exit 1
fi

prepare_production_helm_secret_files

ADDITIONAL_EGRESS_HELM_ARGS=()
if [[ -n "${ADDITIONAL_EGRESS_VALUES_FILE:-}" ]]; then
  if [[ ! -f "${ADDITIONAL_EGRESS_VALUES_FILE}" ]]; then
    echo "ADDITIONAL_EGRESS_VALUES_FILE must name a readable Helm values file." >&2
    exit 1
  fi
  ADDITIONAL_EGRESS_HELM_ARGS+=(--values "${ADDITIONAL_EGRESS_VALUES_FILE}")
fi

AI_HELM_ARGS=()
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  AI_HELM_ARGS+=(--set app.ai.existingSecret=news-dashboard-ai)
fi

# Clear the chart's legacy single-node default, then apply the required
# installation-specific path from runtime configuration.
POSTGRES_HELM_ARGS=(--set-string "postgresql.persistence.hostPath=")
POSTGRES_HELM_ARGS+=(--set-string "postgresql.persistence.hostPath=${POSTGRES_HOST_PATH}")

REPO="${REPO:-localhost:5000/news-dashboard}"
IMAGE="${REPO}@${IMAGE_DIGEST}"

echo "→ Pulling ${IMAGE}"
docker pull "${IMAGE}"

kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "→ Applying AI credentials secret"
  kubectl -n news-dashboard create secret generic news-dashboard-ai \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo "→ Deploying with Helm (digest=${IMAGE_DIGEST})"
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set image.repository="${REPO}" \
  --set-string "image.digest=${IMAGE_DIGEST}" \
  --set-string image.pullSecretName="${PULL_SECRET_NAME:-}" \
  "${ADDITIONAL_EGRESS_HELM_ARGS[@]}" \
  "${POSTGRES_HELM_ARGS[@]}" \
  "${PRODUCTION_HELM_SECRET_ARGS[@]}" \
  "${AI_HELM_ARGS[@]}" \
  --set-string app.publicBaseUrl="https://news.lihor.ro"

echo "→ Waiting for Postgres"
kubectl -n news-dashboard rollout status \
  statefulset/news-dashboard-news-dashboard-postgres --timeout=120s

echo "→ Waiting for app"
kubectl -n news-dashboard rollout status \
  deploy/news-dashboard-news-dashboard --timeout=120s

echo "→ Verifying public TLS Ingress"
curl -sf --max-time 10 --retry 6 --retry-delay 5 \
  https://news.lihor.ro/api/health | grep '"status":"ok"'
echo "✓ Done"
