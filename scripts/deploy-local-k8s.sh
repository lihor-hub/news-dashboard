#!/usr/bin/env bash
# Manual deploy to the local Kubernetes cluster on ioachim-minipc.
# CI runs the equivalent steps automatically on push to main.
#
# Usage:
#   ./scripts/deploy-local-k8s.sh [TAG]
#
# TAG defaults to the current git SHA.  Pass 'latest' only for quick local
# testing — never rely on 'latest' for real deploys (imagePullPolicy won't
# re-pull if the tag is already cached).
set -euo pipefail

REPO="${REPO:-localhost:5000/news-dashboard}"
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="${REPO}:${TAG}"

echo "→ Building ${IMAGE}"
docker build -t "${IMAGE}" .
echo "→ Pushing ${IMAGE}"
docker push "${IMAGE}"

echo "→ Deploying with Helm (tag=${TAG})"
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --set image.repository="${REPO}" \
  --set image.tag="${TAG}" \
  --set-string image.pullSecretName="${PULL_SECRET_NAME:-}" \
  --set service.type=NodePort \
  --set service.nodePort=30088 \
  --set persistence.hostPath=/home/ioachim-minipc/news-dashboard-data \
  --set postgresql.persistence.hostPath=/home/ioachim-minipc/news-dashboard-postgres-data \
  --set ingress.enabled=false

echo "→ Waiting for Postgres"
kubectl -n news-dashboard rollout status statefulset/news-dashboard-news-dashboard-postgres

echo "→ Waiting for app"
kubectl -n news-dashboard rollout status deploy/news-dashboard-news-dashboard
echo "✓ Done"
