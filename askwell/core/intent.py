"""The structured intent the model fills in. It never contains SQL.

Field references are `entity.field` registry slugs (or a bare `field` on the base
entity). Relative dates are tokens; code resolves them against `ASKWELL_NOW`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IntentType = Literal["summary", "grouped_summary", "row_list", "date_series", "unanswerable"]
Aggregate = Literal["count", "count_distinct", "sum", "avg", "min", "max", "ratio"]
FilterOp = Literal[
    "eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "is_null", "ilike_contains"
]
HavingOp = Literal["eq", "neq", "gt", "gte", "lt", "lte", "between"]
Grain = Literal["day", "iso_week", "month", "quarter", "year"]
RelativeToken = Literal[
    "today",
    "yesterday",
    "last_n_days",
    "last_n_weeks",
    "last_n_months",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "this_year",
    "ytd",
    "last_year",
]
Scalar = str | int | float | bool

COMPARISON_OPS: frozenset[str] = frozenset({"eq", "neq", "gt", "gte", "lt", "lte"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Computed(_Strict):
    """A value computed row by row from two numeric fields (feature `computed`)."""

    op: Literal["multiply", "subtract", "add"]
    left: str
    right: str
    alias: str | None = None


class DaysBetween(_Strict):
    """Days from the first date field to the second, with fractions (feature
    `durations`). The second may be "now", the reference time."""

    days_between: list[str]
    alias: str | None = None


# Where a numeric field is read: a field reference, or a value computed from fields.
FieldExpr = str | Computed | DaysBetween


class AggregateOf(_Strict):
    """A filter value that is an aggregate of the filtered field itself, over the rows the
    question selects (feature `vs_aggregate`): "longer than average"."""

    of: Literal["avg", "min", "max"]


class Condition(_Strict):
    """One predicate. Exactly one operand form applies per operator:
    `value` (eq..lte, ilike_contains, is_null as true/false), `values` (in; between as
    [low, high]) or `other_field` (eq..lte against another column)."""

    field: FieldExpr
    op: FilterOp
    value: Scalar | AggregateOf | None = None
    values: list[Scalar] | None = None
    other_field: str | None = None


class FilterGroup(_Strict):
    """A one-level group of conditions. Groups never nest."""

    any_of: list[Condition] | None = None
    all_of: list[Condition] | None = None


class HasFilter(_Strict):
    """Keeps the rows that have (or, with `none`, have no) related rows of `has`, an
    entity whose rows each point at one of these (feature `has`). `where` narrows
    which related rows count; its fields are read from `has`."""

    has: str
    where: list[Condition] = Field(default_factory=list[Condition])
    none: bool = False


class Metric(_Strict):
    """`where` makes it conditional: counted or summed only over the rows that match.
    A `ratio` takes only `numerator` and `denominator` (labels of other metrics in the
    same intent) and `as_percent`."""

    agg: Aggregate
    field: FieldExpr | None = None  # None only for count (count of rows) and ratio
    distinct: bool = False
    alias: str | None = None
    where: list[Condition] = Field(default_factory=list[Condition])
    numerator: str | None = None
    denominator: str | None = None
    as_percent: bool = False


class Having(_Strict):
    metric: str  # a metric alias
    op: HavingOp
    value: float | None = None
    values: list[float] | None = None


class GroupBy(_Strict):
    field: str
    grain: Grain | None = None


class DateRange(_Strict):
    """In a date_series, `field` is left out: the period applies to each series by its
    own date field. Every other intent needs it."""

    field: str | None = None
    relative: RelativeToken | None = None
    n: int | None = None
    start: str | None = None  # ISO date or datetime, inclusive
    end: str | None = None  # ISO date or datetime, exclusive


class Series(_Strict):
    """One column of a date_series: `metric` counted or summed by its own `date_field`,
    over the rows that match the shared filters and its own `where`."""

    metric: Metric
    date_field: str
    where: list[Condition] = Field(default_factory=list[Condition])
    alias: str | None = None


class OrderBy(_Strict):
    target: str  # a field reference or a metric alias
    direction: Literal["asc", "desc"] = "asc"


class Intent(_Strict):
    intent_type: IntentType
    entity: str | None = None
    select: list[FieldExpr] = Field(default_factory=list[FieldExpr])
    metrics: list[Metric] = Field(default_factory=list[Metric])
    filters: list[Condition | FilterGroup | HasFilter] = Field(
        default_factory=list[Condition | FilterGroup | HasFilter]
    )
    having: list[Having] = Field(default_factory=list[Having])
    group_by: list[GroupBy] = Field(default_factory=list[GroupBy])
    date_range: DateRange | None = None
    order_by: list[OrderBy] = Field(default_factory=list[OrderBy])
    limit: int | None = None
    grain: Grain | None = None  # date_series only
    series: list[Series] = Field(default_factory=list[Series])  # date_series only
    unanswerable_reason: str | None = None
