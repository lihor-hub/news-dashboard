from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRECTORY = ROOT / ".github" / "workflows"
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"
HELM_CHART = ROOT / "helm" / "news-dashboard"
HELM_PRODUCTION_VALUES = HELM_CHART / "values-production.yaml"
CI_BUILT_APP_IMAGE = "ghcr.io/lihor-hub/news-dashboard:7d01027c3c2b21a537ab3264ce485d4fea6ba48d"
IMAGE_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")

# Each entry is a reviewed exact action identity and its executable commit.
# Updating or adding an action therefore requires an explicit mapping change.
APPROVED_ACTION_COMMITS = {
    "actions/attest-build-provenance": "0f67c3f4856b2e3261c31976d6725780e5e4c373",
    "actions/attest-sbom": "c604332985a26aa8cf1bdc465b92731239ec6b9e",
    "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/configure-pages": "45bfe0192ca1faeb007ade9deae92b16b8254a0d",
    "actions/dependency-review-action": "a1d282b36b6f3519aa1f3fc636f609c47dddb294",
    "actions/deploy-pages": "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/github-script": "3a2844b7e9c422d3c10d287c895573f7108da1b3",
    "actions/labeler": "8558fd74291d67161a8a78ce36a881fa63b766a9",
    "actions/setup-java": "03ad4de0992f5dab5e18fcb136590ce7c4a0ac95",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/upload-pages-artifact": "fc324d3547104276b827a68afc52ff2a11cc49c9",
    "anchore/sbom-action": "e22c389904149dbc22b58101806040fa8d37a610",
    "android-actions/setup-android": "40fd30fb8d7440372e1316f5d1809ec01dcd3699",
    "aquasecurity/trivy-action": "ed142fd0673e97e23eac54620cfb913e5ce36c25",
    "azure/setup-helm": "9bc31f4ebc9c6b171d7bfbaa5d006ae7abdb4310",
    "codecov/codecov-action": "0fb7174895f61a3b6b78fc075e0cd60383518dac",
    "docker/build-push-action": "53b7df96c91f9c12dcc8a07bcb9ccacbed38856a",
    "docker/login-action": "dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action": "bb05f3f5519dd87d3ba754cc423b652a5edd6d2c",
    "dorny/paths-filter": "7b450fff21473bca461d4b92ce414b9d0420d706",
    "github/codeql-action/analyze": "f205ea1c3313d32999d8d6a48b4f6530d4437b38",
    "github/codeql-action/autobuild": "f205ea1c3313d32999d8d6a48b4f6530d4437b38",
    "github/codeql-action/init": "f205ea1c3313d32999d8d6a48b4f6530d4437b38",
    "github/codeql-action/upload-sarif": "f205ea1c3313d32999d8d6a48b4f6530d4437b38",
}


def discover_workflows(directory: Path) -> list[Path]:
    return sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))


WORKFLOWS = discover_workflows(WORKFLOW_DIRECTORY)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def find_uses(node: object) -> Iterator[str]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "uses":
                if not isinstance(value, str):
                    msg = f"`uses` must be a string, got {type(value).__name__}"
                    raise AssertionError(msg)
                yield value
            yield from find_uses(value)
    elif isinstance(node, list):
        for value in node:
            yield from find_uses(value)


def count_version_comments(workflow_text: str, reference: str) -> int:
    pattern = re.compile(rf"{re.escape(reference)}[^\n#]*#\s+v\d+[^\s,\]}}]*")
    return len(pattern.findall(workflow_text))


def assert_no_floating_action_refs(workflow: Path) -> None:
    workflow_text = workflow.read_text()
    document = yaml.safe_load(workflow_text)
    external_actions: list[str] = []
    for reference in find_uses(document):
        if reference.startswith("./"):
            continue
        if reference.startswith("docker://"):
            assert_immutable_image(reference.removeprefix("docker://"), workflow)
            continue

        action, separator, commit = reference.rpartition("@")
        approved_commit = APPROVED_ACTION_COMMITS.get(action)
        if not separator or approved_commit is None or commit != approved_commit:
            msg = (
                f"{display_path(workflow)} action {reference!r} must use the explicitly "
                f"approved commit for action identity {action!r}"
            )
            raise AssertionError(msg)
        external_actions.append(reference)

    for reference, expected_count in Counter(external_actions).items():
        comment_count = count_version_comments(workflow_text, reference)
        if comment_count != expected_count:
            msg = (
                f"{display_path(workflow)} action {reference!r} needs {expected_count} "
                f"version comments, found {comment_count}"
            )
            raise AssertionError(msg)


def assert_immutable_image(image: str, source: Path) -> None:
    # The deploy job gets github.sha, but publish does not expose its digest as
    # a job output. This is deliberately the only non-digest production image.
    if image == CI_BUILT_APP_IMAGE:
        return

    if IMAGE_DIGEST.fullmatch(image) is None:
        msg = f"{display_path(source)} has mutable production image reference: {image}"
        raise AssertionError(msg)


