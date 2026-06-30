"""Tests for the news_dashboard.cli Typer commands.

The underlying ingest/recommendation functions are mocked so these run fast
and without a database — the CLI layer is just a thin wrapper we want to pin.
"""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from news_dashboard.cli import app

runner = CliRunner()


def test_init_syncs_sources() -> None:
    with patch("news_dashboard.cli.sync_sources") as sync:
        result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    sync.assert_called_once()
    assert "initialized" in result.stdout


def test_ingest_prints_per_source_counts_and_total() -> None:
    from news_dashboard.ingest import IngestResult

    fake = IngestResult(results={"a": 2, "b": 3, "c": -1}, run_id=1, total_errors=1)
    with patch("news_dashboard.cli.ingest_all", return_value=fake):
        result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    assert "a: 2" in result.stdout
    assert "b: 3" in result.stdout
    # Total only sums positive counts.
    assert "inserted: 5" in result.stdout


def test_scheduled_ingest_uses_scheduler_runner() -> None:
    with patch(
        "news_dashboard.scheduler.run_scheduled_ingest",
        return_value={"a": 2, "b": 0, "c": -1},
    ) as run:
        result = runner.invoke(app, ["scheduled-ingest"])
    assert result.exit_code == 0
    run.assert_called_once_with(raise_on_failure=True)
    assert "a: 2" in result.stdout
    assert "inserted: 2" in result.stdout


def test_scheduled_ingest_exits_nonzero_when_scheduler_runner_fails() -> None:
    with patch(
        "news_dashboard.scheduler.run_scheduled_ingest",
        side_effect=RuntimeError("boom"),
    ) as run:
        result = runner.invoke(app, ["scheduled-ingest"])
    assert result.exit_code == 1
    run.assert_called_once_with(raise_on_failure=True)


def test_articles_lists_rows() -> None:
    fake = [{"id": 7, "status": "new", "title": "Hello", "source_name": "Src"}]
    with patch("news_dashboard.cli.list_articles", return_value=fake) as listed:
        result = runner.invoke(app, ["articles", "--status", "new", "--limit", "5"])
    assert result.exit_code == 0
    listed.assert_called_once_with(status="new", limit=5)
    assert "[7] new Hello — Src" in result.stdout


def test_rec_health_prints_snapshot() -> None:
    health = {
        "total_scores": 10,
        "stale_scores": 1,
        "outdated_scores": 2,
        "missing_scores": 3,
        "oldest_computed_at": "2026-06-01",
        "by_model_version": [{"model_version": "v1", "count": 4}],
    }
    with patch("news_dashboard.recommendation_jobs.recommendation_health", return_value=health):
        result = runner.invoke(app, ["rec-health"])
    assert result.exit_code == 0
    assert "total_scores: 10" in result.stdout
    assert "v1: 4" in result.stdout


def test_rec_recalc_prints_summary() -> None:
    class _Summary:
        def as_dict(self) -> dict[str, int]:
            return {"recomputed": 6, "skipped": 1}

    with patch(
        "news_dashboard.recommendation_jobs.recalculate_stale_recommendations",
        return_value=_Summary(),
    ):
        result = runner.invoke(app, ["rec-recalc"])
    assert result.exit_code == 0
    assert "recomputed: 6" in result.stdout
    assert "skipped: 1" in result.stdout
