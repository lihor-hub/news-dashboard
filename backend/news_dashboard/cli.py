from __future__ import annotations

import typer

from .ingest import ingest_all, list_articles, sync_sources

app = typer.Typer(help="News dashboard maintenance CLI")


@app.command()
def init() -> None:
    sync_sources()
    typer.echo("database initialized and sources synced")


@app.command()
def ingest() -> None:
    results = ingest_all()
    for source, count in results.items():
        typer.echo(f"{source}: {count}")
    typer.echo(f"inserted: {sum(value for value in results.values() if value > 0)}")


@app.command()
def articles(status: str | None = None, limit: int = 20) -> None:
    for article in list_articles(status=status, limit=limit):
        typer.echo(
            f"[{article['id']}] {article['status']} {article['title']} — {article['source_name']}"
        )


@app.command(name="rec-health")
def rec_health() -> None:
    """Print a diagnostic snapshot of stale/missing recommendation scores."""
    from .recommendation_jobs import recommendation_health

    health = recommendation_health()
    for key in ("total_scores", "stale_scores", "outdated_scores", "missing_scores"):
        typer.echo(f"{key}: {health[key]}")
    typer.echo(f"oldest_computed_at: {health['oldest_computed_at']}")
    for entry in health["by_model_version"]:
        typer.echo(f"  {entry['model_version']}: {entry['count']}")


@app.command(name="rec-recalc")
def rec_recalc() -> None:
    """Recalculate stale, missing, or superseded recommendation scores."""
    from .recommendation_jobs import recalculate_stale_recommendations

    summary = recalculate_stale_recommendations()
    for key, value in summary.as_dict().items():
        typer.echo(f"{key}: {value}")


if __name__ == "__main__":
    app()
