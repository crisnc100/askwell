"""The `ledgerline` command line."""

from __future__ import annotations

import typer

from ledgerline import __version__

app = typer.Typer(
    no_args_is_help=True, add_completion=False, help="Ledgerline: a governed AI data analyst."
)


@app.command()
def version() -> None:
    """Print the Ledgerline version."""
    typer.echo(__version__)


@app.callback()
def main() -> None:
    """Ledgerline: a governed AI data analyst."""
