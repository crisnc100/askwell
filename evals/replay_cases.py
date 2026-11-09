"""The questions whose model answers are recorded for the replay tests and the demo.

`uv run python -m evals.replay_cases export` runs each one through the pipeline in
export mode, writing every unrecorded model request to evals/pending/. After the answers
are imported (`ledgerline replay import`), run it again: a question whose first answer
failed validation then exports its retry request.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ledgerline.config import Settings, get_settings
from ledgerline.core.executor import readonly_engine
from ledgerline.core.registry import dump_registry
from ledgerline.core.registry_init import init_registry
from ledgerline.llm.simulate import PendingRequestError
from ledgerline.pipeline.service import AskService, SchemaConfig, build_gateway, load_schemas

ROOT = Path(__file__).resolve().parent.parent
SPIDER_DB = "dog_kennels"
SPIDER_PATH = (
    ROOT / "data" / "spider" / "spider_data" / "database" / SPIDER_DB / f"{SPIDER_DB}.sqlite"
)
# Written for this test; not a Spider question.
SPIDER_QUESTION = "How much has been spent on treatments in total for each breed of dog?"


def spider_schema(work_dir: Path) -> SchemaConfig:
    """`registry init --values` on the Spider DB, unedited, as a draft schema."""
    if not SPIDER_PATH.exists():
        raise FileNotFoundError(f"{SPIDER_PATH}: run `uv run python -m scripts.fetch_benchmarks`")
    url = f"sqlite:///{SPIDER_PATH}"
    engine = readonly_engine(url)
    try:
        registry = init_registry(engine, include_values=True, name=SPIDER_DB).registry
    finally:
        engine.dispose()
    path = work_dir / f"{SPIDER_DB}.yaml"
    path.write_text(dump_registry(registry), encoding="utf-8")
    return SchemaConfig(
        id=f"spider_{SPIDER_DB}", title=SPIDER_DB, registry_path=path, db_url=url, allow_draft=True
    )


def cases(
    settings: Settings, work_dir: Path
) -> tuple[dict[str, SchemaConfig], list[tuple[str, str]]]:
    schemas = load_schemas(settings)
    spider = spider_schema(work_dir)
    schemas[spider.id] = spider
    questions = [("fieldservice", q) for q in schemas["fieldservice"].examples]
    questions.append((spider.id, SPIDER_QUESTION))
    return schemas, questions


def export(work_dir: Path) -> list[Path]:
    settings = get_settings()
    schemas, questions = cases(settings, work_dir)
    service = AskService(settings, schemas, build_gateway(settings, "export"), audit=None)
    exported: list[Path] = []
    try:
        for schema_id, question in questions:
            try:
                service.ask(schema_id, question)
            except PendingRequestError as exc:
                exported.append(exc.path)
                print(f"pending  {exc.path.relative_to(ROOT)}  [{schema_id}] {question}")
                continue
            print(f"recorded [{schema_id}] {question}")
    finally:
        service.close()
    return exported


def main(argv: list[str]) -> int:
    if argv[:1] != ["export"]:
        print("usage: python -m evals.replay_cases export")
        return 2
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        exported = export(Path(tmp))
    print(f"{len(exported)} request(s) pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
