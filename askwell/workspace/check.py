"""Check: read a set of uploaded CSV files and report every problem with its fix.

Each problem names the file, the row (the header is row 1, as in a spreadsheet), the
column, what is wrong and the exact fix. A file shows at most `Limits.max_messages`
problems; the rest are counted. Errors block loading; warnings (a link value with no
match) do not.

When the whole set passes, the result carries a plan per table: column types, the ID
column, the links between tables and the rows. A link is a `<x>_id` column naming
another table; with `inferred_links` on, `<role>_<x>_id` and singular forms the plain
rule misses link too, when their values are that table's IDs (`_add_named_links`).
The loader stores exactly that plan, and Check has already run the loader's conversion
on every value.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from askwell.core.features import ALL, Features
from askwell.core.registry import slugify
from askwell.workspace.limits import Limits
from askwell.workspace.rules import (
    CLEAN_KINDS,
    DATE_KINDS,
    ColumnType,
    column_type,
    convert,
    date_fix,
    intended_type,
    is_iso_shaped,
    is_null,
    kind,
    number_fix,
)

Level = Literal["error", "warning"]
_BOM = b"\xef\xbb\xbf"
_CSV_SUFFIX = re.compile(r"\.csv$", re.IGNORECASE)
_LINK = re.compile(r"^(.+)_id$")
# A column that is at least this share ISO dates, and has this many values, is a date
# column with some typos rather than a text column.
_MOSTLY_DATES = 0.9
_MOSTLY_DATES_MIN = 10
_SHOWN_VALUE = 40
# The longest column name, after slugging, that Check accepts.
MAX_COLUMN_NAME = 128


@dataclass(frozen=True)
class Problem:
    level: Level
    code: str
    file: str
    row: int | None
    column: str | None
    message: str
    fix: str

    def text(self) -> str:
        where = [self.file]
        if self.row is not None:
            where.append(f"row {self.row}")
        if self.column is not None:
            where.append(f"column {self.column}")
        return f"{', '.join(where)}: {self.message}. Fix: {self.fix}."

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "code": self.code,
            "file": self.file,
            "row": self.row,
            "column": self.column,
            "message": self.message,
            "fix": self.fix,
            "text": self.text(),
        }


@dataclass(frozen=True)
class UploadedFile:
    name: str
    data: bytes


@dataclass(frozen=True)
class ColumnPlan:
    header: str
    name: str
    type: ColumnType


@dataclass(frozen=True)
class Link:
    column: str
    table: str
    target_column: str


@dataclass
class TablePlan:
    file: str
    name: str
    columns: list[ColumnPlan]
    id_column: str | None
    links: list[Link]
    rows: list[list[str | None]]


@dataclass
class FileReport:
    name: str
    table: str | None
    rows: int = 0
    columns: int = 0
    problems: list[Problem] = field(default_factory=list[Problem])
    more: int = 0
    errors: int = 0
    warnings: int = 0

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "table": self.table,
            "ok": self.ok,
            "rows": self.rows,
            "columns": self.columns,
            "errors": self.errors,
            "warnings": self.warnings,
            "problems": [p.to_dict() for p in self.problems],
            "more": self.more,
            "more_text": f"and {self.more} more like this" if self.more else None,
        }


@dataclass
class CheckResult:
    files: list[FileReport]
    tables: list[TablePlan]

    @property
    def ok(self) -> bool:
        return bool(self.files) and all(f.ok for f in self.files)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "files": [f.to_dict() for f in self.files]}


class _Reporter:
    """One file's problems, keeping the first `cap` and counting the rest."""

    def __init__(self, report: FileReport, cap: int) -> None:
        self.report = report
        self.cap = cap

    def add(
        self,
        level: Level,
        code: str,
        message: str,
        fix: str,
        *,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        if level == "error":
            self.report.errors += 1
        else:
            self.report.warnings += 1
        if len(self.report.problems) < self.cap:
            self.report.problems.append(
                Problem(level, code, self.report.name, row, column, message, fix)
            )
        else:
            self.report.more += 1


@dataclass
class _Parsed:
    report: FileReport
    out: _Reporter
    slug: str
    headers: list[str]
    names: list[str]
    rows: list[list[str | None]]
    row_numbers: list[int]
    types: list[ColumnType]
    # Link columns: their values are checked against the target table's ID type.
    link_columns: set[int] = field(default_factory=set[int])


def shown(value: str) -> str:
    """A cell value as quoted in a message, cut short."""
    if len(value) > _SHOWN_VALUE:
        value = value[:_SHOWN_VALUE] + "…"
    return repr(value)


def table_name(file_name: str) -> str:
    """The table a file becomes: its name without `.csv` (any case), slugged."""
    return slugify(_CSV_SUFFIX.sub("", file_name))


def id_column_candidates(table: str) -> list[str]:
    """The names an ID column may have, in order of preference."""
    names = ["id", f"{table}_id"]
    if table.endswith("s") and len(table) > 1:
        names.append(f"{table[:-1]}_id")
    return names


def check_files(
    files: list[UploadedFile], limits: Limits | None = None, features: Features = ALL
) -> CheckResult:
    limits = limits or Limits()
    parsed: list[_Parsed] = []
    reports: list[FileReport] = []
    for upload in files:
        report = FileReport(name=upload.name, table=table_name(upload.name))
        reports.append(report)
        result = _parse_file(upload, report, _Reporter(report, limits.max_messages), limits)
        if result is not None:
            parsed.append(result)
    _check_table_names(reports, limits)
    # Files that become the same table were reported above; they take no further part,
    # since every later step looks tables up by name.
    counts: dict[str, int] = {}
    for report in reports:
        if report.table is not None:
            counts[report.table] = counts.get(report.table, 0) + 1
    parsed = [p for p in parsed if counts.get(p.slug, 0) == 1]
    # ID and link checks need every table; a file that could not be read at all would
    # make them report problems that are not there. Without them, each column is still
    # typed and its damaged values reported.
    if len(parsed) == len(files):
        plans = _cross_file(parsed, features)
    else:
        tables = {r.table for r in reports if r.table is not None}
        id_index, links = _roles(parsed, tables, complete=False)
        _type_by_role(parsed, id_index, links)
        plans = []
    result = CheckResult(reports, plans)
    if not result.ok:
        result.tables = []
    return result


def _check_table_names(reports: list[FileReport], limits: Limits) -> None:
    by_slug: dict[str, list[FileReport]] = {}
    for report in reports:
        assert report.table is not None
        by_slug.setdefault(report.table, []).append(report)
    for slug, group in by_slug.items():
        out = [_Reporter(r, limits.max_messages) for r in group]
        if slug.startswith("sqlite_"):
            for reporter in out:
                reporter.add(
                    "error",
                    "reserved_name",
                    f"the table name {slug!r} is reserved by the database",
                    "rename the file so it does not start with sqlite_",
                )
        if len(group) > 1:
            names = ", ".join(r.name for r in group)
            for reporter in out:
                reporter.add(
                    "error",
                    "duplicate_table",
                    f"{names} become the same table, {slug!r}",
                    "give each file a different name (one table per file)",
                )


def _records(text: str) -> Iterator[list[str]]:
    return csv.reader(io.StringIO(text, newline=""), strict=True)


def _parse_file(
    upload: UploadedFile, report: FileReport, out: _Reporter, limits: Limits
) -> _Parsed | None:
    data = upload.data
    if len(data) > limits.max_file_bytes:
        out.add(
            "error",
            "file_too_large",
            f"the file is {len(data):,} bytes; the limit is {limits.max_file_bytes:,}",
            "split it into smaller files or remove columns you do not need",
        )
        return None
    if data.startswith(_BOM):
        data = data[len(_BOM) :]
    if not data.strip():
        out.add("error", "empty_file", "the file is empty", "export the table again")
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        out.add(
            "error",
            "not_utf8",
            "the file is not UTF-8 text",
            "save it as UTF-8 (in Excel: Save As, then CSV UTF-8)",
            row=data[: exc.start].count(b"\n") + 1,
        )
        return None
    first_line = text.split("\n", 1)[0]
    if "," not in first_line:
        for delimiter, label in ((";", "semicolons (;)"), ("\t", "tabs")):
            if delimiter in first_line:
                out.add(
                    "error",
                    "wrong_delimiter",
                    f"the columns are separated by {label}, not commas",
                    "save it with commas as the separator (in Excel: CSV UTF-8, comma delimited)",
                    row=1,
                )
                return None
    records = _records(text)
    row_number = 1
    try:
        header = next(records)
    except csv.Error as exc:
        out.add("error", "bad_quoting", f"the row could not be read ({exc})", _QUOTE_FIX, row=1)
        return None
    headers = [h.strip() for h in header]
    while len(headers) > 1 and not headers[-1]:
        headers.pop()  # trailing commas on every line, as some exports write
    if len(headers) > limits.max_columns:
        out.add(
            "error",
            "too_many_columns",
            f"the file has {len(headers)} columns; the limit is {limits.max_columns}",
            "remove columns you do not need, or split the table",
            row=1,
        )
        return None
    names = _check_header(headers, out, limits)
    if names is None:
        return None
    report.columns = len(headers)
    rows: list[list[str | None]] = []
    row_numbers: list[int] = []
    width = len(headers)
    try:
        for record in records:
            row_number += 1
            if not record:
                continue  # a blank line
            if len(record) > width and not any(record[width:]):
                record = record[:width]  # trailing commas
            if len(record) != width:
                out.add(
                    "error",
                    "ragged_row",
                    f"the row has {len(record)} values but there are {width} columns",
                    "give every row one value per column (leave a value blank, but keep "
                    "its comma); a comma inside a value needs quotes around the value",
                    row=row_number,
                )
                continue
            if len(rows) >= limits.max_rows:
                out.add(
                    "error",
                    "too_many_rows",
                    f"the file has more than {limits.max_rows:,} rows",
                    "split it into smaller files",
                    row=row_number,
                )
                break
            cells: list[str | None] = []
            for index, cell in enumerate(record):
                if len(cell) > limits.max_cell_chars:
                    out.add(
                        "error",
                        "cell_too_long",
                        f"the value is {len(cell):,} characters; the limit is "
                        f"{limits.max_cell_chars:,}",
                        "shorten the value",
                        row=row_number,
                        column=headers[index],
                    )
                    # Reported once, and never classified: the file cannot load anyway.
                    cells.append(None)
                    continue
                cells.append(None if is_null(cell) else cell)
            rows.append(cells)
            row_numbers.append(row_number)
    except csv.Error as exc:
        row_number += 1
        if "field larger than field limit" in str(exc):
            out.add(
                "error",
                "cell_too_long",
                f"a value is longer than {limits.max_cell_chars:,} characters",
                "shorten the value",
                row=row_number,
            )
        else:
            out.add(
                "error",
                "bad_quoting",
                f"the row could not be read ({exc})",
                _QUOTE_FIX,
                row=row_number,
            )
        return None
    report.rows = len(rows)
    if not rows and report.ok:
        out.add("error", "no_rows", "the file has column names but no rows", "add the rows")
        return None
    slug = report.table
    assert slug is not None
    types: list[ColumnType] = ["text"] * width
    return _Parsed(report, out, slug, headers, names, rows, row_numbers, types)


_QUOTE_FIX = (
    "put quotes around any value that holds a comma, a quote or a line break, and write "
    'a quote inside a quoted value as two quotes ("")'
)


def _check_header(headers: list[str], out: _Reporter, limits: Limits) -> list[str] | None:
    """The column names (slugged headers), or None after reporting a header problem.
    A header over the cell limit is reported and never classified. Name collisions are
    reported in the same Check as any other header problem, so one upload shows them all."""
    ok = True
    named: list[int] = []
    for index, header in enumerate(headers):
        if not header:
            out.add(
                "error",
                "blank_header",
                f"column {index + 1} has no name",
                "give every column a name in the first row",
                row=1,
            )
            ok = False
        elif len(header) > limits.max_cell_chars:
            out.add(
                "error",
                "header_too_long",
                f"the name of column {index + 1} is {len(header):,} characters; the limit is "
                f"{limits.max_cell_chars:,}",
                "give the column a short name",
                row=1,
            )
            ok = False
        else:
            named.append(index)
            if len(slugify(header)) > MAX_COLUMN_NAME:
                out.add(
                    "error",
                    "column_name_too_long",
                    f"the name of column {index + 1} is too long",
                    f"shorten it to at most {MAX_COLUMN_NAME} letters, digits and underscores",
                    row=1,
                )
                ok = False
    if ok and all(kind(h) != "text" for h in headers):
        out.add(
            "error",
            "no_header",
            "the first row holds values, not column names",
            "add a first row with a name for each column",
            row=1,
        )
        return None
    first: dict[str, str] = {}
    for index in named:
        header = headers[index]
        name = slugify(header)
        if name in first:
            out.add(
                "error",
                "duplicate_header",
                f"{first[name]!r} and {header!r} both become the column {name!r}",
                "give each column a different name",
                row=1,
                column=header,
            )
            ok = False
        else:
            first[name] = header
    return [slugify(h) for h in headers] if ok else None


def _column(
    header: str, values: list[str | None], row_numbers: list[int], out: _Reporter
) -> ColumnType:
    """A column's type, after reporting its damaged values."""
    kinds = {kind(v) for v in values if v is not None}
    meant = intended_type(kinds)
    if meant is not None:
        damaged = "bad_number" if meant == "number" else "bad_date"
        for value, row in zip(values, row_numbers, strict=True):
            if value is None or kind(value) != damaged:
                continue
            if meant == "number":
                message = f"{shown(value)} is not a plain number"
                fix = number_fix(value)
            elif is_iso_shaped(value):
                message = f"{shown(value)} is not a real date"
                fix = date_fix(value)
            else:
                message = f"{shown(value)} is not a date in the form YYYY-MM-DD"
                fix = date_fix(value)
            out.add("error", "bad_value", message, fix, row=row, column=header)
        # Text, so the conversion check does not report these values a second time.
        return "text"
    present = [v for v in values if v is not None]
    dates = sum(1 for v in present if kind(v) in DATE_KINDS)
    if len(present) >= _MOSTLY_DATES_MIN and dates < len(present) <= dates / _MOSTLY_DATES:
        for value, row in zip(values, row_numbers, strict=True):
            if value is not None and kind(value) not in DATE_KINDS:
                out.add(
                    "error",
                    "bad_value",
                    f"{shown(value)} is not a date, but the rest of the column is dates",
                    "use the form YYYY-MM-DD, or leave the value blank",
                    row=row,
                    column=header,
                )
        return "text"
    return column_type(kinds)


def _roles(
    parsed: list[_Parsed], tables: set[str], *, complete: bool
) -> tuple[dict[str, int], dict[str, list[tuple[int, str]]]]:
    """Each table's ID column, and its link columns with their target tables.

    A column named `<x>_id` links to table `<x>` or `<x>s`, but never to its own table:
    `<table>_id` and `<singular>_id` are that table's own ID names. With the whole set
    read (`complete`), a link needs a target with an ID column; otherwise any uploaded
    table counts, so a link to an unreadable file is still treated as a link."""
    id_index: dict[str, int] = {}
    for p in parsed:
        for candidate in id_column_candidates(p.slug):
            if candidate in p.names:
                id_index[p.slug] = p.names.index(candidate)
                break
    links: dict[str, list[tuple[int, str]]] = {}
    for p in parsed:
        own_names = set(id_column_candidates(p.slug))
        for index, name in enumerate(p.names):
            match = _LINK.match(name)
            if match is None or name in own_names:
                continue
            stem = match.group(1)
            target = next(
                (
                    t
                    for t in (stem, f"{stem}s")
                    if t in tables and t != p.slug and (t in id_index or not complete)
                ),
                None,
            )
            if target is not None:
                links.setdefault(p.slug, []).append((index, target))
    return id_index, links


MIN_DISTINCT_FOR_LINK = 10


def _plural_forms(table: str) -> set[str]:
    """The singular stems a table name answers to: `sites` -> site, `addresses` ->
    address, `companies` -> company, and the name itself."""
    forms = {table}
    if table.endswith("ies") and len(table) > 3:
        forms.add(table[:-3] + "y")
    if table.endswith("es") and len(table) > 2:
        forms.add(table[:-2])
    if table.endswith("s") and len(table) > 1:
        forms.add(table[:-1])
    return forms


def _add_named_links(
    parsed: list[_Parsed], id_index: dict[str, int], links: dict[str, list[tuple[int, str]]]
) -> None:
    """Links the `<x>_id` rule misses, kept only on evidence: a column named
    `<x>_id` or `<role>_<x>_id`, where `<x>` is a table's name or singular (the longest
    such table wins; two of one length give none), with at least
    MIN_DISTINCT_FOR_LINK distinct values, every one of them an ID in that table. A
    column that fails is left a plain column, never an error, so a set that loaded
    before still loads."""
    by_slug = {p.slug: p for p in parsed}
    for p in parsed:
        linked = {index for index, _ in links.get(p.slug, [])}
        own = id_index.get(p.slug)
        for index, name in enumerate(p.names):
            if index in linked or index == own or not name.endswith("_id"):
                continue
            stem = name.removesuffix("_id")
            matches: list[tuple[int, str]] = []
            for target, other in by_slug.items():
                if target == p.slug or target not in id_index:
                    continue
                for form in _plural_forms(target):
                    if stem == form or stem.endswith(f"_{form}"):
                        matches.append((len(form), other.slug))
            if not matches:
                continue
            longest = max(length for length, _ in matches)
            targets = sorted({slug for length, slug in matches if length == longest})
            if len(targets) != 1:
                continue
            target = targets[0]
            values = {str(v).strip() for r in p.rows if (v := r[index]) is not None}
            ids = {
                str(v).strip()
                for r in by_slug[target].rows
                if (v := r[id_index[target]]) is not None
            }
            if len(values) >= MIN_DISTINCT_FOR_LINK and values <= ids:
                links.setdefault(p.slug, []).append((index, target))


def _type_by_role(
    parsed: list[_Parsed], id_index: dict[str, int], links: dict[str, list[tuple[int, str]]]
) -> None:
    """Types, in dependency order. ID columns first: checked for damaged values like any
    column when the rest of the column is clean numbers or dates, and otherwise labels
    ('$5' is a fine ID). Then links: each takes its target ID's type before any of its
    values are judged (a link to an unreadable file is typed by its values, unjudged).
    Then every other column, by its own values."""
    by_slug = {p.slug: p for p in parsed}
    for p in parsed:
        index = id_index.get(p.slug)
        if index is not None:
            values = [r[index] for r in p.rows]
            if _has_clean_values(values):
                p.types[index] = _column(p.headers[index], values, p.row_numbers, p.out)
            else:
                p.types[index] = column_type({kind(v) for v in values if v is not None})
    for p in parsed:
        for index, target in links.get(p.slug, []):
            p.link_columns.add(index)
            if target in by_slug and target in id_index:
                p.types[index] = by_slug[target].types[id_index[target]]
            else:
                p.types[index] = column_type(
                    {kind(v) for r in p.rows if (v := r[index]) is not None}
                )
    for p in parsed:
        own = id_index.get(p.slug)
        _type_columns(p, skip=p.link_columns | ({own} if own is not None else set()))


def _has_clean_values(values: list[str | None]) -> bool:
    return any(v is not None and kind(v) in CLEAN_KINDS for v in values)


def _cross_file(parsed: list[_Parsed], features: Features = ALL) -> list[TablePlan]:
    """ID columns, links and link types across the whole set, then the plans."""
    by_slug = {p.slug: p for p in parsed}
    id_index, links = _roles(parsed, set(by_slug), complete=True)
    if "inferred_links" in features:
        _add_named_links(parsed, id_index, links)
    _type_by_role(parsed, id_index, links)

    id_values: dict[str, set[int | float | str]] = {}
    for p in parsed:
        index = id_index.get(p.slug)
        if index is None:
            if len(links.get(p.slug, [])) < 2:
                options = " or ".join(id_column_candidates(p.slug)[:2])
                p.out.add(
                    "error",
                    "no_id_column",
                    "the table has no ID column",
                    f"add a column named {options} with one unique value per row (a table "
                    "that only links two others, with two or more <table>_id columns, "
                    "needs no ID)",
                )
            continue
        id_values[p.slug] = _check_ids(p, index)

    for p in parsed:
        for index, target in links.get(p.slug, []):
            _check_link(p, index, target, p.types[index], id_values.get(target, set()))

    for p in parsed:
        _check_conversion(p)
    if not all(p.report.ok for p in parsed):
        return []
    plans: list[TablePlan] = []
    for p in parsed:
        own = id_index.get(p.slug)
        plans.append(
            TablePlan(
                file=p.report.name,
                name=p.slug,
                columns=[
                    ColumnPlan(h, n, t) for h, n, t in zip(p.headers, p.names, p.types, strict=True)
                ],
                id_column=p.names[own] if own is not None else None,
                links=[
                    Link(p.names[i], t, by_slug[t].names[id_index[t]])
                    for i, t in links.get(p.slug, [])
                ],
                rows=p.rows,
            )
        )
    return plans


def _type_columns(p: _Parsed, skip: set[int]) -> None:
    for index in range(len(p.names)):
        if index not in skip:
            values = [r[index] for r in p.rows]
            p.types[index] = _column(p.headers[index], values, p.row_numbers, p.out)


def _check_ids(p: _Parsed, index: int) -> set[int | float | str]:
    header = p.headers[index]
    seen: dict[int | float | str, int] = {}
    ctype = p.types[index]
    for row, cells in zip(p.row_numbers, p.rows, strict=True):
        value = cells[index]
        if value is None:
            p.out.add(
                "error",
                "blank_id",
                "the ID is blank",
                "give every row its own ID",
                row=row,
                column=header,
            )
            continue
        try:
            stored = convert(value, ctype)
        except ValueError:
            continue  # reported by the conversion check
        if stored in seen:
            p.out.add(
                "error",
                "duplicate_id",
                f"the ID {shown(value)} is also on row {seen[stored]}",
                "give every row its own ID",
                row=row,
                column=header,
            )
        else:
            seen[stored] = row
    return set(seen)


def _check_link(
    p: _Parsed,
    index: int,
    target: str,
    target_type: ColumnType,
    targets: set[int | float | str],
) -> None:
    header = p.headers[index]
    for row, cells in zip(p.row_numbers, p.rows, strict=True):
        value = cells[index]
        if value is None:
            continue
        try:
            stored = convert(value, target_type)
        except ValueError:
            p.out.add(
                "error",
                "link_type",
                f"{shown(value)} is not an ID like those in {target} ({_type_words(target_type)})",
                _link_fix(value, target_type),
                row=row,
                column=header,
            )
            continue
        if stored not in targets:
            p.out.add(
                "warning",
                "orphan_link",
                f"no row in {target} has the ID {shown(value)}",
                f"add that row to {target}, or correct or blank this value; questions that "
                "join the two tables will skip this row",
                row=row,
                column=header,
            )


def _type_words(ctype: ColumnType) -> str:
    return {
        "integer": "whole numbers",
        "number": "numbers",
        "date": "dates",
        "datetime": "dates and times",
        "text": "text",
    }[ctype]


def _link_fix(value: str, target_type: ColumnType) -> str:
    if target_type == "integer" and kind(value) == "zero_int":
        sign = "-" if value.startswith("-") else ""
        digits = value.lstrip("+-").lstrip("0") or "0"
        return f"write it without leading zeros: {sign if digits != '0' else ''}{digits}"
    return "use the ID exactly as it is written in the other table"


def _check_conversion(p: _Parsed) -> None:
    """Run the loader's conversion on every value, so a passing set always loads."""
    for index, ctype in enumerate(p.types):
        if index in p.link_columns:
            continue  # `_check_link` reported these with a link-specific fix
        for row, cells in zip(p.row_numbers, p.rows, strict=True):
            value = cells[index]
            if value is None:
                continue
            try:
                convert(value, ctype)
            except ValueError as exc:
                p.out.add(
                    "error",
                    "bad_value",
                    str(exc),
                    "use a value of the column's type, or leave it blank",
                    row=row,
                    column=p.headers[index],
                )
