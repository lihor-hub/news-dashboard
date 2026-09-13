#!/usr/bin/env bash
# Inject computed app versions into packaging metadata for CI builds.
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${1:-}"
VERSION="${VERSION:-${V:-}}"
CODE="${CODE:-}"

if [ -z "$TARGET" ]; then
  echo "usage: scripts/inject_app_version.sh android|desktop|helm" >&2
  exit 2
fi

if [ -z "$VERSION" ]; then
  echo "VERSION or V must be set" >&2
  exit 2
fi

case "$TARGET" in
  android)
    if [ -z "$CODE" ]; then
      echo "CODE must be set for Android version injection" >&2
      exit 2
    fi

    # Patterns require at least one digit to avoid matching empty strings
    # (POSIX BRE: [0-9][0-9]* = one or more).
    sed -i "s/versionCode [0-9][0-9]*/versionCode $CODE/" android/app/build.gradle
    sed -i "s/versionName \"[0-9][^\"]*\"/versionName \"$VERSION\"/" android/app/build.gradle
    jq --arg v "$VERSION" --argjson c "$CODE" \
      '.appVersionName = $v | .appVersionCode = $c' \
      android/twa-manifest.json > /tmp/twa.json
    mv /tmp/twa.json android/twa-manifest.json
    ;;
  desktop)
    jq --arg v "$VERSION" '.version = $v' \
      desktop/package.json > /tmp/pkg.json
    mv /tmp/pkg.json desktop/package.json
    ;;
  helm)
    if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ ! "${IMAGE_TAG:-}" =~ ^[0-9a-f]{40}$ ]]; then
      echo "Helm injection requires a release VERSION (x.y.z) and IMAGE_TAG (full commit SHA)" >&2
      exit 2
    fi
    chart_tmp=$(mktemp)
    values_tmp=$(mktemp)
    trap 'rm -f "$chart_tmp" "$values_tmp"' EXIT
    awk -v version="$VERSION" '
      /^version:/ { $0 = "version: " version }
      /^appVersion:/ { $0 = "appVersion: \"" version "\"" }
      { print }
    ' helm/news-dashboard/Chart.yaml > "$chart_tmp"
    awk -v tag="$IMAGE_TAG" '
      /^image:/ { in_image = 1; print; next }
      /^[^[:space:]#]/ { in_image = 0 }
      in_image && /^  tag:/ { $0 = "  tag: \"" tag "\""; found = 1 }
      { print }
      END { if (!found) exit 1 }
    ' helm/news-dashboard/values.yaml > "$values_tmp"
    mv "$chart_tmp" helm/news-dashboard/Chart.yaml
    mv "$values_tmp" helm/news-dashboard/values.yaml
    ;;
  *)
    echo "unknown target: $TARGET" >&2
    exit 2
    ;;
esac
