"""The SQL builder: a validated `QueryPlan` to a SQLAlchemy Core `Select`.

SQLAlchemy Core only. Identifiers come from the registry (via the plan) and are quoted
by SQLAlchemy; every value is a bound parameter. Joins follow many-to-one edges only
(the validator guarantees it). Calendar grains compile per dialect and return the
period's first day as a DATE on every engine.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Date,
    DateTime,
    FromClause,
    Integer,
    Numeric,
    Select,
    String,
    and_,
    bindparam,
    column,
    func,
    or_,
    select,
    table,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import NullType, TypeDecorator

from ledgerline.core.validate import (
    PlanMetric,
    Predicate,
    PredicateGroup,
    QueryPlan,
    ResolvedField,
)


class _Lenient(TypeDecorator[Any]):
    """A DATE or DATETIME that reads values it cannot parse as they are stored.

    A column's declared type is not a promise about its contents: Spider's wta_1 stores
    birth dates as integers such as 19800930. Strict parsing would crash the whole
    query; this returns 19800930 unchanged and still parses real dates."""

    cache_ok = True

    def result_processor(self, dialect: Dialect, coltype: object) -> Any:
        strict = self.impl_instance.result_processor(dialect, coltype)
        if strict is None:
            return None

        def process(value: Any) -> Any:
            try:
                return strict(value)
            except (TypeError, ValueError):
                return value

        return process


class LenientDate(_Lenient):
    impl = Date
    cache_ok = True


class LenientDateTime(_Lenient):
    impl = DateTime
    cache_ok = True


_TYPES: dict[str, TypeEngine[Any]] = {
    "integer": Integer(),
    "number": Numeric(asdecimal=False),
    "text": String(),
    "boolean": Boolean(),
    "date": LenientDate(),
    "datetime": LenientDateTime(),
}


# --- calendar grains ---


class _Grain(FunctionElement[Any]):
    type = Date()
    inherit_cache = True
    grain = ""


class GrainDay(_Grain):
    name = "grain_day"
    grain = "day"
    inherit_cache = True


class GrainIsoWeek(_Grain):
    name = "grain_iso_week"
    grain = "iso_week"
    inherit_cache = True


class GrainMonth(_Grain):
    name = "grain_month"
    grain = "month"
    inherit_cache = True


class GrainQuarter(_Grain):
    name = "grain_quarter"
    grain = "quarter"
    inherit_cache = True


class GrainYear(_Grain):
    name = "grain_year"
    grain = "year"
    inherit_cache = True


GRAINS: dict[str, type[_Grain]] = {
    "day": GrainDay,
    "iso_week": GrainIsoWeek,
    "month": GrainMonth,
    "quarter": GrainQuarter,
    "year": GrainYear,
}

# Postgres: date_trunc's 'week' is the ISO week (Monday start).
_PG_UNITS = {"iso_week": "week", "month": "month", "quarter": "quarter", "year": "year"}


@compiles(_Grain, "postgresql")
def _grain_pg(element: _Grain, compiler: SQLCompiler, **kw: Any) -> str:
    expr = compiler.process(element.clauses, **kw)
    if element.grain == "day":
        return f"CAST({expr} AS DATE)"
    return f"CAST(date_trunc('{_PG_UNITS[element.grain]}', {expr}) AS DATE)"


@compiles(_Grain, "sqlite")
def _grain_sqlite(element: _Grain, compiler: SQLCompiler, **kw: Any) -> str:
    expr = compiler.process(element.clauses, **kw)
    if element.grain == "day":
        return f"date({expr})"
    if element.grain == "iso_week":
        # 'weekday 0' moves forward to Sunday (or stays); 6 days back is that ISO Monday.
        return f"date({expr}, 'weekday 0', '-6 days')"
    if element.grain == "month":
        return f"date({expr}, 'start of month')"
    if element.grain == "quarter":
        back = f"((CAST(strftime('%m', {expr}) AS INTEGER) - 1) % 3)"
        return f"date({expr}, 'start of month', '-' || {back} || ' months')"
    return f"date({expr}, 'start of year')"


@compiles(_Grain)
def _grain_other(element: _Grain, compiler: SQLCompiler, **kw: Any) -> str:
    raise CompileError(f"calendar grains are not implemented for {compiler.dialect.name}")


class AsDatetime(FunctionElement[Any]):
    """An operand normalised to a datetime: CAST AS TIMESTAMP on Postgres; on SQLite,
    one text format with microseconds ('YYYY-MM-DD HH:MM:SS.ffffff'), whatever format
    the stored DATE or DATETIME text uses. A fraction followed by a UTC offset is not
    supported on SQLite (SQLAlchemy never writes one)."""

    type = DateTime()
    name = "as_datetime"
    inherit_cache = True


@compiles(AsDatetime, "postgresql")
def _as_datetime_pg(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    return f"CAST({compiler.process(element.clauses, **kw)} AS TIMESTAMP)"


@compiles(AsDatetime, "sqlite")
def _as_datetime_sqlite(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    # 'YYYY-MM-DD HH:MM:SS' from any date/datetime text, then the stored fraction padded
    # to six digits (strftime's %f stops at milliseconds). A DATE gets '.000000'.
    x = compiler.process(element.clauses, **kw)
    fraction = (
        f"CASE WHEN instr({x}, '.') > 0 "
        f"THEN substr(substr({x}, instr({x}, '.') + 1) || '000000', 1, 6) "
        "ELSE '000000' END"
    )
    return f"(strftime('%Y-%m-%d %H:%M:%S', {x}) || '.' || {fraction})"


@compiles(AsDatetime)
def _as_datetime_other(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    raise CompileError(f"datetime normalisation is not implemented for {compiler.dialect.name}")


# --- building ---


class _Tables:
    def __init__(self, plan: QueryPlan) -> None:
        columns: dict[str, dict[str, TypeEngine[Any]]] = {plan.base_alias: {}}
        names: dict[str, tuple[str, str | None]] = {
            plan.base_alias: (plan.base_table, plan.base_schema)
        }
        for join in plan.joins:
            names[join.alias] = (join.table, join.db_schema)
            columns.setdefault(join.parent_alias, {}).setdefault(join.parent_column, NullType())
            columns.setdefault(join.alias, {}).setdefault(join.column, NullType())
        for rfield in _fields(plan):
            columns.setdefault(rfield.alias, {})[rfield.column] = _TYPES[rfield.type]
        self.tables: dict[str, FromClause] = {}
        for alias, (name, schema) in names.items():
            cols = [column(c, t) for c, t in sorted(columns.get(alias, {}).items())]
            self.tables[alias] = table(name, *cols, schema=schema).alias(alias)

    def col(self, rfield: ResolvedField) -> ColumnElement[Any]:
        return self.tables[rfield.alias].c[rfield.column]


def _fields(plan: QueryPlan) -> list[ResolvedField]:
    out: list[ResolvedField] = list(plan.select)
    out += [m.field for m in plan.metrics if m.field is not None]
    out += [g.field for g in plan.group_by]
    out += [o.field for o in plan.order_by if o.field is not None]
    for item in plan.where:
        predicates = item.predicates if isinstance(item, PredicateGroup) else (item,)
        for predicate in predicates:
            out.append(predicate.field)
            if predicate.other is not None:
                out.append(predicate.other)
    return out


def _bind(value: Any, col: ColumnElement[Any]) -> ColumnElement[Any]:
    """A bound parameter typed like its column. Passing a bare Python value lets
    SQLAlchemy render some values (booleans) as SQL literals; this never does."""
    return bindparam(None, value, type_=col.type)


def _comparison_operands(
    tables: _Tables, predicate: Predicate
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    col = tables.col(predicate.field)
    assert predicate.other is not None
    other = tables.col(predicate.other)
    if {predicate.field.type, predicate.other.type} == {"date", "datetime"}:
        # A DATE against a DATETIME: compare both as datetimes (a DATE is its midnight).
        return AsDatetime(col), AsDatetime(other)
    return col, other


def _predicate(tables: _Tables, predicate: Predicate) -> ColumnElement[bool]:
    op = predicate.op
    if predicate.other is not None:
        col, rhs = _comparison_operands(tables, predicate)
    else:
        col = tables.col(predicate.field)
        single = op in ("eq", "neq", "gt", "gte", "lt", "lte")
        rhs = _bind(predicate.values[0], col) if single else None
    if op == "eq":
        return col == rhs
    if op == "neq":
        return col != rhs
    if op == "gt":
        return col > rhs
    if op == "gte":
        return col >= rhs
    if op == "lt":
        return col < rhs
    if op == "lte":
        return col <= rhs
    if op == "between":
        return col.between(_bind(predicate.values[0], col), _bind(predicate.values[1], col))
    if op == "in":
        return col.in_([_bind(v, col) for v in predicate.values])
    if op == "is_null":
        return col.is_(None) if predicate.values[0] else col.is_not(None)
    if op == "ilike_contains":
        return col.icontains(predicate.values[0], autoescape=True)
    raise ValueError(f"unknown operator {op!r}")


def _metric(tables: _Tables, metric: PlanMetric) -> ColumnElement[Any]:
    if metric.field is None:
        return func.count()
    col = tables.col(metric.field)
    arg = col.distinct() if metric.distinct else col
    if metric.agg in ("count", "count_distinct"):
        return func.count(arg)
    return getattr(func, metric.agg)(arg)


def _threshold(value: float) -> ColumnElement[Any]:
    """A HAVING threshold, bound as NUMERIC whatever the aggregate's type: binding it
    with count()'s INTEGER type would cast 1.5 to 2 on Postgres."""
    return bindparam(None, value, type_=Numeric(asdecimal=False))


