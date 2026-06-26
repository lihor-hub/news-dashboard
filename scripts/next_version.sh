#!/usr/bin/env bash
# Single source of truth for "what version is this build?", shared by ci.yml
# (bakes it into the image) and release.yml (tags + builds artifacts).
#
# Computes the next semantic version from the latest v* tag plus the
# Conventional Commits since it, falling back to the VERSION file when no tags
# exist. Stateless: nothing is committed — the version lives in git tags.
#
# Prints KEY=VALUE lines to stdout:
#   version=1.2.3
#   code=1002003
#   tag=v1.2.3
#   bumped=true|false   # false = only ci/docs/test/chore commits since last tag
set -euo pipefail

cd "$(dirname "$0")/.."

LAST_TAG=$(git tag --list 'v*' --sort=-version:refname | head -1)
if [ -z "$LAST_TAG" ]; then
  BASE=$(cat VERSION)
  RESULT=$(python3 scripts/bump_version.py --current "$BASE")
else
  BASE="${LAST_TAG#v}"
  RESULT=$(python3 scripts/bump_version.py --current "$BASE" --since-tag "$LAST_TAG")
fi

BUMP=$(printf '%s\n' "$RESULT" | sed -n 's/^bump=//p')
NEXT=$(printf '%s\n' "$RESULT" | sed -n 's/^next=//p')
CODE=$(printf '%s\n' "$RESULT" | sed -n 's/^code=//p')

if [ "$BUMP" = "none" ]; then BUMPED=false; else BUMPED=true; fi

echo "version=$NEXT"
echo "code=$CODE"
echo "tag=v$NEXT"
echo "bumped=$BUMPED"
