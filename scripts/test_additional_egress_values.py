from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = ROOT / "scripts" / "normalize_additional_egress_values.py"
CHART = ROOT / "helm" / "news-dashboard"
PRODUCTION_VALUES = CHART / "values-production.yaml"


def run_normalizer(
    tmp_path: Path,
    content: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    source = tmp_path / "operator-values.yaml"
    output = tmp_path / "normalized-values.yaml"
    source.write_text(content)
    result = subprocess.run(  # noqa: S603
        [str(NORMALIZER), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, output


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            """
production: false
ingress:
  enabled: false
image:
  repository: attacker.invalid/news-dashboard
networkPolicy:
  enabled: false
  publicEgress: []
  additionalEgress:
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
""",
            id="original-unrestricted-overlay-bypass",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress:
    - to:
        - ipBlock:
            cidr: 10.20.0.0/24
---
production: false
""",
            id="multiple-documents",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress:
    - to: []
      to:
        - ipBlock:
            cidr: 0.0.0.0/0
""",
            id="duplicate-nested-key",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress: &rules
    - to:
        - ipBlock:
            cidr: 10.20.0.0/24
""",
            id="anchor",
        ),
        pytest.param(
            """
rules: &rules
  additionalEgress:
    - to:
        - ipBlock:
            cidr: 10.20.0.0/24
networkPolicy:
  <<: *rules
""",
            id="alias-and-merge-key",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress:
    - to:
        - ipBlock:
            cidr: 10.20.0.0/24
  enabled: false
""",
            id="unknown-network-policy-sibling",
        ),
        pytest.param(
            """
networkPolicy:
  additionalEgress:
    - to:
        - ipBlock:
            cidr: 10.20.0.0/24
unexpected: true
""",
            id="unknown-top-level-key",
        ),
        pytest.param("networkPolicy:\n  additionalEgress: []\n", id="empty-list"),
        pytest.param("networkPolicy:\n  additionalEgress: null\n", id="null"),
        pytest.param("networkPolicy:\n  additionalEgress: disabled\n", id="scalar"),
        pytest.param("networkPolicy:\n  additionalEgress: {}\n", id="mapping"),
    ],
)
def test_normalizer_rejects_non_egress_helm_overlays(
    tmp_path: Path,
    content: str,
) -> None:
    result, output = run_normalizer(tmp_path, content)

    assert result.returncode == 2  # noqa: S101
    assert "invalid additional egress values" in result.stderr.lower()  # noqa: S101
    assert "attacker.invalid" not in result.stderr  # noqa: S101
    assert "0.0.0.0/0" not in result.stderr  # noqa: S101
    assert result.stdout == ""  # noqa: S101
    assert not output.exists()  # noqa: S101


def test_normalizer_emits_only_the_allowed_subtree_and_helm_renders_it(
    tmp_path: Path,
) -> None:
    result, output = run_normalizer(
        tmp_path,
        """
networkPolicy:
  additionalEgress:
    - ports:
        - protocol: TCP
          port: 5432
      to:
        - ipBlock:
            cidr: 10.20.0.0/24
""",
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    assert result.stdout == ""  # noqa: S101
    assert yaml.safe_load(output.read_text()) == {  # noqa: S101
        "networkPolicy": {
            "additionalEgress": [
                {
                    "ports": [{"protocol": "TCP", "port": 5432}],
                    "to": [{"ipBlock": {"cidr": "10.20.0.0/24"}}],
                }
            ]
        }
    }

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
    assert policy["spec"]["egress"] == [  # noqa: S101
        {
            "ports": [{"protocol": "TCP", "port": 5432}],
            "to": [{"ipBlock": {"cidr": "10.20.0.0/24"}}],
        }
    ]
