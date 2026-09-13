#!/usr/bin/env bash
# Wait at most 30 minutes for the matching CI image before publishing its chart.
set -euo pipefail
image="${1:?usage: wait_for_release_image.sh registry/image:commit-sha}"
attempts="${IMAGE_WAIT_ATTEMPTS:-91}"
delay="${IMAGE_WAIT_SECONDS:-20}"
if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]] || [[ ! "$delay" =~ ^[0-9]+$ ]]; then
  echo "Image wait attempts must be positive and delay must be non-negative integers" >&2
  exit 2
fi
for ((attempt = 1; attempt <= attempts; attempt++)); do
  if docker manifest inspect "$image" > /dev/null 2>&1; then
    echo "Release image is available: $image"
    exit 0
  fi
  if ((attempt < attempts)); then
    sleep "$delay"
  fi
done
echo "Timed out waiting for release image after $attempts attempts: $image; chart will not publish" >&2
exit 1
