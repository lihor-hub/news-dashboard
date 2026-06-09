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


if __name__ == "__main__":
    app()