def extract_dockerfile_images(dockerfile: str) -> list[str]:
    logical_lines = dockerfile.replace("\\\r\n", "").replace("\\\n", "")
    images: list[str] = []
    for line in logical_lines.splitlines():
        tokens = shlex.split(line, comments=True)
        if not tokens or tokens[0].upper() != "FROM":
            continue

        image_index = 1
        while image_index < len(tokens) and tokens[image_index].startswith("--"):
            image_index += 1
        if image_index >= len(tokens):
            msg = f"Dockerfile FROM instruction has no image: {line}"
            raise AssertionError(msg)
        images.append(tokens[image_index])
    return images


def extract_compose_images(compose: Path) -> list[str]:
    document = yaml.safe_load(compose.read_text())
    if not isinstance(document, Mapping) or not isinstance(document.get("services"), Mapping):
        msg = f"{display_path(compose)} must define a services mapping"
        raise TypeError(msg)

    images: list[str] = []
    for service_name, service in document["services"].items():
        if not isinstance(service, Mapping) or not isinstance(service.get("image"), str):
            msg = f"{display_path(compose)} service {service_name!r} must define an image"
            raise TypeError(msg)
        images.append(service["image"])
    return images


def workload_pod_spec(document: Mapping[str, Any]) -> Mapping[str, Any] | None:
    kind = document.get("kind")
    spec = document.get("spec")
    if not isinstance(spec, Mapping):
        return None
    if kind in {"DaemonSet", "Deployment", "Job", "ReplicaSet", "StatefulSet"}:
        template = spec.get("template")
    elif kind == "CronJob":
        job_template = spec.get("jobTemplate")
        job_spec = job_template.get("spec") if isinstance(job_template, Mapping) else None
        template = job_spec.get("template") if isinstance(job_spec, Mapping) else None
    elif kind == "Pod":
        return spec
    else:
        return None
    pod_spec = template.get("spec") if isinstance(template, Mapping) else None
    return pod_spec if isinstance(pod_spec, Mapping) else None


def extract_rendered_workload_images(rendered: str) -> list[str]:
    images: list[str] = []
    for document in yaml.safe_load_all(rendered):
        if not isinstance(document, Mapping):
            continue
        pod_spec = workload_pod_spec(document)
        if pod_spec is None:
            continue
        for container_type in ("initContainers", "containers"):
            containers = pod_spec.get(container_type, [])
            if not isinstance(containers, list):
                msg = f"{document.get('kind')} {container_type} must be a list"
                raise TypeError(msg)
            for container in containers:
                image = container.get("image") if isinstance(container, Mapping) else None
                if not isinstance(image, str):
                    msg = f"{document.get('kind')} container must define an image"
                    raise TypeError(msg)
                images.append(image)
    return images


def render_helm_chart(values_file: Path | None = None) -> str:
    helm = shutil.which("helm")
    if helm is None:
        msg = "helm is required to validate rendered production workload images"
        raise AssertionError(msg)
    command = [
        helm,
        "template",
        "news-dashboard",
        str(HELM_CHART),
    ]
    if values_file is not None:
        command.extend(["--values", str(values_file)])
    command.extend(
        [
            "--set-string",
            "app.auth.sessionSecret=pin-test-session-secret",
            "--set-string",
            "postgresql.password=pin-test-postgres-password",
            "--set",
            "neo4j.enabled=true",
            "--set-string",
            "neo4j.auth.password=pin-test-neo4j-password",
        ]
    )
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout


def assert_helm_renderings_are_immutable(renderings: Mapping[Path, str]) -> None:
    for source, rendered in renderings.items():
        images = extract_rendered_workload_images(rendered)
        if not images:
            msg = f"{display_path(source)} must render at least one workload image"
            raise AssertionError(msg)
        for image in images:
            assert_immutable_image(image, source)


def extract_workflow_service_images(workflow: Path) -> list[str]:
    document = yaml.safe_load(workflow.read_text())
    jobs = document.get("jobs") if isinstance(document, Mapping) else None
    if not isinstance(jobs, Mapping):
        return []
    images: list[str] = []
    for job in jobs.values():
        services = job.get("services") if isinstance(job, Mapping) else None
        if not isinstance(services, Mapping):
            continue
        for service in services.values():
            image = service.get("image") if isinstance(service, Mapping) else None
            if not isinstance(image, str):
                msg = f"{display_path(workflow)} service must define an image"
                raise TypeError(msg)
            images.append(image)
    return images


def test_third_party_actions_are_pinned_to_full_commit_shas() -> None:
    for workflow in WORKFLOWS:
        assert_no_floating_action_refs(workflow)


def test_production_container_references_are_immutable() -> None:
    dockerfile_images = extract_dockerfile_images(DOCKERFILE.read_text())
    if not dockerfile_images:
        msg = "Dockerfile must contain at least one FROM instruction"
        raise AssertionError(msg)
    for image in dockerfile_images:
        assert_immutable_image(image, DOCKERFILE)

    for image in extract_compose_images(COMPOSE_PROD):
        assert_immutable_image(image, COMPOSE_PROD)

    assert_helm_renderings_are_immutable(
        {
            HELM_CHART / "values.yaml": render_helm_chart(),
            HELM_PRODUCTION_VALUES: render_helm_chart(HELM_PRODUCTION_VALUES),
        }
    )

    for workflow in WORKFLOWS:
        for image in extract_workflow_service_images(workflow):
            assert_immutable_image(image, workflow)


