from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = ROOT / "scripts" / "normalize_additional_egress_values.py"
DEPLOY_LIBRARY = ROOT / "scripts" / "production-deploy-lib.sh"
CHART = ROOT / "helm" / "news-dashboard"
PRODUCTION_VALUES = CHART / "values-production.yaml"
ADDITIONAL_EGRESS_EXAMPLE = ROOT / "deploy" / "additional-egress-values.example.json"
OPERATOR_DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "SELF_HOSTING.md",
    ROOT / "website" / "docs" / "self-hosting" / "index.md",
)
INVALID_MESSAGE = "Invalid additional egress values.\n"
VALID_VALUES = {
    "networkPolicy": {
        "additionalEgress": [
            {
                "ports": [{"protocol": "TCP", "port": 5432}],
                "to": [{"ipBlock": {"cidr": "10.20.0.0/24"}}],
            }
        ]
    }
}


def run_normalizer(
    tmp_path: Path,
    content: str | bytes,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    source = tmp_path / "operator-values.json"
    output = tmp_path / "normalized-values.json"
    source.write_bytes(content.encode() if isinstance(content, str) else content)
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-S", str(NORMALIZER), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, output


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            json.dumps(
                {
                    "production": False,
                    "ingress": {"enabled": False},
                    "image": {"repository": "attacker.invalid/news-dashboard"},
                    "networkPolicy": {
                        "enabled": False,
                        "publicEgress": [],
                        "additionalEgress": [{"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}],
                    },
                }
            ),
            id="original-unrestricted-overlay-bypass",
        ),
        pytest.param(
            f"{json.dumps(VALID_VALUES)}\n{json.dumps({'production': False})}",
            id="multiple-documents",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":[{"to":[],"to":[{"ipBlock":{}}]}]}}',
            id="duplicate-nested-key",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress: &rules
    - to: []
""",
            id="yaml-anchor",
        ),
        pytest.param(
            """
rules: &rules
  additionalEgress:
    - to: []
networkPolicy:
  <<: *rules
""",
            id="yaml-alias-and-merge-key",
        ),
        pytest.param(
            json.dumps(
                {
                    "networkPolicy": {
                        "additionalEgress": VALID_VALUES["networkPolicy"]["additionalEgress"],
                        "enabled": False,
                    }
                }
            ),
            id="unknown-network-policy-sibling",
        ),
        pytest.param(
            json.dumps({**VALID_VALUES, "unexpected": True}),
            id="unknown-top-level-key",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":[]}}',
            id="empty-list",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":null}}',
            id="null",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":"disabled"}}',
            id="scalar",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":{}}}',
            id="mapping",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":[{"port":' + ("9" * 5000) + "}]}}",
            id="five-thousand-digit-number",
        ),
        pytest.param(
            '{"networkPolicy":{"additionalEgress":[' + ("[" * 1500) + "0" + ("]" * 1500) + "]}}",
            id="fifteen-hundred-level-nesting",
        ),
        pytest.param(b'{"networkPolicy":\xff}', id="invalid-utf8"),
        pytest.param(b" " * (64 * 1024 + 1), id="oversized-input"),
    ],
)
def test_normalizer_rejects_invalid_or_resource_intensive_input_without_leaking(
    tmp_path: Path,
    content: str | bytes,
) -> None:
    result, output = run_normalizer(tmp_path, content)

    assert result.returncode == 2  # noqa: S101
    assert result.stderr == INVALID_MESSAGE  # noqa: S101
    assert len(result.stderr) < 80  # noqa: S101
    assert result.stdout == ""  # noqa: S101
    assert not output.exists()  # noqa: S101


def test_normalizer_uses_only_the_standard_library() -> None:
    source = NORMALIZER.read_text()
    deploy_library = DEPLOY_LIBRARY.read_text()

    assert "import yaml" not in source  # noqa: S101
    assert "from yaml" not in source  # noqa: S101
    assert "python3 ./scripts/normalize_additional_egress_values.py" in deploy_library  # noqa: S101
    assert ".venv" not in deploy_library  # noqa: S101


def test_normalizer_emits_exact_safe_json_and_helm_renders_it(tmp_path: Path) -> None:
    result, output = run_normalizer(tmp_path, json.dumps(VALID_VALUES))

    assert result.returncode == 0, result.stderr  # noqa: S101
    assert result.stdout == ""  # noqa: S101
    assert output.read_text() == json.dumps(VALID_VALUES, indent=2) + "\n"  # noqa: S101

    helm = shutil.which("helm")
    assert helm is not None  # noqa: S101
    render = subprocess.run(  # noqa: S603
        [
            helm,
            "template",
            "normalized",
            str(CHART),
            "--values",
            str(PRODUCTION_VALUES),
            "--values",
            str(output),
            "--set-string",
            "image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--set-string",
            "app.auth.sessionSecret=render-session-secret",
            "--set-string",
            "postgresql.password=render-postgres-password",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert render.returncode == 0, render.stderr  # noqa: S101
    resources = [document for document in yaml.safe_load_all(render.stdout) if document]
    policy = next(
        resource
        for resource in resources
        if resource["kind"] == "NetworkPolicy"
        and resource["metadata"]["name"] == "normalized-news-dashboard-additional-egress"
    )
    assert policy["spec"]["egress"] == VALID_VALUES["networkPolicy"]["additionalEgress"]  # noqa: S101


def test_shared_deploy_library_writes_mode_600_json_and_cleans_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "operator-values.json"
    source.write_text(json.dumps(VALID_VALUES))
    env = os.environ.copy()
    env.update(
        {
            "SESSION_SECRET": "integration-session-secret",
            "POSTGRES_PASSWORD": "integration-postgres-password",
        }
    )
    command = f"""
set -euo pipefail
source {shlex.quote(str(DEPLOY_LIBRARY))}
prepare_production_helm_secret_files
prepare_production_additional_egress_file {shlex.quote(str(source))}
python3 -S - "$PRODUCTION_ADDITIONAL_EGRESS_FILE" <<'PY'
import json
import pathlib
import stat
import sys
path = pathlib.Path(sys.argv[1])
assert stat.S_IMODE(path.stat().st_mode) == 0o600
assert json.loads(path.read_text()) == {VALID_VALUES!r}
PY
normalized_path="$PRODUCTION_ADDITIONAL_EGRESS_FILE"
cleanup_production_helm_secret_files
[[ ! -e "$normalized_path" ]]
"""
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    assert result.stdout == ""  # noqa: S101


def test_operator_contract_consistently_requires_json() -> None:
    assert ADDITIONAL_EGRESS_EXAMPLE.is_file()  # noqa: S101
    assert json.loads(ADDITIONAL_EGRESS_EXAMPLE.read_text()) == VALID_VALUES  # noqa: S101
    for document in OPERATOR_DOCS:
        content = document.read_text()
        assert "additional-egress-values.example.json" in content, document  # noqa: S101
        assert "strict JSON" in content, document  # noqa: S101
        assert "additional-egress-values.example.yaml" not in content, document  # noqa: S101
