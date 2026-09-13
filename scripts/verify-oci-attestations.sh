#!/usr/bin/env bash
# Verify local BuildKit OCI output; retain small, digest-checked evidence only.
set -euo pipefail
archive=${1:?Usage: verify-oci-attestations.sh ARCHIVE INDEX_DIGEST OUTPUT_DIR}
index_digest=${2:?Missing index digest}
output=${3:?Missing output directory}
mkdir -p "$output"

blob() {
  local digest=$1 destination=$2 actual
  [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || return 1
  tar -xOf "$archive" "blobs/sha256/${digest#sha256:}" > "$destination"
  actual=$(shasum -a 256 "$destination")
  [[ "${actual%% *}" == "${digest#sha256:}" ]]
}

blob "$index_digest" "$output/image-index.json"
bash "$(dirname "$0")/resolve-image-platforms.sh" "$output/image-index.json" > "$output/platforms.txt"
for architecture in amd64 arm64; do
  child=$(jq -er --arg arch "$architecture" '.manifests[] | select(.platform.os == "linux" and .platform.architecture == $arch) | .digest' "$output/image-index.json")
  blob "$child" "$output/$architecture-manifest.json"
  attestation=$(jq -er --arg child "$child" '
    [.manifests[] | select(.annotations["vnd.docker.reference.type"] == "attestation-manifest" and .annotations["vnd.docker.reference.digest"] == $child)]
    | if length == 1 then .[0].digest else error("Expected one attestation manifest for " + $child) end
  ' "$output/image-index.json")
  blob "$attestation" "$output/$architecture-attestation.json"
  for predicate in sbom provenance; do
    layer=$(jq -er --arg predicate "$predicate" '
      [.layers[] | select(
        if $predicate == "sbom" then .annotations["in-toto.io/predicate-type"] == "https://spdx.dev/Document"
        else (.annotations["in-toto.io/predicate-type"] // "" | startswith("https://slsa.dev/provenance/")) end)]
      | if length == 1 then .[0].digest else error("Expected one " + $predicate + " layer") end
    ' "$output/$architecture-attestation.json")
    blob "$layer" "$output/$architecture-$predicate.json"
    jq -e --arg child "${child#sha256:}" --arg predicate "$predicate" '
      any(.subject[]; .digest.sha256 == $child) and
      (if $predicate == "sbom" then .predicateType == "https://spdx.dev/Document" and (.predicate.spdxVersion | startswith("SPDX-"))
       else (.predicateType | startswith("https://slsa.dev/provenance/")) end)
    ' "$output/$architecture-$predicate.json" > /dev/null
  done
done
printf '%s\n' "$index_digest" > "$output/index-digest.txt"
