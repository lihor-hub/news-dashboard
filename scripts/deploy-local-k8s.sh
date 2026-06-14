#!/usr/bin/env bash
# Manual deploy to a local single-node Kubernetes cluster.
# CI runs the equivalent steps automatically on push to main.
#
# Usage:
#   ./scripts/deploy-local-k8s.sh [TAG]
#
# Ask AI requires OPENAI_API_KEY in this shell.
#
# TAG defaults to the current git SHA.  Pass 'latest' only for quick local
# testing — never rely on 'latest' for real deploys (imagePullPolicy won't
# re-pull if the tag is already cached).
set -euo pipefail

AI_HELM_ARGS=()
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  AI_HELM_ARGS+=(--set app.ai.existingSecret=news-dashboard-ai)
fi

REPO="${REPO:-localhost:5000/news-dashboard}"
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="${REPO}:${TAG}"

echo "→ Building ${IMAGE}"
docker build -t "${IMAGE}" .
echo "→ Pushing ${IMAGE}"
docker push "${IMAGE}"

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "→ Applying AI credentials secret"
  kubectl -n news-dashboard create secret generic news-dashboard-ai \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo "→ Deploying with Helm (tag=${TAG})"
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --set image.repository="${REPO}" \
  --set image.tag="${TAG}" \
  --set-string image.pullSecretName="${PULL_SECRET_NAME:-}" \
  --set service.type=NodePort \
  --set service.nodePort=30088 \
  --set persistence.hostPath="${DATA_HOSTPATH:-/data/news-dashboard-data}" \
  --set postgresql.persistence.hostPath="${POSTGRES_HOSTPATH:-/data/news-dashboard-postgres-data}" \
  "${AI_HELM_ARGS[@]}" \
  --set ingress.enabled=false

echo "→ Waiting for Postgres"
kubectl -n news-dashboard rollout status statefulset/news-dashboard-news-dashboard-postgres

echo "→ Waiting for app"
kubectl -n news-dashboard rollout status deploy/news-dashboard-news-dashboard
echo "✓ Done"
