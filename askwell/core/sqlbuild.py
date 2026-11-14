"""The SQL builder: a validated `QueryPlan` to a SQLAlchemy Core `Select`.

SQLAlchemy Core only. Identifiers come from the registry (via the plan) and are quoted
by SQLAlchemy; every value is a bound parameter. Joins follow many-to-one edges only
(the validator guarantees it). Calendar grains compile per dialect and return the
period's first day as a DATE on every engine.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CTE,
    BigInteger,
    Boolean,
    ColumnElement,
    Date,
    DateTime,
    Float,
    FromClause,
    Numeric,
    Select,
    String,
    and_,
    bindparam,
    case,
    cast,
    column,
    func,
    literal_column,
    or_,
    select,
    table,
    union,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import NullType, TypeDecorator

from askwell.core.registry import TEXT_NUMBER_PLACEHOLDERS
from askwell.core.validate import (
    PERIOD_LABEL,
    PlanMetric,
    PlanSeries,
    Predicate,
    PredicateGroup,
    QueryPlan,
    ResolvedField,
)


class _Lenient(TypeDecorator[Any]):
    """A DATE or DATETIME that reads values it cannot parse as they are stored.

    A column's declared type is not a promise about its contents: a DATE column can hold
    integers such as 20010203 (some Spider databases store dates that way). Strict parsing
    would crash the whole query; this returns 20010203 unchanged and still parses real
    dates."""

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
    # BIGINT for every integer field: binding a 64-bit id as INTEGER would narrow it to
    # 32 bits on Postgres. Comparing an INTEGER column with a BIGINT value is exact.
    "integer": BigInteger(),
    "number": Numeric(asdecimal=False),
    "text": String(),
    "boolean": Boolean(),
    "date": LenientDate(),
    "datetime": LenientDateTime(),
}


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
    one text format with microseconds, whatever format the stored DATE or DATETIME text
    uses."""

    type = DateTime()
    name = "as_datetime"
    inherit_cache = True


