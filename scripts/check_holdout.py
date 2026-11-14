"""Check a new held-out gold file before its hash is committed.

    uv run python -m scripts.check_holdout <file.jsonl>

The orchestrator runs this, never the writer and never a builder: the overlap check
reads the seen questions, which the writer must not see. Exit 1 on any problem.

Checks:
- every line is a valid gold item, ids are unique, and the category counts are as
  ordered (`--counts`);
- every in_schema gold runs twice as the read-only role and returns the same non-empty
  result;
- the tie rule: an ordered gold's ORDER BY lists only output columns, no two returned rows
  tie on all of them, and with its LIMIT raised by one the next row does not tie with the
  last one returned. The ORDER BY holds only the ordering the question asks for, so a tie
  on it means the question has no single answer;
- no question shares a run of 6 words with any seen question (the same measure as
  tests/test_no_tuning.py);
- no two in_schema items share their gold SQL (compared with case and spacing
  normalised).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from askwell.bench.compare import TOLERANCE
from askwell.bench.systems import raw_sql
from askwell.config import get_settings
from askwell.core.executor import readonly_engine, run
from askwell.gold import GoldItem

ROOT = Path(__file__).resolve().parent.parent
SEEN = (
    ROOT / "evals" / "gold" / "fieldservice.jsonl",
    ROOT / "evals" / "gold" / "holdout-v02.jsonl",
)
RUN = 6
DEFAULT_COUNTS = {"in_schema": 96, "out_of_schema": 12, "should_refuse": 12}

Runner = Callable[[str], tuple[list[str], list[tuple[Any, ...]]]]


@dataclass(frozen=True)
class Problem:
    item_id: str
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.item_id}: {self.check}: {self.detail}"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def word_runs(text: str, size: int = RUN) -> set[str]:
    words = _words(text)
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _top_level(sql: str) -> list[tuple[int, str]]:
    """(position, character) for every character outside parentheses and quotes."""
    out: list[tuple[int, str]] = []
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(sql):
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            out.append((i, ch))
    return out


def _top_level_text(sql: str) -> str:
    """The SQL with everything inside parentheses and quotes blanked to spaces, so
    keyword searches only see the outer query, at the same positions."""
    chars = [" "] * len(sql)
    for i, ch in _top_level(sql):
        chars[i] = ch
    return "".join(chars)


_ORDER = re.compile(r"\border\s+by\b", re.IGNORECASE)
_END = re.compile(r"\b(limit|offset|fetch)\b|;", re.IGNORECASE)
_LIMIT = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)
_DIRECTION = re.compile(r"\s+(asc|desc)?(\s+nulls\s+(first|last))?\s*$", re.IGNORECASE)


def order_items(sql: str) -> list[str]:
    """The outer query's ORDER BY items, without ASC/DESC or NULLS FIRST/LAST."""
    outer = _top_level_text(sql)
    matches = list(_ORDER.finditer(outer))
    if not matches:
        return []
    start = matches[-1].end()
    end_match = _END.search(outer, start)
    end = end_match.start() if end_match else len(sql)
    items: list[str] = []
    cut = start
    for i in range(start, end):
        if outer[i] == ",":
            items.append(sql[cut:i])
            cut = i + 1
    items.append(sql[cut:end])
    return [_DIRECTION.sub("", " " + item).strip() for item in items if item.strip()]


def outer_limit(sql: str) -> int | None:
    match = _LIMIT.search(_top_level_text(sql))
    return int(match.group(1)) if match else None


def with_limit(sql: str, limit: int) -> str:
    match = _LIMIT.search(_top_level_text(sql))
    if match is None:
        raise ValueError("no outer LIMIT")
    return sql[: match.start(1)] + str(limit) + sql[match.end(1) :]


def key_columns(items: Sequence[str], columns: Sequence[str]) -> list[int] | str:
    """Each ORDER BY item as an output column index, or the first item that is not one.

    An item matches an output column by name, by `table.column` whose column is an
    output name, or by its 1-based position."""
    lowered = [c.lower() for c in columns]
    out: list[int] = []
    for item in items:
        name = item.strip().strip('"').lower()
        if name.isdigit() and 1 <= int(name) <= len(columns):
            out.append(int(name) - 1)
            continue
        bare = name.rsplit(".", 1)[-1].strip('"')
        if name in lowered:
            out.append(lowered.index(name))
        elif bare in lowered:
            out.append(lowered.index(bare))
        else:
            return item
    return out


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= TOLERANCE
    try:
        return abs(float(a) - float(b)) <= TOLERANCE  # Decimal from Postgres
    except (TypeError, ValueError):
        return a == b


