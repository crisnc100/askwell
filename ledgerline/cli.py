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