@compiles(AsDatetime, "postgresql")
def _as_datetime_pg(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    return f"CAST({compiler.process(element.clauses, **kw)} AS TIMESTAMP)"


def _sqlite_canonical_datetime(x: str) -> str:
    """SQLite text for `x` as 'YYYY-MM-DD HH:MM:SS.ffffff' in UTC, whatever format it was
    stored in: a space or 'T', with or without a fraction, a 'Z' or a +HH:MM offset, or a
    plain DATE. strftime converts the offset to UTC, but its %f stops at milliseconds, so
    the stored fraction (without any zone suffix) is padded to six digits instead."""
    raw = f"substr({x}, instr({x}, '.') + 1)"
    no_z = f"replace({raw}, 'Z', '')"
    no_plus = f"substr({no_z}, 1, instr({no_z} || '+', '+') - 1)"
    digits = f"substr({no_plus}, 1, instr({no_plus} || '-', '-') - 1)"
    fraction = (
        f"CASE WHEN instr({x}, '.') > 0 THEN substr({digits} || '000000', 1, 6) ELSE '000000' END"
    )
    canonical = f"(strftime('%Y-%m-%d %H:%M:%S', {x}) || '.' || {fraction})"
    # strftime gives NULL for text it cannot read; keep the stored text instead, so an
    # odd value still counts, groups and compares as itself rather than vanishing.
    return f"COALESCE({canonical}, {x})"


@compiles(AsDatetime, "sqlite")
def _as_datetime_sqlite(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    return _sqlite_canonical_datetime(compiler.process(element.clauses, **kw))


class SqliteDatetimeText(FunctionElement[Any]):
    """A DATETIME operand in a filter. On SQLite, timestamps are text and compare as
    text, so '10:30:00' and '10:30:00.000000' differ; this puts both sides in one format.
    Elsewhere it is the operand unchanged (Postgres compares real timestamps)."""

    type = LenientDateTime()  # an unreadable stored value comes back as stored
    name = "sqlite_datetime_text"
    inherit_cache = True


@compiles(SqliteDatetimeText, "sqlite")
def _datetime_text_sqlite(element: SqliteDatetimeText, compiler: SQLCompiler, **kw: Any) -> str:
    return _sqlite_canonical_datetime(compiler.process(element.clauses, **kw))


@compiles(SqliteDatetimeText)
def _datetime_text_other(element: SqliteDatetimeText, compiler: SQLCompiler, **kw: Any) -> str:
    return compiler.process(element.clauses, **kw)


@compiles(AsDatetime)
def _as_datetime_other(element: AsDatetime, compiler: SQLCompiler, **kw: Any) -> str:
    raise CompileError(f"datetime normalisation is not implemented for {compiler.dialect.name}")


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
            stored = String() if rfield.text_number else _TYPES[rfield.type]
            columns.setdefault(rfield.alias, {})[rfield.column] = stored
        self.tables: dict[str, FromClause] = {}
        for alias, (name, schema) in names.items():
            cols = [column(c, t) for c, t in sorted(columns.get(alias, {}).items())]
            self.tables[alias] = table(name, *cols, schema=schema).alias(alias)

    def col(self, rfield: ResolvedField) -> ColumnElement[Any]:
        raw = self.tables[rfield.alias].c[rfield.column]
        if not rfield.text_number:
            return raw
        # Placeholder text reads as NULL on both engines: SQLite would cast 'null' to 0
        # without an error, Postgres would fail the whole query.
        placeholder = func.trim(raw).in_(
            [bindparam(None, p, type_=String()) for p in TEXT_NUMBER_PLACEHOLDERS]
        )
        return cast(case((placeholder, None), else_=raw), Float)

    def value(self, rfield: ResolvedField) -> ColumnElement[Any]:
        """The field as compared, aggregated, grouped or ordered. A DATETIME gets one
        canonical text form on SQLite (a no-op elsewhere), so equal instants stored in
        different text formats are equal. Selected columns use `col` and come back as
        stored."""
        raw = self.col(rfield)
        return SqliteDatetimeText(raw) if rfield.type == "datetime" else raw


def _fields(plan: QueryPlan) -> list[ResolvedField]:
    out: list[ResolvedField] = list(plan.select)
    out += [m.field for m in plan.metrics if m.field is not None]
    out += [g.field for g in plan.group_by]
    out += [g.key for g in plan.group_by if g.key is not None]
    out += [o.field for o in plan.order_by if o.field is not None]
    out += plan.tiebreak
    for series in plan.series:
        out.append(series.date_field)
        if series.metric.field is not None:
            out.append(series.metric.field)
    predicates = [p for m in plan.metrics for p in m.where]
    predicates += [p for series in plan.series for p in series.where]
    for item in plan.where:
        predicates += item.predicates if isinstance(item, PredicateGroup) else (item,)
    for predicate in predicates:
        out.append(predicate.field)
        if predicate.other is not None:
            out.append(predicate.other)
    return out


def _required_aliases(plan: QueryPlan) -> set[str]:
    """Table aliases a row must have a match in. A join used only inside `any_of`
    groups is optional: an inner join there would drop rows that satisfy another branch
    of the OR (an urgent work order with no technician). Select, metrics, group_by and
    AND filters keep inner-join semantics; ORDER BY alone never makes a join required.
    A metric's own `where` never makes a join required either: it picks rows for that
    metric only, and an inner join would drop rows from every other metric."""
    used: list[ResolvedField] = list(plan.select)
    used += [m.field for m in plan.metrics if m.field is not None]
    used += [g.field for g in plan.group_by]
    # ORDER BY is not listed: sorting by a field from an optional join must not turn it
    # into an inner join and drop the rows the OR kept (they sort with NULLs).
    for item in plan.where:
        if isinstance(item, PredicateGroup) and item.mode == "any_of":
            continue
        predicates = item.predicates if isinstance(item, PredicateGroup) else (item,)
        for predicate in predicates:
            used.append(predicate.field)
            if predicate.other is not None:
                used.append(predicate.other)
    return _with_parents(plan, used)


def _with_parents(plan: QueryPlan, used: list[ResolvedField]) -> set[str]:
    parents = {join.alias: join.parent_alias for join in plan.joins}
    required: set[str] = set()
    for rfield in used:
        alias: str | None = rfield.alias
        while alias is not None and alias not in required:
            required.add(alias)
            alias = parents.get(alias)
    return required


def _bind(value: Any, col: ColumnElement[Any]) -> ColumnElement[Any]:
    """A bound parameter typed like its column. Passing a bare Python value lets
    SQLAlchemy render some values (booleans) as SQL literals; this never does."""
    return bindparam(None, value, type_=col.type)


def _comparison_operands(
    tables: _Tables, predicate: Predicate
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    assert predicate.other is not None
    if {predicate.field.type, predicate.other.type} == {"date", "datetime"}:
        # A DATE against a DATETIME: compare both as datetimes (a DATE is its midnight).
        return AsDatetime(tables.col(predicate.field)), AsDatetime(tables.col(predicate.other))
    return tables.value(predicate.field), tables.value(predicate.other)


def _predicate(tables: _Tables, predicate: Predicate) -> ColumnElement[bool]:
    op = predicate.op
    if predicate.other is not None:
        col, rhs = _comparison_operands(tables, predicate)
    else:
        raw = tables.col(predicate.field)

        def bound(value: Any) -> ColumnElement[Any]:
            if predicate.field.type == "datetime":
                return SqliteDatetimeText(_bind(value, raw))
            return _bind(value, raw)

        col = SqliteDatetimeText(raw) if predicate.field.type == "datetime" else raw
        if op == "is_null":
            col = raw
        single = op in ("eq", "neq", "gt", "gte", "lt", "lte")
        rhs = bound(predicate.values[0]) if single else None
        if op == "between":
            return col.between(bound(predicate.values[0]), bound(predicate.values[1]))
        if op == "in":
            return col.in_([bound(v) for v in predicate.values])
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
    if metric.field is None and not metric.where:
        return func.count()
    # A code constant, not a value: rendered as text so only user values are bound.
    col: ColumnElement[Any] = (
        literal_column("1", BigInteger()) if metric.field is None else tables.value(metric.field)
    )
    if metric.where:
        # No FILTER (WHERE …): CASE runs the same on Postgres and SQLite. Rows that do
        # not match give NULL, which every aggregate skips.
        col = case((and_(*[_predicate(tables, p) for p in metric.where]), col))
    arg = col.distinct() if metric.distinct else col
    if metric.agg in ("count", "count_distinct"):
        return func.count(arg)
    return getattr(func, metric.agg)(arg)


def _ratio(exprs: dict[str, ColumnElement[Any]], metric: PlanMetric) -> ColumnElement[Any]:
    """numerator * scale / NULLIF(denominator, 0), in floating point: Postgres would
    divide two counts as integers, and a zero denominator must give NULL, not an error.
    The constants are rendered as text, so only user values are ever bound."""
    numerator = cast(exprs[metric.numerator or ""], Float)
    if metric.as_percent:
        numerator = numerator * literal_column("100")
    return numerator / func.nullif(exprs[metric.denominator or ""], literal_column("0"))


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


def _source(plan: QueryPlan, tables: _Tables, required: set[str]) -> FromClause:
    source = tables.tables[plan.base_alias]
    for join in plan.joins:
        parent = tables.tables[join.parent_alias]
        child = tables.tables[join.alias]
        source = source.join(
            child,
            parent.c[join.parent_column] == child.c[join.column],
            isouter=join.alias not in required,
        )
    return source


def _shared_where(tables: _Tables, plan: QueryPlan) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    for item in plan.where:
        if isinstance(item, PredicateGroup):
            parts = [_predicate(tables, p) for p in item.predicates]
            conditions.append(or_(*parts) if item.mode == "any_of" else and_(*parts))
        else:
            conditions.append(_predicate(tables, item))
    return conditions


def _series_part(plan: QueryPlan, series: PlanSeries, index: int) -> CTE:
    """One series as (period, value), grouped by its own date field. Its own tables, so
    each subquery joins only what it needs to inner-join."""
    tables = _Tables(plan)
    used: list[ResolvedField] = [series.date_field, *(p.field for p in series.where)]
    if series.metric.field is not None:
        used.append(series.metric.field)
    for item in plan.where:
        if isinstance(item, PredicateGroup) and item.mode == "any_of":
            continue
        predicates = item.predicates if isinstance(item, PredicateGroup) else (item,)
        used += [p.field for p in predicates]
        used += [p.other for p in predicates if p.other is not None]
    used += [p.other for p in series.where if p.other is not None]
    source = _source(plan, tables, _with_parents(plan, used))
    period = GRAINS[plan.grain or ""](tables.value(series.date_field))
    conditions = _shared_where(tables, plan)
    conditions += [_predicate(tables, p) for p in series.where]
    # A row with no date in this series belongs to no period.
    conditions.append(tables.col(series.date_field).is_not(None))
    stmt = (
        select(period.label(PERIOD_LABEL), _metric(tables, series.metric).label("value"))
        .select_from(source)
        .where(and_(*conditions))
        .group_by(period)
    )
    # A CTE, not a subquery: the series is read twice (for the periods and for its
    # values), and a subquery would be written out, and run, twice.
    return stmt.cte(f"s{index}")


def _build_series(plan: QueryPlan) -> Select[Any]:
    """Each series is its own grouped subquery, left-joined to the union of every
    series' periods. No FULL OUTER JOIN and no generate_series, so it runs on SQLite
    and Postgres alike. A period missing from a count series is 0; from any other
    aggregate, NULL."""
    parts = [_series_part(plan, series, i) for i, series in enumerate(plan.series)]
    if len(parts) == 1:
        periods: FromClause = parts[0]
    else:
        periods = union(*[select(part.c[PERIOD_LABEL]) for part in parts]).subquery("periods")
    period = periods.c[PERIOD_LABEL]
    source: FromClause = periods
    columns: list[ColumnElement[Any]] = [period.label(PERIOD_LABEL)]
    for part, series in zip(parts, plan.series, strict=True):
        if part is not periods:
            source = source.outerjoin(part, part.c[PERIOD_LABEL] == period)
        value: ColumnElement[Any] = part.c.value
        if series.metric.agg in ("count", "count_distinct"):
            value = func.coalesce(value, literal_column("0"))
        columns.append(value.label(series.label))
    return select(*columns).select_from(source).order_by(period)


ORDER_PREFIX = "_order_"  # labels are slugs, which start with a letter, so never collide

# Two ordering values within this distance tie: the eval scorer's tolerance, so a float
# sum that differs in its last bits between Postgres and SQLite still counts as a tie.
TIE_TOLERANCE = 1e-6


def peeks(plan: QueryPlan, row_cap: int) -> bool:
    """Whether a run fetches one row past the limit, to see if it ties with the last."""
    return (
        plan.intent_type != "date_series"
        and plan.limit is not None
        and bool(plan.order_by)
        and plan.limit < row_cap
    )


def _hidden_order_index(plan: QueryPlan, index: int) -> bool:
    """A row-list ORDER BY field that is not also selected needs its own column to be
    compared."""
    item = plan.order_by[index]
    return item.field is not None and all(
        (f.alias, f.column) != (item.field.alias, item.field.column) for f in plan.select
    )


def tie_labels(plan: QueryPlan) -> list[str]:
    """The output column of each ORDER BY item, in order."""
    labels: list[str] = []
    for index, item in enumerate(plan.order_by):
        if item.field is None:
            labels.append(item.label or "")
        elif _hidden_order_index(plan, index):
            labels.append(f"{ORDER_PREFIX}{index}")
        else:
            labels.append(item.field.label)
    return labels


def values_tie(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    numeric = (int, float, Decimal)
    both_numbers = isinstance(a, numeric) and isinstance(b, numeric)
    if both_numbers and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) <= TIE_TOLERANCE
    return bool(a == b)


def build(plan: QueryPlan, *, peek: bool = False) -> Select[Any]:
    """`peek` fetches one row past the limit, and adds a column for each row-list
    ORDER BY field that is not selected, so the caller can tell whether the next row
    ties with the last one. The caller drops both (`peeks`, `tie_labels`)."""
    if plan.intent_type == "date_series":
        return _build_series(plan)
    tables = _Tables(plan)
    source = _source(plan, tables, _required_aliases(plan))

    labelled: dict[str, ColumnElement[Any]] = {}
    group_exprs: list[ColumnElement[Any]] = []
    columns: list[ColumnElement[Any]] = []
    if plan.intent_type == "row_list":
        columns = [tables.col(f).label(f.label) for f in plan.select]
    else:
        for group in plan.group_by:
            if group.key is not None:
                key = tables.value(group.key)
                group_exprs.append(key)
                if group.key_shown:
                    columns.append(key.label(group.key.label))
                    _label(labelled, group.key.label, key)
            expr = tables.value(group.field)
            if group.grain is not None:
                expr = GRAINS[group.grain](expr)
            group_exprs.append(expr)
            columns.append(expr.label(group.label))
            _label(labelled, group.label, expr)
        exprs = {m.label: _metric(tables, m) for m in plan.metrics if m.agg != "ratio"}
        for metric in plan.metrics:
            expr = exprs.get(metric.label)
            if expr is None:
                expr = _ratio(exprs, metric)
            columns.append(expr.label(metric.label))
            _label(labelled, metric.label, expr)

    stmt = select(*columns).select_from(source)
    conditions = _shared_where(tables, plan)
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
        expr = tables.value(item.field) if item.field is not None else labelled[item.label or ""]
        # Explicit NULLS LAST both ways: by default Postgres puts NULLs first when
        # descending and SQLite puts them last, so the same intent would sort differently.
        ordered = expr.desc() if item.direction == "desc" else expr.asc()
        order.append(ordered.nulls_last())
    # Then a defined order inside ties: every group column (its key first), or a row
    # list's key, ascending. Without it, tied rows come back in whatever order the
    # engine returns, which differs between Postgres and SQLite.
    for group in plan.group_by:
        if group.key is not None:
            order.append(tables.value(group.key).asc().nulls_last())
        order.append(labelled[group.label].asc().nulls_last())
    order += [tables.value(f).asc().nulls_last() for f in plan.tiebreak]
    if order:
        stmt = stmt.order_by(*order)
    if peek and plan.limit is not None:
        for index, item in enumerate(plan.order_by):
            if item.field is not None and _hidden_order_index(plan, index):
                stmt = stmt.add_columns(tables.value(item.field).label(f"{ORDER_PREFIX}{index}"))
        stmt = stmt.limit(plan.limit + 1)
    elif plan.limit is not None:
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
