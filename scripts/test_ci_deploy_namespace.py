from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_HELPER = ROOT / "scripts" / "deploy-local-k8s.sh"
DEPLOY_LIBRARY = ROOT / "scripts" / "production-deploy-lib.sh"
PRODUCTION_VALUES = ROOT / "helm" / "news-dashboard" / "values-production.yaml"
CHART = ROOT / "helm" / "news-dashboard"
PRODUCTION_DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "SELF_HOSTING.md",
    ROOT / "website" / "docs" / "architecture" / "product-spec.md",
    ROOT / "website" / "docs" / "configuration" / "https-caddy.md",
    ROOT / "website" / "docs" / "self-hosting" / "index.md",
)


def run_cutover_gate(value: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if value is None:
        env.pop("INGRESS_CUTOVER_ENABLED", None)
    else:
        env["INGRESS_CUTOVER_ENABLED"] = value
    command = f"source {shlex.quote(str(DEPLOY_LIBRARY))}; production_cutover_enabled"
    return subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_deploy_creates_namespace_before_secrets() -> None:
    workflow = CI_WORKFLOW.read_text()

    namespace_command = (
        "kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -"
    )
    pull_command = "kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret"
    ai_command = "kubectl -n news-dashboard create secret generic news-dashboard-ai"

    namespace_index = workflow.index(namespace_command)
    pull_index = workflow.index(pull_command)
    ai_index = workflow.index(ai_command)
    gate_index = workflow.index("if ! production_cutover_enabled; then")
    docker_pull_index = workflow.index('docker pull "${IMG}@${IMAGE_DIGEST}"')

    assert gate_index < docker_pull_index  # noqa: S101
    assert namespace_index < pull_index  # noqa: S101
    assert namespace_index < ai_index  # noqa: S101
    assert gate_index < namespace_index  # noqa: S101


def test_deploy_supports_public_ghcr_without_token() -> None:
    workflow = CI_WORKFLOW.read_text()
    public_image_message = (
        'echo "GHCR_TOKEN is empty; treating ${IMG}@${IMAGE_DIGEST} as a public GHCR image."'
    )
    empty_image_pull_arg = "pull_secret_helm_args=(--set-string image.pullSecretName=)"

    assert 'if [ -n "$GHCR_TOKEN" ]; then' in workflow  # noqa: S101
    assert public_image_message in workflow  # noqa: S101
    assert empty_image_pull_arg in workflow  # noqa: S101
    assert '"${pull_secret_helm_args[@]}"' in workflow  # noqa: S101


def test_deploy_keeps_private_ghcr_pull_secret_when_token_is_set() -> None:
    workflow = CI_WORKFLOW.read_text()

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


def test_production_deploy_uses_cluster_ip_and_ingress() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    for source in (workflow, helper):
        assert "service.type=NodePort" not in source  # noqa: S101
        assert "service.nodePort=30088" not in source  # noqa: S101
        assert "values-production.yaml" in source  # noqa: S101


def test_publish_exposes_and_deploys_the_exact_application_digest() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    publish = workflow["jobs"]["publish"]
    deploy = workflow["jobs"]["deploy"]
    deploy_step = next(step for step in deploy["steps"] if step["name"] == "Deploy (Helm)")

    assert publish["outputs"]["image_digest"] == "${{ steps.build.outputs.digest }}"  # noqa: S101
    assert deploy_step["env"]["IMAGE_DIGEST"] == (  # noqa: S101
        "${{ needs.publish.outputs.image_digest }}"
    )
    script = deploy_step["run"]
    assert 'docker pull "${IMG}@${IMAGE_DIGEST}"' in script  # noqa: S101
    assert '--set-string "image.digest=${IMAGE_DIGEST}"' in script  # noqa: S101
    assert "--set image.tag=" not in script  # noqa: S101


def test_manual_production_helper_requires_and_deploys_image_digest() -> None:
    helper = DEPLOY_HELPER.read_text()

    assert 'if [[ -z "${IMAGE_DIGEST:-}" ]]; then' in helper  # noqa: S101
    assert "IMAGE_DIGEST must be sha256:" in helper  # noqa: S101
    assert '--set-string "image.digest=${IMAGE_DIGEST}"' in helper  # noqa: S101
    assert "--set image.tag=" not in helper  # noqa: S101


def test_deploy_supports_persistent_non_secret_additional_egress_values() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    deploy_step = next(
        step for step in workflow["jobs"]["deploy"]["steps"] if step["name"] == "Deploy (Helm)"
    )
    script = deploy_step["run"]
    helper = DEPLOY_HELPER.read_text()

    assert deploy_step["env"]["ADDITIONAL_EGRESS_VALUES"] == (  # noqa: S101
        "${{ vars.ADDITIONAL_EGRESS_VALUES }}"
    )
    assert "additional-egress-values.yaml" in script  # noqa: S101
    assert '"${additional_egress_helm_args[@]}"' in script  # noqa: S101
    assert "ADDITIONAL_EGRESS_VALUES_FILE" in helper  # noqa: S101
    assert '"${ADDITIONAL_EGRESS_HELM_ARGS[@]}"' in helper  # noqa: S101


def test_public_smoke_check_uses_https_hostname() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert "http://localhost:30088" not in workflow  # noqa: S101
    assert "https://news.lihor.ro/api/health" in workflow  # noqa: S101
    assert "https://news.lihor.ro/api/health" in helper  # noqa: S101


def test_public_smoke_runs_only_after_the_deploy_step_reports_an_apply() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    steps = workflow["jobs"]["deploy"]["steps"]
    deploy_step = next(step for step in steps if step["name"] == "Deploy (Helm)")
    smoke_step = next(step for step in steps if step["name"] == "Smoke test public TLS Ingress")

    assert deploy_step["id"] == "deploy"  # noqa: S101
    assert smoke_step["if"] == "steps.deploy.outputs.applied == 'true'"  # noqa: S101

    script = deploy_step["run"]
    default_index = script.index('echo "applied=false" >> "$GITHUB_OUTPUT"')
    gate_index = script.index("if ! production_cutover_enabled; then")
    helm_index = script.index('helm "${helm_args[@]}"')
    applied_index = script.index('echo "applied=true" >> "$GITHUB_OUTPUT"')
    assert default_index < gate_index < helm_index < applied_index  # noqa: S101


def test_production_deploy_does_not_inherit_host_inventory() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert "192.168." not in workflow  # noqa: S101
    assert "ioachim-minipc" not in helper  # noqa: S101
    assert (  # noqa: S101
        "postgres_helm_args=(--set-string postgresql.persistence.hostPath=)" in workflow
    )
    assert (  # noqa: S101
        'POSTGRES_HELM_ARGS=(--set-string "postgresql.persistence.hostPath=")' in helper
    )


def test_mini_pc_deploy_requires_runtime_storage_path() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert 'if [ -z "$POSTGRES_HOST_PATH" ]; then' in workflow  # noqa: S101
    assert 'if [[ -z "${POSTGRES_HOST_PATH:-}" ]]; then' in helper  # noqa: S101


def test_cutover_gate_requires_exact_explicit_activation() -> None:
    assert run_cutover_gate(None).returncode != 0  # noqa: S101
    assert run_cutover_gate("").returncode != 0  # noqa: S101
    assert run_cutover_gate("false").returncode != 0  # noqa: S101
    assert run_cutover_gate("TRUE").returncode != 0  # noqa: S101
    assert run_cutover_gate("true").returncode == 0  # noqa: S101


def test_file_based_helm_secrets_preserve_hostile_values_without_argv_exposure() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()
    for source in (workflow, helper):
        assert "--set-string app.auth.sessionSecret=" not in source  # noqa: S101
        assert "--set-string postgresql.password=" not in source  # noqa: S101
        assert "PRODUCTION_HELM_SECRET_ARGS" in source  # noqa: S101

    session_value = "session,with{braces}\\slashes\nand-newline"
    postgres_value = "postgres,with{braces}\\slashes\nand-newline"
    env = os.environ.copy()
    env.update(
        {
            "SESSION_SECRET": session_value,
            "POSTGRES_PASSWORD": postgres_value,
        }
    )
    script = f"""
set -euo pipefail
source {shlex.quote(str(DEPLOY_LIBRARY))}
prepare_production_helm_secret_files
for argument in "${{PRODUCTION_HELM_SECRET_ARGS[@]}}"; do
  [[ "$argument" != *"$SESSION_SECRET"* ]]
  [[ "$argument" != *"$POSTGRES_PASSWORD"* ]]
done
helm template secret-test {shlex.quote(str(CHART))} \
  --values {shlex.quote(str(PRODUCTION_VALUES))} \
  --set-string image.digest=sha256:{"a" * 64} \
  --set-string postgresql.persistence.hostPath= \
  "${{PRODUCTION_HELM_SECRET_ARGS[@]}}"
"""
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    rendered = [document for document in yaml.safe_load_all(result.stdout) if document]
    secrets = {
        resource["metadata"]["name"]: resource["stringData"]
        for resource in rendered
        if resource["kind"] == "Secret"
    }
    assert secrets["secret-test-news-dashboard-auth"]["SESSION_SECRET"] == session_value  # noqa: S101
    assert (  # noqa: S101
        secrets["secret-test-news-dashboard-postgres"]["POSTGRES_PASSWORD"] == postgres_value
    )


def test_repeated_secret_preparation_removes_the_previous_directory() -> None:
    env = os.environ.copy()
    env.update(
        {
            "SESSION_SECRET": "session-secret",
            "POSTGRES_PASSWORD": "postgres-password",
        }
    )
    script = f"""
set -euo pipefail
source {shlex.quote(str(DEPLOY_LIBRARY))}
prepare_production_helm_secret_files
first_dir="$PRODUCTION_HELM_SECRET_DIR"
prepare_production_helm_secret_files
[[ ! -e "$first_dir" ]]
second_dir="$PRODUCTION_HELM_SECRET_DIR"
cleanup_production_helm_secret_files
[[ ! -e "$second_dir" ]]
"""
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101


def test_direct_production_helm_examples_choose_storage_and_secret_files() -> None:
    for document in PRODUCTION_DOCS:
        blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", document.read_text(), re.DOTALL)
        production_commands = [
            block
            for block in blocks
            if "helm upgrade" in block and "values-production.yaml" in block
        ]
        for command in production_commands:
            assert command.strip().startswith("(")  # noqa: S101
            assert command.strip().endswith(")")  # noqa: S101
            assert "postgresql.persistence.hostPath" in command  # noqa: S101
            assert "--set-file app.auth.sessionSecret=" in command  # noqa: S101
            assert "--set-file postgresql.password=" in command  # noqa: S101
            assert 'IMAGE_DIGEST="${IMAGE_DIGEST:?' in command  # noqa: S101
            assert '--set-string image.digest="${IMAGE_DIGEST}"' in command  # noqa: S101
            assert "--namespace news-dashboard --create-namespace" in command  # noqa: S101
            assert "--set-string app.auth.sessionSecret=" not in command  # noqa: S101
            assert "--set-string postgresql.password=" not in command  # noqa: S101


def test_documented_secret_file_commands_cleanup_at_the_end_of_a_subshell() -> None:
    for document in PRODUCTION_DOCS:
        blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", document.read_text(), re.DOTALL)
        secret_commands = [
            block
            for block in blocks
            if "prepare_production_helm_secret_files" in block and "helm upgrade" in block
        ]
        assert secret_commands, document  # noqa: S101
        for command in secret_commands:
            assert command.strip().startswith("(\nset -euo pipefail")  # noqa: S101
            assert command.strip().endswith(")")  # noqa: S101


def test_documented_operational_subshells_enable_strict_mode_first() -> None:
    for document in PRODUCTION_DOCS:
        blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", document.read_text(), re.DOTALL)
        operational_subshells = [
            block
            for block in blocks
            if block.strip().startswith("(")
            and any(
                operation in block
                for operation in (
                    "prepare_production_helm_secret_files",
                    "helm ",
                    "kubectl ",
                )
            )
        ]
        for command in operational_subshells:
            lines = [line.strip() for line in command.strip().splitlines()]
            assert lines[:2] == ["(", "set -euo pipefail"]  # noqa: S101


def test_strict_operational_subshell_propagates_helm_failure_and_cleans_secrets() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp_dir = Path(directory)
        fake_bin = temp_dir / "bin"
        fake_bin.mkdir()
        fake_helm = fake_bin / "helm"
        fake_helm.write_text("#!/usr/bin/env bash\nexit 42\n")
        fake_helm.chmod(0o755)
        tracked_dir_file = temp_dir / "tracked-dir"
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}:{env['PATH']}",
                "SESSION_SECRET": "session-secret",
                "POSTGRES_PASSWORD": "postgres-password",
                "TRACKED_DIR_FILE": str(tracked_dir_file),
            }
        )
        command = f"""
(
set -euo pipefail
source {shlex.quote(str(DEPLOY_LIBRARY))}
prepare_production_helm_secret_files
printf %s "$PRODUCTION_HELM_SECRET_DIR" >"$TRACKED_DIR_FILE"
helm upgrade representative-failure
:
)
"""
        result = subprocess.run(  # noqa: S603
            ["/bin/bash", "-c", command],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 42  # noqa: S101
        tracked_dir = Path(tracked_dir_file.read_text())
        assert not tracked_dir.exists()  # noqa: S101


def test_local_render_mode_does_not_require_cutover_activation() -> None:
    env = os.environ.copy()
    env.pop("INGRESS_CUTOVER_ENABLED", None)
    result = subprocess.run(  # noqa: S603
        [str(DEPLOY_HELPER), "--render"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    rendered = [document for document in yaml.safe_load_all(result.stdout) if document]
    app_service = next(
        resource
        for resource in rendered
        if resource["kind"] == "Service"
        and resource["metadata"]["name"] == "news-dashboard-news-dashboard"
    )
    assert app_service["spec"]["type"] == "ClusterIP"  # noqa: S101


def test_local_live_deploy_rejects_inactive_cutover_before_external_commands() -> None:
    for value in (None, "", "false", "TRUE"):
        env = os.environ.copy()
        env.pop("SESSION_SECRET", None)
        env.pop("POSTGRES_PASSWORD", None)
        env.pop("POSTGRES_HOST_PATH", None)
        if value is None:
            env.pop("INGRESS_CUTOVER_ENABLED", None)
        else:
            env["INGRESS_CUTOVER_ENABLED"] = value

        result = subprocess.run(  # noqa: S603
            [str(DEPLOY_HELPER), "test-tag"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 2  # noqa: S101
        assert "INGRESS_CUTOVER_ENABLED=true" in result.stderr  # noqa: S101
        assert "Building" not in result.stdout  # noqa: S101
