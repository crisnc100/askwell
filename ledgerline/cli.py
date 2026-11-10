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


registry_app = typer.Typer(no_args_is_help=True, help="Create and check registries.")
app.add_typer(registry_app, name="registry")


@app.callback()
def main() -> None:
    """Ledgerline: a governed AI data analyst."""


@registry_app.command("init")
def registry_init(
    db_url: Annotated[str, typer.Argument(help="Database URL (opened read-only).")],
    output: Annotated[str, typer.Option("-o", "--output", help="Registry YAML to write.")],
    values: Annotated[
        bool,
        typer.Option(
            "--values",
            help="Read data to mark short text fields categorical, with their values.",
        ),
    ] = False,
    name: Annotated[str, typer.Option(help="Registry name.")] = "",
) -> None:
    """Draft a registry from a live database (deterministic; marked draft: true)."""
    from pathlib import Path

    from sqlalchemy.engine import make_url

    from ledgerline.core.executor import readonly_engine
    from ledgerline.core.registry import dump_registry
    from ledgerline.core.registry_init import init_registry

    url = make_url(db_url)
    sqlite_path = url.database if url.get_backend_name() == "sqlite" else None
    engine = readonly_engine(db_url)
    try:
        result = init_registry(engine, include_values=values, name=name, sqlite_path=sqlite_path)
    finally:
        engine.dispose()
    Path(output).write_text(dump_registry(result.registry), encoding="utf-8")
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
    entities = result.registry.entities
    typer.echo(
        f"wrote {output}: {len(entities)} entities, "
        f"{len(result.registry.relationships)} relationships (draft)"
    )


@registry_app.command("check")
def registry_check(
    path: Annotated[str, typer.Argument(help="Registry YAML.")],
) -> None:
    """Load and validate a registry file."""
    from ledgerline.core.registry import load_registry

    registry = load_registry(path)
    hidden = sum(f.hidden for e in registry.entities.values() for f in e.fields.values())
    typer.echo(
        f"{path}: ok, {len(registry.entities)} entities, "
        f"{len(registry.relationships)} relationships, {hidden} hidden fields"
        + (", DRAFT" if registry.draft else "")
    )


@app.command("compile")
def compile_intent(
    registry: Annotated[str, typer.Option(help="Registry YAML.")],
    intent: Annotated[str, typer.Option(help="Intent JSON file.")],
    dialect: Annotated[str, typer.Option(help="postgresql or sqlite.")] = "postgresql",
    allow_draft: Annotated[bool, typer.Option(help="Accept a draft registry.")] = False,
) -> None:
    """Validate an intent against a registry and print the SQL and its parameters."""
    import json
    from pathlib import Path

    from ledgerline.core.intent import Intent
    from ledgerline.core.registry import load_registry
    from ledgerline.core.sqlbuild import build, compile_sql
    from ledgerline.core.validate import validate

    settings = get_settings()
    parsed = Intent.model_validate_json(Path(intent).read_text(encoding="utf-8"))
    result = validate(
        parsed,
        load_registry(registry),
        now=settings.now,
        allow_draft=allow_draft,
        row_cap=settings.row_cap,
    )
    if result.refusal_reason is not None:
        typer.echo(f"refusal: {result.refusal_reason}")
        return
    if result.plan is None:
        for issue in result.issues:
            typer.echo(f"{issue.code} at {issue.location}: {issue.message}", err=True)
        raise typer.Exit(code=1)
    sql, params = compile_sql(build(result.plan), dialect)
    typer.echo(sql)
    typer.echo(json.dumps(params, default=str, indent=2))


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
