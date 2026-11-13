"""Load: store a checked set of tables in one SQLite file, all or nothing.

The file is built under a temporary name and renamed into place only when every table
loaded, so a workspace never holds half a load. Each table gets its ID column as the
primary key and each link as a foreign key, which `registry init` reads as a declared
relationship. SQLite does not enforce foreign keys unless asked, so a link value with no
match (a Check warning) still loads.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from askwell.workspace.check import TablePlan
from askwell.workspace.rules import ColumnType, Stored, convert

SQL_TYPES: dict[ColumnType, str] = {
    "integer": "INTEGER",
    "number": "REAL",
    "date": "DATE",
    "datetime": "DATETIME",
    "text": "TEXT",
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_table_sql(plan: TablePlan) -> str:
    parts = [f"{_quote(c.name)} {SQL_TYPES[c.type]}" for c in plan.columns]
    if plan.id_column is not None:
        parts.append(f"PRIMARY KEY ({_quote(plan.id_column)})")
    for link in plan.links:
        parts.append(
            f"FOREIGN KEY ({_quote(link.column)}) REFERENCES "
            f"{_quote(link.table)} ({_quote(link.target_column)})"
        )
    return f"CREATE TABLE {_quote(plan.name)} ({', '.join(parts)})"


def load_tables(plans: list[TablePlan], path: Path) -> None:
    """Write `plans` to a new SQLite file at `path`, replacing any file there."""
    tmp = path.with_name(path.name + ".loading")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        with conn:
            for plan in plans:
                conn.execute(create_table_sql(plan))
                columns = ", ".join(_quote(c.name) for c in plan.columns)
                marks = ", ".join("?" for _ in plan.columns)
                types: list[ColumnType] = [c.type for c in plan.columns]
                conn.executemany(
                    f"INSERT INTO {_quote(plan.name)} ({columns}) VALUES ({marks})",  # noqa: S608 (identifiers are slugs, quoted)
                    (_row(cells, types) for cells in plan.rows),
                )
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp, path)


def _row(cells: list[str | None], types: list[ColumnType]) -> list[Stored | None]:
    return [None if c is None else convert(c, t) for c, t in zip(cells, types, strict=True)]
