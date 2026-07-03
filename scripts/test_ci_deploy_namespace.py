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


def test_deploy_supports_public_ghcr_without_token() -> None:
    workflow = WORKFLOW.read_text()
    public_image_message = (
        'echo "GHCR_TOKEN is empty; treating ${IMG}:${SHA} as a public GHCR image."'
    )
    empty_image_pull_arg = "pull_secret_helm_args=(--set-string image.pullSecretName=)"

    assert 'if [ -n "$GHCR_TOKEN" ]; then' in workflow  # noqa: S101
    assert public_image_message in workflow  # noqa: S101
    assert empty_image_pull_arg in workflow  # noqa: S101
    assert '"${pull_secret_helm_args[@]}"' in workflow  # noqa: S101


def test_deploy_keeps_private_ghcr_pull_secret_when_token_is_set() -> None:
    workflow = WORKFLOW.read_text()

    token_branch_index = workflow.index('if [ -n "$GHCR_TOKEN" ]; then')
    docker_login_index = workflow.index(
        'echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_ACTOR" --password-stdin'
    )
    secret_index = workflow.index(
        "kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret"
    )
    helm_arg_index = workflow.index(
        "pull_secret_helm_args=(--set-string image.pullSecretName=ghcr-pull-secret)"
    )
    no_token_index = workflow.index("else", token_branch_index)

    assert token_branch_index < docker_login_index < no_token_index  # noqa: S101
    assert token_branch_index < secret_index < no_token_index  # noqa: S101
    assert token_branch_index < helm_arg_index < no_token_index  # noqa: S101
