"""L20: everything that passes Check loads, and every value reads back as what the cell
said. Hypothesis writes valid and messy-but-valid files: a BOM, CRLF line ends, quoted
commas and line breaks, null spellings, leading zeros, and link columns (some values
with no match)."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ledgerline.core.registry import slugify
from ledgerline.workspace.check import UploadedFile, check_files
from ledgerline.workspace.load import load_tables
from ledgerline.workspace.rules import ColumnType, convert, is_null
from tests.workspace.conftest import SAMPLE

NULLS = ["", "NULL", "null", "NA", "n/a", "N/A", "-", "  "]
TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\x00")
    | st.sampled_from([",", '"', "\n", "\r", " "]),
    min_size=1,
    max_size=12,
).filter(lambda s: not is_null(s))
INTEGER = st.integers(-(2**63), 2**63 - 1).map(str) | st.integers(0, 99).map(lambda n: f"+{n}")
NUMBER = st.decimals(min_value=-(10**9), max_value=10**9, places=4, allow_nan=False).map(str)
DATE = st.dates().map(lambda d: d.isoformat())
DATETIME = st.datetimes().map(
    lambda d: d.strftime("%Y-%m-%d %H:%M") if d.second == 0 else d.strftime("%Y-%m-%d %H:%M:%S")
)
ZERO_PADDED = st.integers(0, 99999).map(lambda n: f"0{n}")
KINDS: dict[str, st.SearchStrategy[str]] = {
    "integer": INTEGER,
    "number": NUMBER,
    "date": DATE,
    "datetime": DATETIME,
    "text": TEXT,
    "zero_padded": ZERO_PADDED,
}


def cells(values: st.SearchStrategy[str], n: int) -> st.SearchStrategy[list[str]]:
    return st.lists(values | st.sampled_from(NULLS), min_size=n, max_size=n)


@st.composite
def file_set(draw: st.DrawFn) -> list[UploadedFile]:
    n_rows = draw(st.integers(1, 8))
    text_ids = draw(st.booleans())
    id_strategy = ZERO_PADDED if text_ids else INTEGER
    ids = draw(st.lists(id_strategy, min_size=n_rows, max_size=n_rows, unique_by=_id_key))
    kinds = draw(st.lists(st.sampled_from(sorted(KINDS)), min_size=1, max_size=5))
    columns: dict[str, list[str]] = {"id": ids}
    for i, name in enumerate(kinds):
        values = draw(cells(KINDS[name], n_rows))
        if name == "text":
            values[0] = "a word"  # one plain word keeps a text column text
        columns[f"Col {i} {name}"] = values
    parents = _write("Parents.csv", columns, draw)

    n_children = draw(st.integers(1, 6))
    link_values = st.sampled_from(ids) | id_strategy | st.sampled_from(NULLS)
    children = {
        "id": [str(i) for i in range(1, n_children + 1)],
        "parent_id": draw(st.lists(link_values, min_size=n_children, max_size=n_children)),
        "note": draw(cells(TEXT, n_children)),
    }
    children["note"][0] = "a word"
    return [parents, _write("children.csv", children, draw)]


def _id_key(value: str) -> Any:
    """IDs that are equal once stored: zero-padded ones as text, others as numbers."""
    return value if len(value) > 1 and value.startswith("0") else int(value)


def _write(name: str, columns: dict[str, list[str]], draw: st.DrawFn) -> UploadedFile:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=draw(st.sampled_from(["\n", "\r\n"])))
    writer.writerow(list(columns))
    writer.writerows(zip(*columns.values(), strict=True))
    data = out.getvalue().encode("utf-8")
    if draw(st.booleans()):
        data = b"\xef\xbb\xbf" + data
    return UploadedFile(name, data)


def means(stored: Any, cell: str, ctype: str) -> bool:
    """Whether the stored value says exactly what the cell said, for the column type."""
    if is_null(cell):
        return stored is None
    if ctype == "integer":
        return type(stored) is int and stored == int(cell)
    if ctype == "number":
        return type(stored) is float and Decimal(repr(stored)) == Decimal(cell)
    if ctype == "datetime":
        return datetime.fromisoformat(stored) == datetime.fromisoformat(cell)
    return stored == cell


def assert_round_trip(files: list[UploadedFile], db: Path) -> None:
    result = check_files(files)
    assert result.ok, [p.text() for f in result.files for p in f.problems]
    load_tables(result.tables, db)
    conn = sqlite3.connect(db)
    try:
        for upload, plan in zip(files, result.tables, strict=True):
            raw = upload.data.decode("utf-8-sig")
            original = list(csv.reader(io.StringIO(raw, newline="")))[1:]
            names = ", ".join(f'"{c.name}"' for c in plan.columns)
            stored = conn.execute(f'SELECT {names} FROM "{plan.name}" ORDER BY rowid').fetchall()
            assert len(stored) == len(original)
            if plan.id_column is not None:
                # An INTEGER primary key is SQLite's rowid, so rows come back in ID order.
                at = [c.name for c in plan.columns].index(plan.id_column)
                key_type: ColumnType = plan.columns[at].type
                original.sort(key=lambda row: convert(row[at], key_type))
                stored.sort(key=lambda row: row[at])
            for row_stored, row_cells in zip(stored, original, strict=True):
                for value, cell, col in zip(row_stored, row_cells, plan.columns, strict=True):
                    assert means(value, cell, col.type), (plan.name, col.name, cell, value)
    finally:
        conn.close()


@settings(max_examples=150, deadline=None)
@given(file_set())
def test_everything_that_passes_check_loads_and_round_trips(
    tmp_path_factory: Any, files: list[UploadedFile]
) -> None:
    db = tmp_path_factory.mktemp("roundtrip") / "data.sqlite"
    assert_round_trip(files, db)


def test_generated_headers_slug_as_expected() -> None:
    assert slugify("Col 3 zero_padded") == "col_3_zero_padded"


def test_the_sample_dataset_round_trips(tmp_path: Path) -> None:
    files = [UploadedFile(p.name, p.read_bytes()) for p in sorted(SAMPLE.glob("*.csv"))]
    assert_round_trip(files, tmp_path / "data.sqlite")