def test_workflow_discovery_includes_yaml_extension(tmp_path: Path) -> None:
    (tmp_path / "first.yml").write_text("jobs: {}\n")
    yaml_workflow = tmp_path / "second.yaml"
    yaml_workflow.write_text("jobs: {}\n")

    if yaml_workflow not in discover_workflows(tmp_path):
        pytest.fail("Workflow discovery skipped the .yaml extension")


def test_flow_style_action_reference_cannot_bypass_validation(tmp_path: Path) -> None:
    workflow = tmp_path / "flow.yaml"
    workflow.write_text("jobs: {check: {steps: [{uses: actions/checkout@v7}]}}\n")

    with pytest.raises(AssertionError, match="approved commit"):
        assert_no_floating_action_refs(workflow)


def test_wrong_full_action_sha_is_rejected(tmp_path: Path) -> None:
    workflow = tmp_path / "wrong-sha.yml"
    workflow.write_text(
        "jobs:\n"
        "  check:\n"
        "    steps:\n"
        "      - uses: actions/checkout@0000000000000000000000000000000000000000 # v7\n"
    )

    with pytest.raises(AssertionError, match="approved commit"):
        assert_no_floating_action_refs(workflow)


def test_only_approved_sub_action_identities_are_allowed(tmp_path: Path) -> None:
    codeql_commit = APPROVED_ACTION_COMMITS["github/codeql-action/init"]
    approved_workflow = tmp_path / "approved-sub-actions.yml"
    approved_workflow.write_text(
        "jobs:\n"
        "  check:\n"
        "    steps:\n"
        f"      - uses: github/codeql-action/init@{codeql_commit} # v4\n"
        f"      - uses: github/codeql-action/analyze@{codeql_commit} # v4\n"
    )
    assert_no_floating_action_refs(approved_workflow)

    unapproved_workflow = tmp_path / "unapproved-sub-action.yml"
    unapproved_workflow.write_text(
        "jobs:\n"
        "  check:\n"
        "    steps:\n"
        f"      - uses: github/codeql-action/not-approved@{codeql_commit} # v4\n"
    )
    with pytest.raises(AssertionError, match="approved commit"):
        assert_no_floating_action_refs(unapproved_workflow)


def test_each_action_occurrence_needs_a_version_comment(tmp_path: Path) -> None:
    checkout = APPROVED_ACTION_COMMITS["actions/checkout"]
    workflow = tmp_path / "missing-comment.yml"
    workflow.write_text(
        "jobs:\n"
        "  check:\n"
        "    steps:\n"
        f"      - uses: actions/checkout@{checkout} # v7\n"
        f"      - uses: actions/checkout@{checkout}\n"
    )

    with pytest.raises(AssertionError, match="2 version comments"):
        assert_no_floating_action_refs(workflow)


def test_digest_pinned_docker_action_is_allowed(tmp_path: Path) -> None:
    workflow = tmp_path / "docker-action.yml"
    workflow.write_text(
        "jobs:\n"
        "  check:\n"
        "    steps:\n"
        "      - uses: docker://alpine:3.22@sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    )

    assert_no_floating_action_refs(workflow)


def test_dockerfile_from_parser_handles_options_and_aliases() -> None:
    dockerfile = (
        "FROM --platform=$BUILDPLATFORM "
        "node:26-bookworm-slim@sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa AS build\n"
        "FROM python:3.14-slim@sha256:"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb runtime\n"
    )

    expected = [
        (
            "node:26-bookworm-slim@sha256:"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        (
            "python:3.14-slim@sha256:"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
    ]
    if extract_dockerfile_images(dockerfile) != expected:
        pytest.fail("Dockerfile parser did not handle FROM options and aliases")


def test_compose_images_are_read_from_service_structure(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n"
        "  database: {image: 'postgres:16@sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}\n"
    )

    expected = [
        ("postgres:16@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    ]
    if extract_compose_images(compose) != expected:
        pytest.fail("Compose parser did not read the service image")


def test_rendered_workload_parser_finds_all_container_kinds() -> None:
    rendered = """
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      initContainers:
        - image: init:1@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      containers:
        - image: app:1@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
---
apiVersion: batch/v1
kind: CronJob
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - image: job:1@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
"""

    expected = [
        "init:1@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "app:1@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "job:1@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    ]
    if extract_rendered_workload_images(rendered) != expected:
        pytest.fail("Rendered workload parser missed container images")


def test_production_only_mutable_helm_image_is_rejected() -> None:
    default_render = """
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - image: app:1@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
    production_render = """
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - image: app:latest
"""

    with pytest.raises(AssertionError, match=r"production-overlay.*mutable"):
        assert_helm_renderings_are_immutable(
            {
                Path("default-values"): default_render,
                Path("production-overlay"): production_render,
            }
        )
