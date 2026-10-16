#!/usr/bin/env bash
# Rebuild the identified upstream native source patch, entirely offline.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root=$PWD
vendor=$repo_root/vendor/fastuuid
output=${1:-$vendor/fastuuid-0.14.0+nd.1.tar.gz}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
(
  cd "$vendor"
  echo '178947fc2f995b38497a74172adee64fdeb8b7ec18f2a5934d037641ba265d26  fastuuid-0.14.0.tar.gz' | shasum -a 256 -c -
)
# Extract only the hash-verified upstream release; patch never runs build code.
tar -xzf "$vendor/fastuuid-0.14.0.tar.gz" -C "$work"
(
  cd "$work/fastuuid-0.14.0"
  patch --batch --forward -p1 < "$vendor/python315.patch"
)
python3 - "$work/fastuuid-0.14.0" "$output" <<'PY'
import gzip
import io
import sys
import tarfile
from pathlib import Path

source, output = map(Path, sys.argv[1:])
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        info = tarfile.TarInfo("fastuuid-0.14.0+nd.1/" + path.relative_to(source).as_posix())
        content = path.read_bytes()
        info.size = len(content)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(content))
output.write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
PY
