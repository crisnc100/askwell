"""The `ledgerline` command line."""

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy import create_engine

from ledgerline import __version__
from ledgerline.config import get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Ledgerline: a governed AI data analyst.",
)


@app.callback()
def main() -> None:
    """Ledgerline: a governed AI data analyst."""


@app.command()
def version() -> None:
    """Print the Ledgerline version."""
    typer.echo(__version__)


@app.command()
def seed(
    db_url: Annotated[
        str | None,
        typer.Option(help="Target DB URL. Defaults to LEDGERLINE_DATABASE_URL (owner role)."),
    ] = None,
    random_seed: Annotated[int, typer.Option("--seed", help="Random seed.")] = 20260630,
) -> None:
    """Drop, recreate and load the fieldservice demo data (deterministic)."""
    from ledgerline.fieldservice.seed import content_hash, generate, load

    settings = get_settings()
    engine = create_engine(db_url or settings.database_url)
    try:
        dataset = generate(settings.now, seed=random_seed)
        load(engine, dataset)
        for name, count in dataset.counts().items():
            typer.echo(f"{name:>18}: {count}")
        typer.echo(f"reference time: {settings.now.isoformat()}")
        typer.echo(f"content sha256: {content_hash(engine)}")
    finally:
        engine.dispose()


@app.command()
def spike(
    models: Annotated[str, typer.Option(help="Comma-separated OpenRouter model ids to probe.")],
    budget: Annotated[float, typer.Option(help="Hard budget for the whole spike, USD.")] = 0.50,
    providers: Annotated[
        str | None, typer.Option(help="Optional comma-separated provider order to pin.")
    ] = None,
    max_tokens: Annotated[int, typer.Option(help="Completion cap per call.")] = 300,
    out_dir: Annotated[str, typer.Option(help="Where the JSON report goes.")] = "evals/spike",
) -> None:
    """Live: probe candidate models for json_schema support (ADR-004)."""
    from pathlib import Path

    from ledgerline.llm.gateway import OpenRouterTransport
    from ledgerline.llm.pricing import PriceBook
    from ledgerline.llm.spike import (
        advertised_support,
        fetch_models_payload,
        make_live_gateway,
        run_spike,
        write_report,
    )

    settings = get_settings()
    if settings.openrouter_api_key is None:
        typer.echo("OPENROUTER_API_KEY is not set: the spike is a live run.", err=True)
        raise typer.Exit(code=2)
    candidates = [m.strip() for m in models.split(",") if m.strip()]
    payload = fetch_models_payload(settings.openrouter_base_url)
    book = PriceBook.from_models_payload(payload)
    transport = OpenRouterTransport(
        settings, providers=[p.strip() for p in providers.split(",")] if providers else None
    )
    gateway = make_live_gateway(transport, book.get, budget, max_tokens)
    reports, stopped = run_spike(candidates, gateway, advertised_support(payload))
    path = write_report(reports, stopped, budget, Path(out_dir))
    for r in reports:
        typer.echo(
            f"{r.model}: honoured {r.honoured}/{len(r.probes)}, exact {r.exact}, ${r.cost_usd:.5f}"
        )
    if stopped:
        typer.echo(f"STOPPED: {stopped}", err=True)
    typer.echo(f"report: {path}")
