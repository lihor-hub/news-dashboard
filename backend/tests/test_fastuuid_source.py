"""Check the provenance and supported build configuration of the native patch."""

import hashlib
import io
import subprocess
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor" / "fastuuid"
UPSTREAM_SHA256 = "178947fc2f995b38497a74172adee64fdeb8b7ec18f2a5934d037641ba265d26"


def _files(path: Path) -> dict[str, bytes]:
    with tarfile.open(path) as archive:
        return {
            str(Path(member.name).relative_to(Path(member.name).parts[0])): stream.read()
            for member in archive.getmembers()
            if member.isfile() and (stream := archive.extractfile(member)) is not None
        }


def test_supported_native_build_preserves_uuid_implementation() -> None:
    original = VENDOR / "fastuuid-0.14.0.tar.gz"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == UPSTREAM_SHA256
    upstream = _files(original)
    patched = _files(VENDOR / "fastuuid-0.14.0+nd.1.tar.gz")
    cargo = tomllib.loads(patched["Cargo.toml"].decode())
    build = tomllib.loads(patched["pyproject.toml"].decode())
    assert cargo["dependencies"]["pyo3"]["version"] == "=0.30.1"
    assert cargo["package"]["version"] == "0.14.0+nd.1"
    assert build["tool"]["maturin"]["locked"] is True
    assert build["build-system"]["requires"] == ["maturin==1.15.0"]
    assert upstream.keys() == patched.keys()
    changed = {name for name in upstream if upstream[name] != patched[name]}
    assert changed == {"Cargo.toml", "Cargo.lock", "src/lib.rs", "pyproject.toml", "PKG-INFO"}
    expected = (
        upstream["src/lib.rs"]
        .replace(b".downcast::<PyInt>()", b".cast::<PyInt>()")
        .replace(
            b"pyclass(subclass, freelist = 1000)",
            b"pyclass(subclass, freelist = 1000, from_py_object)",
        )
    )
    assert patched["src/lib.rs"] == expected
    # Preserve the OS-backed randomness path and exact uuid/rand versions.
    old_lock = tomllib.loads(upstream["Cargo.lock"].decode())
    new_lock = tomllib.loads(patched["Cargo.lock"].decode())
    for name in ("uuid", "rand", "getrandom"):
        assert [p for p in old_lock["package"] if p["name"] == name] == [
            p for p in new_lock["package"] if p["name"] == name
        ]


def test_source_archive_rebuilds_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "rebuilt.tar.gz"
    subprocess.run(  # noqa: S603 - repository-owned script and test-owned output
        ["/bin/bash", str(ROOT / "scripts" / "rebuild_fastuuid.sh"), str(output)],
        check=True,
        cwd=ROOT,
    )
    assert output.read_bytes() == (VENDOR / "fastuuid-0.14.0+nd.1.tar.gz").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(output.read_bytes())) as archive:
        assert all(member.isfile() or member.isdir() for member in archive.getmembers())
