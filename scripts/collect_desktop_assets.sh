#!/usr/bin/env bash
# Collect only install/update artifacts; reject incomplete desktop builds.
set -euo pipefail

platform="${1:?usage: collect_desktop_assets.sh mac|linux|win [dist] [output]}"
dist="${2:-desktop/dist}"
output="${3:-desktop/dist/release-assets}"
case "$platform" in
  mac) patterns=('*.dmg' '*.zip' '*.dmg.blockmap' '*.zip.blockmap' 'latest-mac.yml') ;;
  linux) patterns=('*.AppImage' 'latest-linux.yml') ;;
  win) patterns=('*.exe' '*.exe.blockmap' 'latest.yml') ;;
  *) echo "Unknown desktop platform: $platform" >&2; exit 2 ;;
esac
mkdir -p "$output"
shopt -s nullglob
for pattern in "${patterns[@]}"; do
  # Patterns above contain no whitespace; expand their glob against the quoted directory.
  # shellcheck disable=SC2206
  matches=("$dist"/$pattern)
  if [ "${#matches[@]}" -eq 0 ]; then
    echo "Missing desktop artifact: $dist/$pattern" >&2
    exit 1
  fi
  for artifact in "${matches[@]}"; do
    test -s "$artifact"
    cp "$artifact" "$output/"
  done
done
