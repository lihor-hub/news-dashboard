#!/usr/bin/env bash
# Inject computed app versions into packaging metadata for CI builds.
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${1:-}"
VERSION="${VERSION:-${V:-}}"
CODE="${CODE:-}"

if [ -z "$TARGET" ]; then
  echo "usage: scripts/inject_app_version.sh android|desktop" >&2
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
  *)
    echo "unknown target: $TARGET" >&2
    exit 2
    ;;
esac
