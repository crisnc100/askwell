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
replay_app = typer.Typer(no_args_is_help=True, help="Replay recordings and simulated answers.")
app.add_typer(replay_app, name="replay")


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


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="The business question.")],
    schema: Annotated[str, typer.Option(help="Schema id from config/schemas.yaml.")] = (
        "fieldservice"
    ),
    mode: Annotated[
        str | None, typer.Option(help="replay | export | record | live (default: config).")
    ] = None,
) -> None:
    """Ask one question and print the trace as JSON."""
    import json

    from ledgerline.llm.errors import ReplayMissError
    from ledgerline.llm.simulate import PendingRequestError
    from ledgerline.pipeline.service import AskService

    service = AskService.from_settings(get_settings(), mode)
    try:
        result = service.ask(schema, question)
    except PendingRequestError as exc:
        typer.echo(f"exported for a simulated answer: {exc.path}")
        raise typer.Exit(code=3) from exc
    except ReplayMissError as exc:
        typer.echo(f"no recording: {exc}", err=True)
        raise typer.Exit(code=4) from exc
    finally:
        service.close()
    typer.echo(json.dumps(result.to_dict(), indent=2, default=str))


@replay_app.command("import")
def replay_import(
    pending_dir: Annotated[
        str | None, typer.Option(help="Default: LEDGERLINE_PENDING_DIR.")
    ] = None,
    keep: Annotated[bool, typer.Option(help="Keep the pending files after import.")] = False,
) -> None:
    """Load simulated answers (<key>.answer.json) into the replay store, with provenance."""
    from pathlib import Path

    from ledgerline.llm.replay import ReplayStore
    from ledgerline.llm.simulate import import_answers, pending_requests
    from ledgerline.pipeline.service import RECORDINGS_FILE, ROOT

    settings = get_settings()
    pending = Path(pending_dir) if pending_dir else ROOT / settings.pending_dir
    store = ReplayStore(ROOT / settings.replay_dir / RECORDINGS_FILE)
    imported = import_answers(pending, store, remove=not keep)
    for item in imported:
        typer.echo(
            f"imported {item.key} (simulated by {item.simulated_by}, "
            f"standing in for {item.standing_in_for})"
        )
    left = pending_requests(pending) if pending.exists() else []
    typer.echo(f"{len(imported)} imported, {len(left)} still pending")


@app.command("eval")
def eval_command(
    schema: Annotated[
        list[str] | None,
        typer.Option("--schema", help="Schema id (repeatable), e.g. fieldservice, spider_car_1."),
    ] = None,
    all_schemas: Annotated[
        bool, typer.Option("--all", help="fieldservice and every pre-registered Spider DB.")
    ] = False,
    systems: Annotated[str, typer.Option(help="Comma-separated systems.")] = "ledgerline,oneshot",
    mode: Annotated[str, typer.Option(help="replay | export | import | record | live")] = "replay",
    models: Annotated[
        str | None, typer.Option(help="Comma-separated model ids (default: config).")
    ] = None,
    trials: Annotated[int, typer.Option(help="Trials on fieldservice (Spider runs 1).")] = 1,
    budget: Annotated[float, typer.Option(help="Hard budget for the whole run, USD.")] = 1.0,
    run_id: Annotated[str | None, typer.Option(help="Resume or name a run.")] = None,
) -> None:
    """Run the benchmark and write evals/reports/<run id>.md and .json.

    Export mode writes every unrecorded model request to evals/pending/eval/ and stops
    those items; `--mode import` loads the answers; then run again in replay mode.
    """
    from ledgerline.bench import report as report_module
    from ledgerline.bench.items import spider_databases
    from ledgerline.bench.run import EVAL_PENDING, EVAL_RECORDINGS, pending_counts, run_eval
    from ledgerline.llm.replay import ReplayStore
    from ledgerline.llm.simulate import import_answers

    if mode == "import":
        total = 0
        for directory in sorted(p for p in EVAL_PENDING.glob("*/*") if p.is_dir()):
            schema_id, system = directory.parent.name, directory.name
            store = ReplayStore(EVAL_RECORDINGS / schema_id / f"{system}.jsonl")
            done = import_answers(directory, store)
            total += len(done)
            typer.echo(f"{schema_id}/{system}: imported {len(done)}")
        typer.echo(f"{total} imported; still pending: {pending_counts() or 'none'}")
        return

    settings = get_settings()
    schema_ids = list(schema or [])
    if all_schemas:
        schema_ids = ["fieldservice", *(f"spider_{db}" for db in spider_databases())]
    if not schema_ids:
        typer.echo("give --schema or --all", err=True)
        raise typer.Exit(code=2)
    model_ids = [m.strip() for m in models.split(",")] if models else [settings.default_model or ""]
    name = run_id or f"{mode}-{'-'.join(schema_ids) if len(schema_ids) < 3 else 'all'}"
    result = run_eval(
        settings,
        run_id=name,
        schema_ids=schema_ids,
        systems=[s.strip() for s in systems.split(",")],
        mode=mode,
        models=model_ids,
        trials=trials,
        budget_usd=budget,
    )
    if result.deferred:
        typer.echo("exported for simulated answers (pending requests per schema/system):")
        for key, count in sorted(pending_counts().items()):
            typer.echo(f"  {key}: {count}")
    data = report_module.build(result)
    md, _ = report_module.write(data)
    typer.echo(
        f"{len(result.records)} finished, {sum(result.deferred.values())} deferred; report: {md}"
    )
