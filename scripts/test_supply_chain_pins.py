from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"
HELM_VALUES = ROOT / "helm" / "news-dashboard" / "values.yaml"
CI_BUILT_APP_IMAGE = "ghcr.io/lihor-hub/news-dashboard:7d01027c3c2b21a537ab3264ce485d4fea6ba48d"

ACTION_REF = re.compile(
    r"^\s*(?:-\s+)?uses:\s+[^\s#]+@(?P<sha>[0-9a-f]{40})\s+#\s+(?P<version>v[^\s]+)\s*$"
)
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s+(?P<reference>[^\s#]+)(?:\s+#.*)?$")
IMAGE_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
FROM_LINE = re.compile(r"^FROM\s+(?P<image>[^\s]+)(?:\s+AS\s+\w+)?$", re.MULTILINE)
IMAGE_LINE = re.compile(r"^\s*image:\s*(?P<image>[^\s#]+)", re.MULTILINE)


def assert_no_floating_action_refs(workflow: Path) -> None:
    for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
        match = USES_LINE.match(line)
        if match is None:
            continue

        reference = match["reference"]
        if reference.startswith("./"):
            continue

        if ACTION_REF.match(line) is None:
            msg = (
                f"{workflow.relative_to(ROOT)}:{line_number} must use a full SHA "
                "and # v<version> comment"
            )
            raise AssertionError(msg)


def assert_immutable_image(image: str, source: Path) -> None:
    # The deploy job gets github.sha, but publish does not expose its digest as
    # a job output. This is deliberately the only non-digest production image.
    if image == CI_BUILT_APP_IMAGE:
        return

    if IMAGE_DIGEST.fullmatch(image) is None:
        msg = f"{source.relative_to(ROOT)} has mutable production image reference: {image}"
        raise AssertionError(msg)


def test_third_party_actions_are_pinned_to_full_commit_shas() -> None:
    for workflow in WORKFLOWS:
        assert_no_floating_action_refs(workflow)


def test_production_container_references_are_immutable() -> None:
    for match in FROM_LINE.finditer(DOCKERFILE.read_text()):
        assert_immutable_image(match["image"], DOCKERFILE)

    for match in IMAGE_LINE.finditer(COMPOSE_PROD.read_text()):
        assert_immutable_image(match["image"], COMPOSE_PROD)

    helm_values = HELM_VALUES.read_text()
    app_image = re.search(
        r"^image:\n\s+repository:\s*(?P<repository>\S+)\n(?:.*\n)*?\s+tag:\s*(?P<tag>\S+)",
        helm_values,
        re.MULTILINE,
    )
    if app_image is None:
        msg = "Helm values must define the production application image"
        raise AssertionError(msg)
    assert_immutable_image(f"{app_image['repository']}:{app_image['tag']}", HELM_VALUES)

    postgres_image = re.search(
        r"^\s*image:\s*(?P<image>pgvector/[^\s#]+)",
        helm_values,
        re.MULTILINE,
    )
    if postgres_image is None:
        msg = "Helm values must define the PostgreSQL image"
        raise AssertionError(msg)
    assert_immutable_image(postgres_image["image"], HELM_VALUES)

    neo4j = re.search(
        r"^neo4j:\n(?:.*\n)*?^\s+repository:\s*(?P<repository>\S+)\n\s+tag:\s*(?P<tag>\S+)",
        helm_values,
        re.MULTILINE,
    )
    if neo4j is None:
        msg = "Helm values must define the Neo4j image"
        raise AssertionError(msg)
    assert_immutable_image(f"{neo4j['repository']}:{neo4j['tag']}", HELM_VALUES)

    for workflow in (
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "nightly.yml",
        ROOT / ".github" / "workflows" / "pr-timing.yml",
    ):
        for match in IMAGE_LINE.finditer(workflow.read_text()):
            image = match["image"]
            if image.startswith("pgvector/"):
                assert_immutable_image(image, workflow)
