#!/usr/bin/env bash
# Update an existing appliance installation without applying a new Helm topology.
# Never creates resources, rotates credentials, or changes storage/networking.
set -euo pipefail
: "${IMG:?set IMG to the application repository}"
[[ "$IMG" =~ ^[a-z0-9./:_-]+$ ]] || { echo 'Invalid IMG repository' >&2; exit 2; }
if [[ ! "${IMAGE_DIGEST:-}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo 'IMAGE_DIGEST must be sha256:<64 lowercase hex characters>' >&2
  exit 2
fi
namespace=news-dashboard
deployment=news-dashboard-news-dashboard
cronjob=news-dashboard-news-dashboard-ingest
image="${IMG}@${IMAGE_DIGEST}"
# Both must exist before any mutation. Do not infer or recreate host inventory.
old_app=$(kubectl -n "$namespace" get deployment "$deployment" -o 'jsonpath={.spec.template.spec.containers[?(@.name=="news-dashboard")].image}')
old_ingest=$(kubectl -n "$namespace" get cronjob "$cronjob" -o 'jsonpath={.spec.jobTemplate.spec.template.spec.containers[?(@.name=="ingest")].image}')
[[ -n "$old_app" && -n "$old_ingest" ]] || { echo 'Existing application and ingest containers are required' >&2; exit 2; }
rollback() {
  echo 'Image rollout failed; restoring previous application and ingestion images.' >&2
  kubectl -n "$namespace" set image "deployment/$deployment" "news-dashboard=$old_app" || true
  kubectl -n "$namespace" set image "cronjob/$cronjob" "ingest=$old_ingest" || true
  kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=600s || true
}
trap rollback ERR
# Initialization on the real database exceeds the legacy 55-second liveness window.
# Patch together with the image to avoid rolling out an intermediate revision.
kubectl -n "$namespace" patch deployment "$deployment" --type=strategic -p "{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"news-dashboard\",\"image\":\"$image\",\"startupProbe\":{\"httpGet\":{\"path\":\"/api/live\",\"port\":\"http\"},\"periodSeconds\":10,\"timeoutSeconds\":3,\"failureThreshold\":60}}]}}}}"
kubectl -n "$namespace" set image "cronjob/$cronjob" "ingest=$image"
kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=600s
# When called by CI, verify the public endpoint before considering this successful.
if [[ -n "${BUILD_REVISION:-}" ]]; then
  python3 "$(dirname "$0")/verify-deployed-build.py" \
    "${PUBLIC_BASE_URL:-https://news.lihor.ro}" "$BUILD_REVISION" "${BUILD_VERSION:?set BUILD_VERSION}"
fi
trap - ERR
