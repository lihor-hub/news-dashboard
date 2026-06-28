# ruff: noqa: S101

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CADDYFILE = ROOT / "deploy" / "Caddyfile"


def test_production_caddyfile_contains_keycloak_and_hardening() -> None:
    caddyfile = PRODUCTION_CADDYFILE.read_text()

    assert "news.lihor.ro" in caddyfile
    assert "handle /keycloak*" in caddyfile
    assert "reverse_proxy 127.0.0.1:8081" in caddyfile
    assert "reverse_proxy 127.0.0.1:30088" in caddyfile
    assert "encode zstd gzip" in caddyfile
    assert "X-Content-Type-Options nosniff" in caddyfile
    assert "X-Frame-Options DENY" in caddyfile
    assert "Referrer-Policy no-referrer" in caddyfile
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"' in caddyfile


def test_docs_point_to_single_production_caddyfile() -> None:
    docs = [
        ROOT / "docs" / "CADDY_HTTPS_SETUP.md",
        ROOT / "docs" / "RUNNER_SETUP.md",
        ROOT / "docs" / "ARCHITECTURE.md",
    ]

    for doc in docs:
        text = doc.read_text()
        assert "deploy/Caddyfile" in text
        assert "deploy/news.lihor.ro.caddyfile" not in text
