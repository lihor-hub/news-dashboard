#!/usr/bin/env bash
# Resolve runnable child manifests, ignoring BuildKit's unknown/unknown attestations.
set -euo pipefail

index_path=${1:?Usage: resolve-image-platforms.sh INDEX_JSON}
resolve() {
  jq -er --arg architecture "$1" '
    [.manifests[] | select(.platform.os == "linux" and .platform.architecture == $architecture)]
    | if length == 1 and (.[0].digest | test("^sha256:[a-f0-9]{64}$"))
      then .[0].digest
      else error("Expected exactly one valid linux/" + $architecture + " child digest")
      end
  ' "$index_path"
}
amd64_digest=$(resolve amd64)
arm64_digest=$(resolve arm64)
printf 'amd64_digest=%s\narm64_digest=%s\n' "$amd64_digest" "$arm64_digest"
