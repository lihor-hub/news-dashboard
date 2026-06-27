from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_deploy_creates_namespace_before_secrets() -> None:
    workflow = WORKFLOW.read_text()

    namespace_command = (
        "kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -"
    )
    pull_command = "kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret"
    ai_command = "kubectl -n news-dashboard create secret generic news-dashboard-ai"

    namespace_index = workflow.index(namespace_command)
    pull_index = workflow.index(pull_command)
    ai_index = workflow.index(ai_command)

    assert namespace_index < pull_index  # noqa: S101
    assert namespace_index < ai_index  # noqa: S101
