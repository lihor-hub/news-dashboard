# ruff: noqa: S101
"""Rendered-manifest security contracts for the production Helm values."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "news-dashboard"
PRODUCTION_VALUES = CHART / "values-production.yaml"
ADDITIONAL_EGRESS_EXAMPLE = ROOT / "deploy" / "additional-egress-values.example.yaml"
TEST_APP_DIGEST = f"sha256:{'a' * 64}"
PUBLIC_EGRESS_IPV4_EXCEPTIONS = {
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
}
PUBLIC_EGRESS_IPV6_EXCEPTIONS = {
    "2001::/23",
    "2001:db8::/32",
    "2002::/16",
    "3fff::/20",
}


def render_chart(*arguments: str) -> list[dict[str, object]]:
    """Render the chart with the secrets needed only for manifest rendering."""
    command = [
        "helm",
        "template",
        "release",
        str(CHART),
        "--set-string",
        "app.auth.sessionSecret=render-only-session-secret",
        "--set-string",
        "postgresql.password=render-only-postgres-password",
        "--set-string",
        "neo4j.auth.password=render-only-neo4j-password",
        "--set-string",
        f"image.digest={TEST_APP_DIGEST}",
        *arguments,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def find_resource(rendered: Iterable[dict[str, object]], kind: str, name: str) -> dict[str, object]:
    for resource in rendered:
        metadata = resource.get("metadata", {})
        if resource["kind"] == kind and metadata.get("name") == name:
            return resource
    message = f"{kind}/{name} was not rendered"
    raise AssertionError(message)


def find_kind(rendered: Iterable[dict[str, object]], kind: str) -> dict[str, object]:
    for resource in rendered:
        if resource["kind"] == kind:
            return resource
    message = f"No {kind} was rendered"
    raise AssertionError(message)


def resource_names(rendered: Iterable[dict[str, object]], kind: str) -> set[str]:
    return {resource["metadata"]["name"] for resource in rendered if resource["kind"] == kind}


def rendered_pod_specs(rendered: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    pod_specs: list[dict[str, object]] = []
    for resource in rendered:
        spec = resource.get("spec", {})
        if resource["kind"] in {"Deployment", "StatefulSet"}:
            pod_specs.append(spec["template"]["spec"])
        elif resource["kind"] == "CronJob":
            pod_specs.append(spec["jobTemplate"]["spec"]["template"]["spec"])
    return pod_specs


def container(resource: dict[str, object], name: str) -> dict[str, object]:
    for pod_spec in rendered_pod_specs([resource]):
        for candidate in pod_spec["containers"]:
            if candidate["name"] == name:
                return candidate
    message = f"Container {name} was not rendered"
    raise AssertionError(message)


def assert_restrictive_security_context(resource: dict[str, object], container_name: str) -> None:
    pod_spec = rendered_pod_specs([resource])[0]
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    context = container(resource, container_name)["securityContext"]
    assert context["allowPrivilegeEscalation"] is False
    assert context["capabilities"]["drop"] == ["ALL"]


def test_production_service_is_cluster_ip_without_node_port() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    service = find_resource(rendered, "Service", "release-news-dashboard")
    assert service["spec"]["type"] == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]
    assert "NodePort" not in yaml.safe_dump_all(rendered)


def test_production_renders_application_images_by_digest() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    expected = f"ghcr.io/lihor-hub/news-dashboard@{TEST_APP_DIGEST}"
    deployment = find_resource(rendered, "Deployment", "release-news-dashboard")
    ingest = find_resource(rendered, "CronJob", "release-news-dashboard-ingest")

    assert container(deployment, "news-dashboard")["image"] == expected
    assert container(ingest, "ingest")["image"] == expected


def test_production_rejects_missing_or_invalid_application_digest() -> None:
    for arguments in (
        [],
        ["--set-string", "image.digest=sha256:not-a-digest"],
        ["--set-string", f"image.digest=sha512:{'a' * 64}"],
    ):
        command = [
            "helm",
            "template",
            "release",
            str(CHART),
            "--values",
            str(PRODUCTION_VALUES),
            "--set-string",
            "app.auth.sessionSecret=render-only-session-secret",
            "--set-string",
            "postgresql.password=render-only-postgres-password",
            *arguments,
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603

        assert result.returncode != 0
        assert "image.digest must be a sha256 digest in production" in result.stderr


def test_production_rejects_non_cluster_ip_service_configuration() -> None:
    command = [
        "helm",
        "template",
        "release",
        str(CHART),
        "--values",
        str(PRODUCTION_VALUES),
        "--set",
        "service.type=NodePort",
        "--set-string",
        "app.auth.sessionSecret=render-only-session-secret",
        "--set-string",
        "postgresql.password=render-only-postgres-password",
        "--set-string",
        "neo4j.auth.password=render-only-neo4j-password",
        "--set-string",
        f"image.digest={TEST_APP_DIGEST}",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0
    assert "service.type must be ClusterIP in production" in result.stderr


def test_network_policy_requires_controller_selectors() -> None:
    command = [
        "helm",
        "template",
        "release",
        str(CHART),
        "--set",
        "networkPolicy.enabled=true",
        "--set-string",
        "app.auth.sessionSecret=render-only-session-secret",
        "--set-string",
        "postgresql.password=render-only-postgres-password",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0
    assert "networkPolicy.ingressController selectors must be configured" in result.stderr


def test_production_ingress_requires_tls() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    ingress = find_kind(rendered, "Ingress")
    assert ingress["spec"]["tls"][0]["hosts"] == ["news.lihor.ro"]


def test_production_traefik_enforces_redirect_and_baseline_headers() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    ingress = find_kind(rendered, "Ingress")
    redirect = find_resource(
        rendered,
        "Middleware",
        "release-news-dashboard-redirect-https",
    )
    headers = find_resource(
        rendered,
        "Middleware",
        "release-news-dashboard-security-headers",
    )

    assert ingress["spec"]["ingressClassName"] == "traefik"
    assert ingress["spec"]["tls"][0]["secretName"] == "news-dashboard-tls"
    assert ingress["metadata"]["annotations"] == {
        "traefik.ingress.kubernetes.io/router.entrypoints": "web,websecure",
        "traefik.ingress.kubernetes.io/router.middlewares": (
            "default-release-news-dashboard-redirect-https@kubernetescrd,"
            "default-release-news-dashboard-security-headers@kubernetescrd"
        ),
    }
    assert redirect["spec"]["redirectScheme"] == {"scheme": "https", "permanent": True}
    assert headers["spec"]["headers"] == {
        "contentTypeNosniff": True,
        "frameDeny": True,
        "referrerPolicy": "no-referrer",
        "permissionsPolicy": "camera=(), microphone=(), geolocation=()",
        "stsSeconds": 31536000,
        "stsIncludeSubdomains": True,
        "stsPreload": True,
    }
    assert "contentSecurityPolicy" not in headers["spec"]["headers"]
    assert "customResponseHeaders" not in headers["spec"]["headers"]


def test_production_enables_application_hsts() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    deployment = find_resource(rendered, "Deployment", "release-news-dashboard")
    app_env = {
        entry["name"]: entry.get("value")
        for entry in container(deployment, "news-dashboard")["env"]
    }

    assert app_env["ENABLE_HSTS"] == "true"


def test_production_rejects_disabled_transport_hardening() -> None:
    for override, expected_error in (
        (
            "ingress.traefik.middlewareEnabled=false",
            "Traefik middleware must be enabled in production",
        ),
        ("app.config.enableHsts=false", "application HSTS must be enabled in production"),
    ):
        command = [
            "helm",
            "template",
            "release",
            str(CHART),
            "--values",
            str(PRODUCTION_VALUES),
            "--set",
            override,
            "--set-string",
            "app.auth.sessionSecret=render-only-session-secret",
            "--set-string",
            "postgresql.password=render-only-postgres-password",
            "--set-string",
            f"image.digest={TEST_APP_DIGEST}",
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603

        assert result.returncode != 0
        assert expected_error in result.stderr


def test_production_rejects_ingress_without_tls() -> None:
    command = [
        "helm",
        "template",
        "release",
        str(CHART),
        "--values",
        str(PRODUCTION_VALUES),
        "--set-json",
        "ingress.tls=[]",
        "--set-string",
        "app.auth.sessionSecret=render-only-session-secret",
        "--set-string",
        "postgresql.password=render-only-postgres-password",
        "--set-string",
        f"image.digest={TEST_APP_DIGEST}",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0
    assert "ingress.tls must be configured in production" in result.stderr


def test_all_workloads_disable_service_account_token_mounting() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    for pod_spec in rendered_pod_specs(rendered):
        assert pod_spec["automountServiceAccountToken"] is False


def test_production_renders_default_deny_and_required_allow_policies() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    policy_names = resource_names(rendered, "NetworkPolicy")
    assert {
        "release-news-dashboard-default-deny",
        "release-news-dashboard-app",
        "release-news-dashboard-ingest",
        "release-news-dashboard-postgres",
        "release-news-dashboard-neo4j",
        "release-news-dashboard-dns",
        "release-news-dashboard-public-egress",
    } <= policy_names


def test_network_policies_allow_controller_dns_https_and_configured_egress() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    app_policy = find_resource(rendered, "NetworkPolicy", "release-news-dashboard-app")
    ingress_peer = app_policy["spec"]["ingress"][0]["from"][0]
    assert ingress_peer["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": "traefik"
    }
    assert ingress_peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "traefik"}

    policies = {
        resource["metadata"]["name"]: resource
        for resource in rendered
        if resource["kind"] == "NetworkPolicy"
    }
    egress = (
        policies["release-news-dashboard-app"]["spec"]["egress"]
        + policies["release-news-dashboard-dns"]["spec"]["egress"]
        + policies["release-news-dashboard-public-egress"]["spec"]["egress"]
    )
    ports = {
        (port["protocol"], port["port"]) for entry in egress for port in entry.get("ports", [])
    }
    assert {("UDP", 53), ("TCP", 53), ("TCP", 443), ("TCP", 5432), ("TCP", 7687)} <= ports
    ip_blocks = [
        peer["ipBlock"] for entry in egress for peer in entry.get("to", []) if "ipBlock" in peer
    ]
    assert any(
        block["cidr"] == "0.0.0.0/0" and set(block["except"]) == PUBLIC_EGRESS_IPV4_EXCEPTIONS
        for block in ip_blocks
    )

    configured = render_chart(
        "--values",
        str(PRODUCTION_VALUES),
        "--set",
        "networkPolicy.additionalEgress[0].to[0].ipBlock.cidr=10.0.0.0/8",
    )
    additional = find_resource(
        configured, "NetworkPolicy", "release-news-dashboard-additional-egress"
    )
    assert additional["spec"]["egress"][0]["to"][0]["ipBlock"] == {"cidr": "10.0.0.0/8"}


def test_operator_additional_egress_example_renders_private_custom_service() -> None:
    rendered = render_chart(
        "--values",
        str(PRODUCTION_VALUES),
        "--values",
        str(ADDITIONAL_EGRESS_EXAMPLE),
    )
    policy = find_resource(
        rendered,
        "NetworkPolicy",
        "release-news-dashboard-additional-egress",
    )

    assert policy["spec"]["egress"] == [
        {
            "to": [{"ipBlock": {"cidr": "10.20.0.0/24"}}],
            "ports": [{"protocol": "TCP", "port": 5432}],
        }
    ]


def test_production_public_egress_excludes_non_global_networks() -> None:
    rendered = render_chart("--values", str(PRODUCTION_VALUES))
    policy = find_resource(rendered, "NetworkPolicy", "release-news-dashboard-public-egress")
    entries = policy["spec"]["egress"]

    assert {(port["protocol"], port["port"]) for entry in entries for port in entry["ports"]} == {
        ("TCP", 443),
        ("TCP", 465),
        ("TCP", 587),
        ("TCP", 993),
    }
    ip_blocks = {
        peer["ipBlock"]["cidr"]: set(peer["ipBlock"]["except"])
        for entry in entries
        for peer in entry["to"]
    }
    assert ip_blocks["0.0.0.0/0"] == PUBLIC_EGRESS_IPV4_EXCEPTIONS
    assert ip_blocks["2000::/3"] == PUBLIC_EGRESS_IPV6_EXCEPTIONS


def test_backup_policy_allows_backup_to_bundled_postgres() -> None:
    rendered = render_chart(
        "--values",
        str(PRODUCTION_VALUES),
        "--set",
        "postgresql.backup.enabled=true",
        "--set",
        "postgresql.backup.hostPath=/var/backups/news-dashboard",
    )
    policy = find_resource(
        rendered,
        "NetworkPolicy",
        "release-news-dashboard-postgres-backup",
    )

    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "news-dashboard-postgres-backup",
        "app.kubernetes.io/instance": "release",
    }
    assert policy["spec"]["egress"] == [
        {
            "to": [
                {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "news-dashboard-postgres",
                            "app.kubernetes.io/instance": "release",
                        }
                    }
                }
            ],
            "ports": [{"protocol": "TCP", "port": 5432}],
        }
    ]


def test_production_workloads_have_image_compatible_restrictive_security_contexts() -> None:
    rendered = render_chart(
        "--values",
        str(PRODUCTION_VALUES),
        "--set",
        "postgresql.backup.enabled=true",
        "--set",
        "postgresql.backup.hostPath=/var/backups/news-dashboard",
        "--set",
        "neo4j.enabled=true",
    )
    app = find_resource(rendered, "Deployment", "release-news-dashboard")
    ingest = find_resource(rendered, "CronJob", "release-news-dashboard-ingest")
    postgres_backup = find_resource(rendered, "CronJob", "release-news-dashboard-postgres-backup")
    neo4j = find_resource(rendered, "StatefulSet", "release-news-dashboard-neo4j")

    for pod_spec in rendered_pod_specs(rendered):
        assert pod_spec["automountServiceAccountToken"] is False

    for resource, name in (
        (app, "news-dashboard"),
        (ingest, "ingest"),
        (postgres_backup, "postgres-backup"),
        (neo4j, "neo4j"),
    ):
        assert_restrictive_security_context(resource, name)

    for resource, name in ((app, "news-dashboard"), (ingest, "ingest")):
        context = container(resource, name)["securityContext"]
        assert context["runAsNonRoot"] is True
        assert context["readOnlyRootFilesystem"] is True
