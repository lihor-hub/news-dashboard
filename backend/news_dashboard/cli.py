from __future__ import annotations

import logging

import typer

from news_dashboard.ingest import ingest_all, list_articles, sync_sources

logger = logging.getLogger(__name__)

app = typer.Typer(help="News dashboard maintenance CLI")


@app.command()
def init() -> None:
    sync_sources()
    typer.echo("database initialized and sources synced")


@app.command()
def ingest() -> None:
    ingest_result = ingest_all()
    for source, count in ingest_result.results.items():
        typer.echo(f"{source}: {count}")
    typer.echo(f"inserted: {sum(value for value in ingest_result.results.values() if value > 0)}")
    # Short-lived process: flush any buffered Langfuse traces before exit.
    from news_dashboard.ai_client import flush

    flush()


@app.command(name="scheduled-ingest")
def scheduled_ingest() -> None:
    from news_dashboard.scheduler import run_scheduled_ingest

    try:
        results = run_scheduled_ingest(raise_on_failure=True)
    except Exception as e:
        logger.exception("Scheduled ingest failed")
        raise typer.Exit(code=1) from e
    for source, count in results.items():
        typer.echo(f"{source}: {count}")
    typer.echo(f"inserted: {sum(value for value in results.values() if value > 0)}")
    # Short-lived process: flush any buffered Langfuse traces before exit.
    from news_dashboard.ai_client import flush

    flush()


@app.command()
def articles(status: str | None = None, limit: int = 20) -> None:
    for article in list_articles(status=status, limit=limit):
        typer.echo(
            f"[{article['id']}] {article['status']} {article['title']} — {article['source_name']}"
        )


@app.command(name="rec-health")
def rec_health() -> None:
    """Print a diagnostic snapshot of stale/missing recommendation scores."""
    from news_dashboard.recommendation_jobs import recommendation_health

    health = recommendation_health()
    for key in ("total_scores", "stale_scores", "outdated_scores", "missing_scores"):
        typer.echo(f"{key}: {health[key]}")
    typer.echo(f"oldest_computed_at: {health['oldest_computed_at']}")
    for entry in health["by_model_version"]:
        typer.echo(f"  {entry['model_version']}: {entry['count']}")


@app.command(name="rec-recalc")
def rec_recalc() -> None:
    """Recalculate stale, missing, or superseded recommendation scores."""
    from news_dashboard.recommendation_jobs import recalculate_stale_recommendations

    summary = recalculate_stale_recommendations()
    for key, value in summary.as_dict().items():
        typer.echo(f"{key}: {value}")


@app.command(name="improve-prompt")
def improve_prompt(
    name: str = "ask-system",
    days: int = 14,
    max_examples: int = 50,
) -> None:
    """Draft an improved prompt version from thumbs-down feedback in Langfuse.

    Fetches recent unhelpful answers, asks an LLM to revise the prompt, and saves
    the result to Langfuse under the 'candidate' label for human review. Does NOT
    auto-deploy: promote the candidate to 'production' in the Langfuse UI.
    """
    from news_dashboard.embeddings import ASK_SYSTEM_PROMPT
    from news_dashboard.prompt_optimizer import PromptOptimizerError, optimize_prompt

    fallback = ASK_SYSTEM_PROMPT if name == "ask-system" else ""
    try:
        result = optimize_prompt(
            prompt_name=name,
            fallback=fallback,
            days=days,
            max_examples=max_examples,
        )
    except PromptOptimizerError as exc:
        typer.echo(f"skipped: {exc}")
        raise typer.Exit(code=0) from exc

    typer.echo(
        f"proposed candidate for '{result.prompt_name}' "
        f"(version {result.new_version}, label '{result.candidate_label}') "
        f"from {result.example_count} thumbs-down examples"
    )
    typer.echo("review it in Langfuse and promote to 'production' if it is an improvement.")

    from news_dashboard.ai_client import flush

    flush()


if __name__ == "__main__":
    app()
