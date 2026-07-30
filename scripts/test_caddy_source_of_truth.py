# ruff: noqa: S101

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CADDYFILE = ROOT / "deploy" / "Caddyfile"
SELF_HOSTING = ROOT / "docs" / "SELF_HOSTING.md"
HTTPS_CADDY = ROOT / "website" / "docs" / "configuration" / "https-caddy.md"
ARCHITECTURE = ROOT / "website" / "docs" / "architecture" / "index.md"
PRODUCT_SPEC = ROOT / "website" / "docs" / "architecture" / "product-spec.md"
POSTGRES_BACKUP = ROOT / "website" / "docs" / "configuration" / "postgres-backup.md"


def test_caddyfile_preserves_keycloak_but_no_longer_routes_the_application() -> None:
    caddyfile = PRODUCTION_CADDYFILE.read_text()

    assert "news.lihor.ro" in caddyfile
    assert "handle /keycloak*" in caddyfile
    assert "reverse_proxy 127.0.0.1:8081" in caddyfile
    assert "reverse_proxy 127.0.0.1:30088" not in caddyfile
    assert "X-Content-Type-Options nosniff" in caddyfile
    assert "X-Frame-Options DENY" in caddyfile
    assert "Referrer-Policy no-referrer" in caddyfile
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"' in caddyfile


def test_ingress_is_documented_as_the_application_tls_source_of_truth() -> None:
    docs = [HTTPS_CADDY, ARCHITECTURE, PRODUCT_SPEC]

    for doc in docs:
        text = doc.read_text()
        assert "Ingress" in text
        assert "Caddy is the application TLS source of truth" not in text
        assert "Caddy config is the only production source of truth" not in text


def test_runbook_preserves_keycloak_and_orders_a_safe_cutover() -> None:
    runbook = HTTPS_CADDY.read_text()

    rollback_index = runbook.index("## Prepare rollback")
    remove_route_index = runbook.index("## Remove the old application route")

    assert "preserve the existing Keycloak route" in runbook
    assert "ports 80 and 443" in runbook
    assert rollback_index < remove_route_index


def test_runbook_covers_host_postgresql_controls() -> None:
    runbook = SELF_HOSTING.read_text()

    for requirement in (
        "listen_addresses",
        "pg_hba.conf",
        "firewall",
        "TLS",
        "backups",
        "restore verification",
    ):
        assert requirement in runbook


def test_docs_link_the_manual_appliance_rollout_issue() -> None:
    assert "issues/1302" in SELF_HOSTING.read_text()


def test_operator_docs_do_not_publish_private_inventory() -> None:
    operator_docs = (SELF_HOSTING, HTTPS_CADDY, POSTGRES_BACKUP)

    for doc in operator_docs:
        text = doc.read_text()
        assert "ioachim-minipc" not in text
        assert "192.168." not in text
