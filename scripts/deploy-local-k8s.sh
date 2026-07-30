#!/usr/bin/env bash
# Manual deploy to the production single-node Kubernetes cluster.
# CI runs the equivalent steps automatically on push to main.
#
# Usage:
#   ./scripts/deploy-local-k8s.sh [TAG]
#
# Required environment:
#   SESSION_SECRET       long random session-signing value
#   POSTGRES_PASSWORD    password for the bundled PostgreSQL role
#   POSTGRES_HOST_PATH   existing host-backed PostgreSQL data path
#
# Optional environment:
#   OPENAI_API_KEY       enables Ask AI
#
# TAG defaults to the current git SHA.  Pass 'latest' only for quick local
# testing — never rely on 'latest' for real deploys (imagePullPolicy won't
# re-pull if the tag is already cached).
set -euo pipefail

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

AI_HELM_ARGS=()
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  AI_HELM_ARGS+=(--set app.ai.existingSecret=news-dashboard-ai)
fi

# Clear the chart's legacy single-node default, then apply the required
# installation-specific path from runtime configuration.
POSTGRES_HELM_ARGS=(--set-string "postgresql.persistence.hostPath=")
POSTGRES_HELM_ARGS+=(--set-string "postgresql.persistence.hostPath=${POSTGRES_HOST_PATH}")

REPO="${REPO:-localhost:5000/news-dashboard}"
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="${REPO}:${TAG}"

echo "→ Building ${IMAGE}"
docker build -t "${IMAGE}" .
echo "→ Pushing ${IMAGE}"
docker push "${IMAGE}"

kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "→ Applying AI credentials secret"
  kubectl -n news-dashboard create secret generic news-dashboard-ai \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo "→ Deploying with Helm (tag=${TAG})"
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set image.repository="${REPO}" \
  --set image.tag="${TAG}" \
  --set-string image.pullSecretName="${PULL_SECRET_NAME:-}" \
  --set-string app.auth.sessionSecret="${SESSION_SECRET}" \
  --set-string postgresql.password="${POSTGRES_PASSWORD}" \
  "${POSTGRES_HELM_ARGS[@]}" \
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
