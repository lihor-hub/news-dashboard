"""Tests for the optional Prometheus /metrics endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.main import app
from news_dashboard.metrics import (
    ingest_articles_new_total,
    ingest_runs_total,
    scheduler_job_runs_total,
)


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


@pytest.mark.smoke
def test_metrics_not_served_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    resp = _client().get("/metrics")
    assert resp.status_code == 404


@pytest.mark.smoke
def test_metrics_returns_exposition_format_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "true")
    ingest_runs_total.labels(status="success").inc()
    ingest_articles_new_total.inc(3)
    scheduler_job_runs_total.labels(job_name="digest", status="success").inc()

    resp = _client().get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "news_dashboard_ingest_runs_total" in body
    assert "news_dashboard_ingest_articles_new_total" in body
    assert "news_dashboard_scheduler_job_runs_total" in body


@pytest.mark.smoke
@pytest.mark.parametrize("flag_value", ["0", "false", "no", "off", ""])
def test_metrics_disabled_flag_values(monkeypatch: pytest.MonkeyPatch, flag_value: str) -> None:
    monkeypatch.setenv("METRICS_ENABLED", flag_value)
    resp = _client().get("/metrics")
    assert resp.status_code == 404
