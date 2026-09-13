from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve-image-platforms.sh"


def descriptor(architecture: str, digest: str) -> dict[str, object]:
    return {"platform": {"os": "linux", "architecture": architecture}, "digest": digest}


def resolve(tmp_path: Path, manifests: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"manifests": manifests}))
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(SCRIPT), str(index)], capture_output=True, text=True, check=False
    )


def test_resolves_child_digests_without_confusing_attestation_manifests(tmp_path: Path) -> None:
    amd64 = "sha256:" + "a" * 64
    arm64 = "sha256:" + "b" * 64
    result = resolve(
        tmp_path,
        [
            descriptor("amd64", amd64),
            descriptor("arm64", arm64),
            descriptor("unknown", "sha256:" + "c" * 64),
        ],
    )
    assert result.returncode == 0  # noqa: S101
    assert result.stdout.splitlines() == [f"amd64_digest={amd64}", f"arm64_digest={arm64}"]  # noqa: S101


@pytest.mark.parametrize(
    "invalid",
    [
        [],
        [descriptor("amd64", "sha256:" + "a" * 64)],
        [descriptor("amd64", "invalid"), descriptor("arm64", "sha256:" + "b" * 64)],
        [
            descriptor("amd64", "sha256:" + "a" * 64),
            descriptor("amd64", "sha256:" + "c" * 64),
            descriptor("arm64", "sha256:" + "b" * 64),
        ],
    ],
)
def test_rejects_missing_duplicate_or_invalid_architecture_digests(
    tmp_path: Path, invalid: list[dict[str, object]]
) -> None:
    assert resolve(tmp_path, invalid).returncode != 0  # noqa: S101


def test_publish_covers_both_platforms_and_attests_each_sbom_to_its_child() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["publish"]["steps"]
    qemu = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("docker/setup-qemu-action@")
    )
    buildx = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("docker/setup-buildx-action@")
    )
    assert qemu < buildx  # noqa: S101
    build = next(step for step in steps if step.get("id") == "build")
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"  # noqa: S101
    for architecture in ("amd64", "arm64"):
        sbom = next(step for step in steps if step.get("name") == f"Generate {architecture} SBOM")
        attestation = next(
            step for step in steps if step.get("name") == f"Attest {architecture} SBOM"
        )
        digest = "${{ steps.platforms.outputs." + architecture + "_digest }}"
        assert sbom["with"]["image"].endswith("@" + digest)  # noqa: S101
        assert attestation["with"]["subject-digest"] == digest  # noqa: S101
        assert attestation["with"]["sbom-path"] == sbom["with"]["output-file"]  # noqa: S101
    provenance = next(step for step in steps if step.get("name") == "Attest build provenance")
    assert provenance["with"]["subject-digest"] == "${{ steps.build.outputs.digest }}"  # noqa: S101


def test_manual_validation_is_opt_in_and_cannot_publish() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    # PyYAML's YAML 1.1 loader interprets the GitHub Actions `on` key as True.
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["validate_multiarch_images"]["default"] is False  # noqa: S101
    job = workflow["jobs"]["validate-multiarch-images"]
    assert job["if"] == (  # noqa: S101
        "github.event_name == 'workflow_dispatch' && inputs.validate_multiarch_images"
    )
    assert job["permissions"] == {"contents": "read"}  # noqa: S101
    builds = [s for s in job["steps"] if s.get("uses", "").startswith("docker/build-push-action@")]
    assert len(builds) == 2  # noqa: S101
    fixture = next(
        s for s in job["steps"] if s.get("name") == "Verify a tiny dual-architecture OCI fixture"
    )
    assert "--tag news-dashboard-validation:fixture" in fixture["run"]  # noqa: S101
    for build in builds:
        assert build["with"]["push"] is False  # noqa: S101
        assert build["with"].get("tags", "").startswith("news-dashboard-validation:")  # noqa: S101
        assert build["with"]["no-cache"] is True  # noqa: S101
        assert build["with"]["sbom"] is True  # noqa: S101
        assert build["with"]["outputs"].startswith("type=oci,")  # noqa: S101
    assert "github.event_name == 'push'" in workflow["jobs"]["publish"]["if"]  # noqa: S101
    assert "publish" in workflow["jobs"]["deploy"]["needs"]  # noqa: S101
    assert "if" not in workflow["jobs"]["deploy"]  # noqa: S101


@pytest.mark.parametrize("fault", [None, "missing-arm64-sbom", "wrong-subject", "corrupt-index"])
def test_verifies_oci_attestations_against_each_child(tmp_path: Path, fault: str | None) -> None:
    import hashlib
    import io
    import tarfile

    archive_path = tmp_path / "image.tar"
    with tarfile.open(archive_path, "w") as archive:

        def add_blob(payload: dict[str, object], *, corrupt: bool = False) -> str:
            data = json.dumps(payload).encode()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            stored = b"{}" if corrupt else data
            member = tarfile.TarInfo("blobs/sha256/" + digest.removeprefix("sha256:"))
            member.size = len(stored)
            archive.addfile(member, io.BytesIO(stored))
            return digest

        manifests: list[dict[str, object]] = []
        for architecture in ("amd64", "arm64"):
            child = add_blob({"schemaVersion": 2, "architecture": architecture})
            manifests.append(descriptor(architecture, child))
            layers: list[dict[str, object]] = []
            for predicate in ("sbom", "provenance"):
                if (
                    fault == "missing-arm64-sbom"
                    and architecture == "arm64"
                    and predicate == "sbom"
                ):
                    continue
                predicate_type = (
                    "https://spdx.dev/Document"
                    if predicate == "sbom"
                    else "https://slsa.dev/provenance/v0.2"
                )
                subject = "0" * 64 if fault == "wrong-subject" else child.removeprefix("sha256:")
                layer = add_blob(
                    {
                        "subject": [{"digest": {"sha256": subject}}],
                        "predicateType": predicate_type,
                        "predicate": {"spdxVersion": "SPDX-2.3"},
                    }
                )
                layers.append(
                    {"digest": layer, "annotations": {"in-toto.io/predicate-type": predicate_type}}
                )
            attestation = descriptor("unknown", add_blob({"layers": layers}))
            attestation["annotations"] = {
                "vnd.docker.reference.type": "attestation-manifest",
                "vnd.docker.reference.digest": child,
            }
            manifests.append(attestation)
        index = add_blob({"manifests": manifests}, corrupt=fault == "corrupt-index")
    result = subprocess.run(  # noqa: S603
        [
            "/bin/bash",
            str(ROOT / "scripts/verify-oci-attestations.sh"),
            str(archive_path),
            index,
            str(tmp_path / "evidence"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is (fault is None), result.stderr  # noqa: S101
    if fault is None:
        assert (tmp_path / "evidence/arm64-sbom.json").is_file()  # noqa: S101
        assert (tmp_path / "evidence/amd64-provenance.json").is_file()  # noqa: S101
