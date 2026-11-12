"""Eval items: the frozen fieldservice gold set and the pre-registered Spider questions.

Spider question text and SQL are read from the fetched dev.json at run time (they are
CC BY-SA and never committed). Every Spider item is answerable (`in_schema`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from askwell.gold import GOLD_DIR, load_gold

ROOT = Path(__file__).resolve().parents[2]
SPIDER_DIR = ROOT / "data" / "spider" / "spider_data"
SPIDER_IDS = GOLD_DIR / "spider_ids.json"


@dataclass(frozen=True)
class EvalItem:
    id: str
    schema_id: str
    category: str  # in_schema | out_of_schema | should_refuse
    question: str
    gold_sql: str | None
    ordered: bool
    difficulty: str
    gold: str = ""  # the gold file's name, carried into every record and report row


DEFAULT_GOLD = "fieldservice.jsonl"
SPIDER_GOLD = "spider_ids.json"


def default_gold(schema_id: str) -> str:
    return SPIDER_GOLD if schema_id.startswith("spider_") else DEFAULT_GOLD


def fieldservice_items(path: Path | None = None) -> list[EvalItem]:
    source = path or GOLD_DIR / DEFAULT_GOLD
    return [
        EvalItem(
            id=item.id,
            schema_id="fieldservice",
            category=item.category,
            question=item.question,
            gold_sql=item.gold_sql,
            ordered=item.ordered,
            difficulty=item.difficulty,
            gold=source.name,
        )
        for item in load_gold(source)
    ]


def spider_databases() -> list[str]:
    return [db["db_id"] for db in json.loads(SPIDER_IDS.read_text())["databases"]]


def spider_items(db_id: str) -> list[EvalItem]:
    from evals.gold.spider_selection import spider_hardness

    selection = json.loads(SPIDER_IDS.read_text())
    entry = next((db for db in selection["databases"] if db["db_id"] == db_id), None)
    if entry is None:
        raise ValueError(f"{db_id} is not a pre-registered Spider database")
    dev_json = SPIDER_DIR / "dev.json"
    if not dev_json.exists():
        raise FileNotFoundError(f"{dev_json}: run `uv run python -m scripts.fetch_benchmarks`")
    dev = json.loads(dev_json.read_text())
    items: list[EvalItem] = []
    for index in entry["ids"]:
        example = dev[index]
        if example["db_id"] != db_id:
            raise ValueError(f"dev.json[{index}] is not from {db_id}: wrong dev.json?")
        query = str(example["query"])
        items.append(
            EvalItem(
                id=f"spider:{index}",
                schema_id=f"spider_{db_id}",
                category="in_schema",
                question=str(example["question"]),
                gold_sql=query,
                ordered="order by" in query.lower(),
                difficulty=spider_hardness(example["sql"]),
                gold=SPIDER_GOLD,
            )
        )
    return items
