"""Gold eval items: the schema of `evals/gold/*.jsonl` and a loader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

Category = Literal["in_schema", "out_of_schema", "should_refuse"]
Difficulty = Literal["easy", "medium", "hard"]
Feature = Literal["join", "group", "having", "date", "distinct", "order_limit"]

GOLD_DIR = Path(__file__).resolve().parent.parent / "evals" / "gold"


class GoldItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: Category
    difficulty: Difficulty
    features: list[Feature]
    question: str
    # in_schema: the reference query (Postgres dialect, dates relative to LEDGERLINE_NOW
    # written as literals). Refusal items: null, the gold answer is a refusal.
    gold_sql: str | None
    # True when row order is part of the answer (the gold has a meaningful ORDER BY).
    ordered: bool
    # Refusal items: why the right answer is a refusal. in_schema: null.
    refusal_reason: str | None

    @model_validator(mode="after")
    def _category_shape(self) -> Self:
        if self.category == "in_schema":
            if not self.gold_sql:
                raise ValueError(f"{self.id}: in_schema items need gold_sql")
            if self.refusal_reason is not None:
                raise ValueError(f"{self.id}: in_schema items have no refusal_reason")
            if self.ordered and "order by" not in self.gold_sql.lower():
                raise ValueError(f"{self.id}: ordered items need an ORDER BY")
        else:
            if self.gold_sql is not None:
                raise ValueError(f"{self.id}: refusal items have gold_sql null")
            if not self.refusal_reason:
                raise ValueError(f"{self.id}: refusal items need a refusal_reason")
            if self.ordered or self.features:
                raise ValueError(f"{self.id}: refusal items are unordered with no features")
        if len(set(self.features)) != len(self.features):
            raise ValueError(f"{self.id}: duplicate features")
        return self


def load_gold(path: Path | str) -> list[GoldItem]:
    items: list[GoldItem] = []
    with Path(path).open(encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                items.append(GoldItem.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate item ids")
    return items
