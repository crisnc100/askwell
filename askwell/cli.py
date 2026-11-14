"""The `askwell` command line."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import create_engine

from askwell import __version__
from askwell.config import get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Askwell: a governed AI data analyst.",
)


registry_app = typer.Typer(no_args_is_help=True, help="Create and check registries.")
app.add_typer(registry_app, name="registry")
replay_app = typer.Typer(no_args_is_help=True, help="Replay recordings and simulated answers.")
app.add_typer(replay_app, name="replay")


@app.callback()
def main() -> None:
    """Askwell: a governed AI data analyst."""


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

    from askwell.core.executor import readonly_engine
    from askwell.core.registry import dump_registry
    from askwell.core.registry_init import init_registry

    url = make_url(db_url)
    sqlite_path = url.database if url.get_backend_name() == "sqlite" else None
    engine = readonly_engine(db_url)
    try:
        result = init_registry(
            engine,
            include_values=values,
            name=name,
            sqlite_path=sqlite_path,
            features=get_settings().features,
        )
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
    from askwell.core.registry import load_registry

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

    from askwell.core.intent import Intent
    from askwell.core.registry import load_registry
    from askwell.core.sqlbuild import build, compile_sql
    from askwell.core.validate import validate

    settings = get_settings()
    parsed = Intent.model_validate_json(Path(intent).read_text(encoding="utf-8"))
    result = validate(
        parsed,
        load_registry(registry),
        now=settings.now,
        allow_draft=allow_draft,
        row_cap=settings.row_cap,
        features=settings.features,
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
    """Print the Askwell version."""
    typer.echo(__version__)


@app.command()
def seed(
    db_url: Annotated[
        str | None,
        typer.Option(help="Target DB URL. Defaults to ASKWELL_DATABASE_URL (owner role)."),
    ] = None,
    random_seed: Annotated[int, typer.Option("--seed", help="Random seed.")] = 20260630,
) -> None:
    """Drop, recreate and load the fieldservice demo data (deterministic)."""
    from askwell.fieldservice.seed import content_hash, generate, load

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

    from askwell.llm.gateway import OpenRouterTransport
    from askwell.llm.pricing import PriceBook
    from askwell.llm.spike import (
        advertised_support,
        fetch_models_payload,
        make_live_gateway,
        run_spike,
        write_report,
    )
    from askwell.pipeline.service import daily_spend

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
    gateway = make_live_gateway(
        transport,
        book.get,
        budget,
        max_tokens,
        daily=daily_spend(settings),
        live_answers_off=settings.live_answers_off,
    )
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

    from askwell.llm.errors import ReplayMissError
    from askwell.llm.simulate import PendingRequestError
    from askwell.pipeline.service import AskService

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


@app.command()
def sweep() -> None:
    """Delete expired workspaces and finish any deletion that failed. Run it from cron."""
    from pathlib import Path

    from askwell.workspace.store import WorkspaceStore

    result = WorkspaceStore(Path(get_settings().workspace_dir)).sweep()
    typer.echo(f"removed {len(result.removed)} expired workspace(s)")
    for name in result.failed:
        typer.echo(f"could not remove {name} yet; the next sweep retries it", err=True)


@replay_app.command("import")
def replay_import(
    pending_dir: Annotated[str | None, typer.Option(help="Default: ASKWELL_PENDING_DIR.")] = None,
    keep: Annotated[bool, typer.Option(help="Keep the pending files after import.")] = False,
) -> None:
    """Load simulated answers (<key>.answer.json) into the replay store, with provenance."""
    from pathlib import Path

    from askwell.llm.replay import ReplayStore
    from askwell.llm.simulate import import_answers_report, pending_requests
    from askwell.pipeline.service import RECORDINGS_FILE, ROOT

    settings = get_settings()
    pending = Path(pending_dir) if pending_dir else ROOT / settings.pending_dir
    store = ReplayStore(ROOT / settings.replay_dir / RECORDINGS_FILE)
    report = import_answers_report(pending, store, remove=not keep)
    for item in report.imported:
        typer.echo(
            f"imported {item.key} (simulated by {item.simulated_by}, "
            f"standing in for {item.standing_in_for})"
        )
    for rejected in report.rejected:
        typer.echo(f"REJECTED {rejected.key}: {rejected.reason}", err=True)
    left = pending_requests(pending) if pending.exists() else []
    typer.echo(
        f"{len(report.imported)} imported, {len(report.rejected)} rejected (kept on disk), "
        f"{len(left)} still pending"
    )


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
    gold: Annotated[
        Path | None,
        typer.Option(help="A second gold file for the one --schema given, e.g. a held-out set."),
    ] = None,
    items: Annotated[
        Path | None,
        typer.Option(
            help='Run only the item IDs in this JSON file ({"ids": [...]}), each for every '
            "trial, Spider included."
        ),
    ] = None,
) -> None:
    """Run the benchmark and write evals/reports/<run id>.md and .json.

    Export mode writes every unrecorded model request to evals/pending/eval/ and stops
    those items; `--mode import` loads the answers; then run again in replay mode.
    """
    from askwell.bench import report as report_module
    from askwell.bench.items import spider_databases
    from askwell.bench.run import EVAL_PENDING, EVAL_RECORDINGS, pending_counts, run_eval
    from askwell.llm.replay import ReplayStore
    from askwell.llm.simulate import import_answers_report

    if mode == "import":
        total = 0
        for directory in sorted(p for p in EVAL_PENDING.glob("*/*") if p.is_dir()):
            schema_id, system = directory.parent.name, directory.name
            store = ReplayStore(EVAL_RECORDINGS / schema_id / f"{system}.jsonl")
            result = import_answers_report(directory, store)
            total += len(result.imported)
            typer.echo(f"{schema_id}/{system}: imported {len(result.imported)}")
            for rejected in result.rejected:
                typer.echo(f"  REJECTED {rejected.key}: {rejected.reason}", err=True)
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
        gold=gold,
        item_ids=set(json.loads(items.read_text(encoding="utf-8"))["ids"]) if items else None,
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
