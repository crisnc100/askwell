"""The CSV path (`askwell_csv`): a database as a person would bring it to the upload
page, one CSV file per table, then the upload check, the load, the drafted registry
confirmed as drafted (no edits, the drafted name columns kept), and the same ask
pipeline with the pinned reference time.

It runs the functions the workspace store runs (check_files, load_tables, fields.draft,
fields.apply), not the store itself, whose uploads stream over HTTP. A file that fails
the check is dropped and the rest are checked again, as a person would do; every
question whose gold SQL reads a dropped table counts as refused, and the failures are
kept with their problem codes for the report. Problem codes, never problem text: the
text quotes cell values, and Spider values stay out of committed files.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine

from askwell.bench.items import EvalItem
from askwell.bench.systems import AskwellSystem, SystemAnswer
from askwell.core.executor import readonly_engine
from askwell.core.features import ALL, Features
from askwell.core.registry import Registry, load_registry, slugify
from askwell.llm.budget import BudgetGuard
from askwell.pipeline.service import AskResult, AskService, AskTarget
from askwell.workspace import fields
from askwell.workspace.check import UploadedFile, check_files
from askwell.workspace.limits import Limits
from askwell.workspace.load import load_tables

FAILED_TABLE = "csv_check_failed"
_TABLE_REF = re.compile(r"\b(?:from|join)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def export_csv(sqlite_path: Path, out_dir: Path) -> list[Path]:
    """One CSV file per table, header first, NULL as an empty cell. Text is written
    byte for byte, even where it is not valid UTF-8, so the check sees what an export
    from that database would hold."""
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.text_factory = bytes
    written: list[Path] = []
    try:
        names = [
            str(row[0], "utf-8")
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = conn.execute(f"SELECT * FROM {quoted}")  # noqa: S608 - a table name read from the file itself
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow([d[0] for d in cursor.description])
            for row in cursor:
                writer.writerow([_cell(v) for v in row])
            path = out_dir / f"{name}.csv"
            path.write_bytes(buffer.getvalue().encode("utf-8", "surrogateescape"))
            written.append(path)
    finally:
        conn.close()
    return written


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "surrogateescape")
    return str(value)


@dataclass
class CsvWorkspace:
    # None when no file passed the check: then every question counts as refused.
    registry: Registry | None
    db_path: Path | None
    # Table slug -> the problem codes of the check that dropped its file.
    failed: dict[str, list[str]] = field(default_factory=dict[str, list[str]])


def build_workspace(
    csv_files: Sequence[Path],
    work_dir: Path,
    limits: Limits | None = None,
    features: Features = ALL,
) -> CsvWorkspace:
    """Check, load, draft and confirm the files as drafted."""
    limits = limits or Limits()
    files = [UploadedFile(p.name, p.read_bytes()) for p in csv_files]
    failed: dict[str, list[str]] = {}
    while True:
        result = check_files(files, limits, features)
        if result.ok:
            break
        dropped = {r.name: r for r in result.files if not r.ok}
        if not dropped:
            raise ValueError("the check failed without a failing file")
        for name, report in dropped.items():
            failed[slugify(Path(name).stem)] = sorted({p.code for p in report.problems})
        files = [f for f in files if f.name not in dropped]
        if not files:
            return CsvWorkspace(registry=None, db_path=None, failed=failed)
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "data.sqlite"
    load_tables(result.tables, db_path)
    drafted = fields.draft(db_path, result.tables, features)
    for name, text in drafted.items():
        (work_dir / name).write_text(text, encoding="utf-8")
    info = fields.FieldInfo.from_json(drafted[fields.FIELDS_FILE])
    registry = fields.apply(load_registry(work_dir / fields.DRAFT_FILE), info, fields.Edits())
    return CsvWorkspace(registry=registry, db_path=db_path, failed=failed)


def tables_in(sql: str) -> set[str]:
    """The tables a gold query reads, as upload slugs."""
    return {slugify(name) for name in _TABLE_REF.findall(sql)}


class AskwellCsvSystem(AskwellSystem):
    name = "askwell_csv"

    def __init__(
        self, service: AskService, schema_id: str, workspace: CsvWorkspace, now: datetime
    ) -> None:
        super().__init__(service, schema_id)
        self.workspace = workspace
        self.engine: Engine | None = (
            readonly_engine(f"sqlite:///{workspace.db_path}") if workspace.db_path else None
        )
        self.now = now

    def _ask(self, item: EvalItem, trial: int) -> AskResult:
        assert self.workspace.registry is not None
        assert self.engine is not None
        target = AskTarget(
            schema_id=self.schema_id,
            registry=self.workspace.registry,
            engine=self.engine,
            allow_draft=False,
            now=self.now,
            time_zone="UTC",
            audit=None,
        )
        return self.service.ask_target(
            target,
            item.question,
            trial=trial,
            context={"system": self.name, "item_id": item.id, "trial": trial},
        )

    def answer(self, item: EvalItem, trial: int, guard: BudgetGuard | None) -> SystemAnswer:
        dropped = sorted(tables_in(item.gold_sql or "") & set(self.workspace.failed))
        if self.workspace.registry is None:
            dropped = sorted(self.workspace.failed)
        if dropped:
            return SystemAnswer(
                rows=[],
                refused=True,
                error=None,
                cost_usd=0.0,
                latency_ms=0.0,
                detail={
                    "refusal": FAILED_TABLE,
                    "issue_codes": [FAILED_TABLE],
                    "failed_tables": {t: self.workspace.failed[t] for t in dropped},
                },
            )
        return super().answer(item, trial, guard)

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