def _ties(row_a: Sequence[Any], row_b: Sequence[Any], keys: Sequence[int]) -> bool:
    return all(_same(row_a[k], row_b[k]) for k in keys)


def _normalised_sql(sql: str) -> str:
    return " ".join(sql.lower().replace(";", " ").split())


def check_items(
    items: Sequence[GoldItem],
    runner: Runner,
    seen_questions: Sequence[str],
    counts: dict[str, int] | None = None,
) -> list[Problem]:
    problems: list[Problem] = []
    ids = [item.id for item in items]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(Problem(duplicate, "ids", "duplicate id"))
    if counts is not None:
        for category, wanted in counts.items():
            got = sum(item.category == category for item in items)
            if got != wanted:
                problems.append(Problem("*", "counts", f"{category}: {got}, wanted {wanted}"))

    seen_runs: dict[str, str] = {}
    for question in seen_questions:
        for words in word_runs(question):
            seen_runs.setdefault(words, question)
    for item in items:
        shared = sorted(word_runs(item.question) & seen_runs.keys())
        if shared:
            problems.append(
                Problem(item.id, "overlap", f"shares {shared[0]!r} with a seen question")
            )

    by_sql: dict[str, str] = {}
    for item in items:
        if item.gold_sql is None:
            continue
        key = _normalised_sql(item.gold_sql)
        if key in by_sql:
            problems.append(Problem(item.id, "duplicate_sql", f"same gold SQL as {by_sql[key]}"))
        else:
            by_sql[key] = item.id

    for item in items:
        if item.category == "in_schema" and item.gold_sql is not None:
            problems.extend(_check_sql(item, item.gold_sql, runner))
    return problems


def _check_sql(item: GoldItem, sql: str, runner: Runner) -> list[Problem]:
    try:
        columns, first = runner(sql)
        _, second = runner(sql)
    except Exception as exc:  # whatever stops a gold from running is the finding
        return [Problem(item.id, "runs", f"does not run: {exc}")]
    if not first:
        return [Problem(item.id, "runs", "returns no rows")]
    if first != second:
        return [Problem(item.id, "runs", "two runs differ")]
    if not item.ordered:
        return []

    keys = key_columns(order_items(sql), columns)
    if isinstance(keys, str):
        return [Problem(item.id, "ties", f"ORDER BY item {keys!r} is not an output column")]
    if not keys:
        return [Problem(item.id, "ties", "ordered but no outer ORDER BY")]
    for above, below in pairwise(first):
        if _ties(above, below, keys):
            return [Problem(item.id, "ties", f"returned rows tie on the ordering: {above!r}")]
    limit = outer_limit(sql)
    if limit is not None and len(first) == limit:
        try:
            _, extended = runner(with_limit(sql, limit + 1))
        except Exception as exc:
            return [Problem(item.id, "ties", f"LIMIT {limit + 1} does not run: {exc}")]
        if len(extended) > limit and _ties(extended[limit - 1], extended[limit], keys):
            return [Problem(item.id, "ties", f"the row after LIMIT {limit} ties with the last")]
    return []


def _load(path: Path) -> list[GoldItem]:
    items: list[GoldItem] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                items.append(GoldItem.model_validate_json(line))
            except ValueError as exc:
                raise SystemExit(f"{path}:{number}: {exc}") from exc
    return items


def _seen_questions(paths: Sequence[Path]) -> list[str]:
    return [item.question for path in paths for item in _load(path)]


def database_runner(url: str) -> Runner:
    engine = readonly_engine(url)

    def runner(sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        result = run(engine, raw_sql(sql), untrusted=True)
        return list(result.columns), [tuple(row) for row in result.rows]

    return runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a new held-out gold file.")
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--counts",
        default="96,12,12",
        help="in_schema,out_of_schema,should_refuse (default 96,12,12)",
    )
    args = parser.parse_args(argv)
    wanted = [int(n) for n in args.counts.split(",")]
    counts = dict(zip(DEFAULT_COUNTS, wanted, strict=True))
    items = _load(args.file)
    runner = database_runner(get_settings().database_ro_url)
    problems = check_items(items, runner, _seen_questions(SEEN), counts)
    for problem in problems:
        print(problem)
    ties = sum(p.check == "ties" for p in problems)
    print(f"{len(items)} items, {len(problems)} problems ({ties} under the tie rule)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