def _compare(expr: ColumnElement[Any], op: str, values: tuple[float, ...]) -> ColumnElement[bool]:
    if op == "between":
        return expr.between(_threshold(values[0]), _threshold(values[1]))
    value = _threshold(values[0])
    comparisons = {
        "eq": expr == value,
        "neq": expr != value,
        "gt": expr > value,
        "gte": expr >= value,
        "lt": expr < value,
        "lte": expr <= value,
    }
    return comparisons[op]


def _label(labelled: dict[str, ColumnElement[Any]], label: str, expr: ColumnElement[Any]) -> None:
    if label in labelled:
        # The validator rejects this (alias_collision); never let one label shadow another.
        raise ValueError(f"duplicate output label {label!r}")
    labelled[label] = expr


def build(plan: QueryPlan) -> Select[Any]:
    tables = _Tables(plan)
    source = tables.tables[plan.base_alias]
    for join in plan.joins:
        parent = tables.tables[join.parent_alias]
        child = tables.tables[join.alias]
        source = source.join(child, parent.c[join.parent_column] == child.c[join.column])

    labelled: dict[str, ColumnElement[Any]] = {}
    group_exprs: list[ColumnElement[Any]] = []
    columns: list[ColumnElement[Any]] = []
    if plan.intent_type == "row_list":
        columns = [tables.col(f).label(f.label) for f in plan.select]
    else:
        for group in plan.group_by:
            expr = tables.col(group.field)
            if group.grain is not None:
                expr = GRAINS[group.grain](expr)
            group_exprs.append(expr)
            columns.append(expr.label(group.label))
            _label(labelled, group.label, expr)
        for metric in plan.metrics:
            expr = _metric(tables, metric)
            columns.append(expr.label(metric.label))
            _label(labelled, metric.label, expr)

    stmt = select(*columns).select_from(source)
    conditions: list[ColumnElement[bool]] = []
    for item in plan.where:
        if isinstance(item, PredicateGroup):
            parts = [_predicate(tables, p) for p in item.predicates]
            conditions.append(or_(*parts) if item.mode == "any_of" else and_(*parts))
        else:
            conditions.append(_predicate(tables, item))
    if conditions:
        stmt = stmt.where(and_(*conditions))
    if group_exprs:
        stmt = stmt.group_by(*group_exprs)
    if plan.having:
        stmt = stmt.having(
            and_(*[_compare(labelled[h.metric], h.op, h.values) for h in plan.having])
        )
    order: list[ColumnElement[Any]] = []
    for item in plan.order_by:
        expr = tables.col(item.field) if item.field is not None else labelled[item.label or ""]
        order.append(expr.desc() if item.direction == "desc" else expr.asc())
    if order:
        stmt = stmt.order_by(*order)
    if plan.limit is not None:
        stmt = stmt.limit(plan.limit)
    return stmt


def dialect_for(name: str) -> Dialect:
    if name == "postgresql":
        return postgresql.psycopg.dialect()  # type: ignore[no-any-return]
    if name == "sqlite":
        return sqlite.pysqlite.dialect()  # type: ignore[no-any-return]
    raise ValueError(f"unsupported dialect {name!r}")


def compile_sql(stmt: Select[Any], dialect_name: str) -> tuple[str, dict[str, Any]]:
    """The SQL text (placeholders only) and its bound parameters."""
    compiled = stmt.compile(
        dialect=dialect_for(dialect_name), compile_kwargs={"render_postcompile": True}
    )
    return str(compiled), dict(compiled.params)
