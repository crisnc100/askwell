"""The validator: every intent field checked against the registry, in plain Python.

It returns typed issues (never raises for a bad intent) and, when the intent is valid,
a `QueryPlan` the SQL builder compiles. All of the plan's identifiers come from the
registry and every value is already converted to the field's Python type.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from ledgerline.core.dates import naive_utc, resolve_relative
from ledgerline.core.intent import (
    COMPARISON_OPS,
    Condition,
    FilterGroup,
    Intent,
    Scalar,
)
from ledgerline.core.registry import (
    NUMERIC_TYPES,
    TEMPORAL_TYPES,
    EntityDef,
    FieldDef,
    FieldType,
    Registry,
)

MAX_HOPS = 3
DEFAULT_ROW_CAP = 1000

ErrorCode = Literal[
    "draft_registry",
    "intent_shape",
    "unknown_entity",
    "unknown_field",
    "hidden_field",
    "unreachable_field",
    "ambiguous_path",
    "fan_out",
    "one_to_many_join",
    "not_filterable",
    "not_aggregatable",
    "aggregate_type",
    "operator_type",
    "value_type",
    "value_shape",
    "value_not_allowed",
    "ambiguous_value",
    "column_comparison_type",
    "empty_in",
    "reversed_between",
    "date_range_field_type",
    "date_range_duplicate",
    "invalid_date_range",
    "grain_type",
    "having_without_group_by",
    "unknown_metric",
    "invalid_alias",
    "duplicate_alias",
    "alias_collision",
    "invalid_order_by",
    "limit_out_of_range",
]

_ALIAS = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_ORDERABLE: frozenset[str] = NUMERIC_TYPES | TEMPORAL_TYPES
_RANGE_OPS: frozenset[str] = frozenset({"gt", "gte", "lt", "lte", "between"})

Value = int | float | str | bool | date | datetime


@dataclass(frozen=True)
class Issue:
    code: ErrorCode
    location: str
    message: str


# --- the plan ---


@dataclass(frozen=True)
class JoinStep:
    """JOIN `table` AS `alias` ON `parent_alias`.`parent_column` = `alias`.`column`.

    Always a many-to-one step: the parent row references exactly one row here."""

    alias: str
    parent_alias: str
    parent_column: str
    table: str
    db_schema: str | None
    column: str


@dataclass(frozen=True)
class ResolvedField:
    alias: str  # table alias in the query
    entity: str
    name: str  # field slug
    column: str
    type: FieldType
    is_base: bool

    @property
    def label(self) -> str:
        return self.name if self.is_base else f"{self.entity}__{self.name}"

    @property
    def key(self) -> tuple[str, str]:
        return (self.entity, self.name)


@dataclass(frozen=True)
class Predicate:
    field: ResolvedField
    op: str
    values: tuple[Value, ...] = ()
    other: ResolvedField | None = None


@dataclass(frozen=True)
class PredicateGroup:
    mode: Literal["any_of", "all_of"]
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True)
class PlanMetric:
    label: str
    agg: str
    field: ResolvedField | None
    distinct: bool


@dataclass(frozen=True)
class PlanGroup:
    label: str
    field: ResolvedField
    grain: str | None


@dataclass(frozen=True)
class PlanHaving:
    metric: str  # metric label
    op: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class PlanOrder:
    label: str | None  # a metric or group label
    field: ResolvedField | None  # row_list: any reachable field
    direction: Literal["asc", "desc"]


@dataclass(frozen=True)
class QueryPlan:
    intent_type: str
    base_entity: str
    base_table: str
    base_schema: str | None
    base_alias: str
    joins: tuple[JoinStep, ...]
    select: tuple[ResolvedField, ...]
    metrics: tuple[PlanMetric, ...]
    where: tuple[Predicate | PredicateGroup, ...]
    group_by: tuple[PlanGroup, ...]
    having: tuple[PlanHaving, ...]
    order_by: tuple[PlanOrder, ...]
    limit: int | None


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list[Issue])
    plan: QueryPlan | None = None
    refusal_reason: str | None = None

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> list[str]:
        return [issue.code for issue in self.issues]


# --- paths ---


@dataclass(frozen=True)
class _Edge:
    rel: int
    src: str
    dst: str
    src_field: str
    dst_field: str
    down: bool  # True: one-to-many (src is the "one" side)


def _adjacency(registry: Registry) -> dict[str, list[_Edge]]:
    adjacency: dict[str, list[_Edge]] = {slug: [] for slug in registry.entities}
    for index, rel in enumerate(registry.relationships):
        if rel.from_entity == rel.to_entity:
            continue  # self-references cannot be expressed without self-joins
        adjacency[rel.from_entity].append(
            _Edge(index, rel.from_entity, rel.to_entity, rel.from_field, rel.to_field, False)
        )
        adjacency[rel.to_entity].append(
            _Edge(index, rel.to_entity, rel.from_entity, rel.to_field, rel.from_field, True)
        )
    return adjacency


@dataclass(frozen=True)
class _PathInfo:
    hops: int
    count: int  # number of distinct shortest paths
    path: tuple[_Edge, ...]  # valid only when count == 1


def _shortest_paths(registry: Registry, base: str) -> dict[str, _PathInfo]:
    adjacency = _adjacency(registry)
    dist: dict[str, int] = {base: 0}
    count: dict[str, int] = {base: 1}
    pred: dict[str, _Edge] = {}
    queue: deque[str] = deque([base])
    while queue:
        node = queue.popleft()
        if dist[node] == MAX_HOPS:
            continue
        for edge in adjacency[node]:
            nxt = edge.dst
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                count[nxt] = count[node]
                pred[nxt] = edge
                queue.append(nxt)
            elif dist[nxt] == dist[node] + 1:
                count[nxt] += count[node]
    out: dict[str, _PathInfo] = {}
    for node, hops in dist.items():
        path: list[_Edge] = []
        if count[node] == 1:
            cursor = node
            while cursor != base:
                edge = pred[cursor]
                path.append(edge)
                cursor = edge.src
            path.reverse()
        out[node] = _PathInfo(hops, count[node], tuple(path))
    return out


# --- the validator ---


class _Validator:
    def __init__(self, intent: Intent, registry: Registry, now: datetime, row_cap: int) -> None:
        self.intent = intent
        self.registry = registry
        self.now = now
        self.row_cap = row_cap
        self.issues: list[Issue] = []
        self.aggregated = bool(intent.metrics)
        self.base = ""
        self.base_def: EntityDef | None = None
        self.paths: dict[str, _PathInfo] = {}
        self.join_aliases: dict[tuple[tuple[int, bool], ...], str] = {}
        self.joins: list[JoinStep] = []

    def fail(self, code: ErrorCode, location: str, message: str) -> None:
        self.issues.append(Issue(code, location, message))

    # entity and field lookup

    def _find_entity(self, name: str) -> str | None:
        lowered = name.lower()
        if lowered in self.registry.entities:
            return lowered
        for slug, entity in self.registry.entities.items():
            if lowered in (alias.lower() for alias in entity.aliases):
                return slug
        return None

    @staticmethod
    def _find_field(entity: EntityDef, name: str) -> str | None:
        lowered = name.lower()
        if lowered in entity.fields:
            return lowered
        for slug, fdef in entity.fields.items():
            if lowered in (alias.lower() for alias in fdef.aliases):
                return slug
        return None

    def _alias_for(self, path: tuple[_Edge, ...]) -> str:
        if not path:
            return "t0"
        key = tuple((edge.rel, edge.down) for edge in path)
        if key in self.join_aliases:
            return self.join_aliases[key]
        parent = self._alias_for(path[:-1])
        alias = f"t{len(self.join_aliases) + 1}"
        self.join_aliases[key] = alias
        edge = path[-1]
        src = self.registry.entities[edge.src]
        dst = self.registry.entities[edge.dst]
        self.joins.append(
            JoinStep(
                alias=alias,
                parent_alias=parent,
                parent_column=src.fields[edge.src_field].column,
                table=dst.table,
                db_schema=dst.db_schema,
                column=dst.fields[edge.dst_field].column,
            )
        )
        return alias

    def resolve(self, ref: str, location: str) -> tuple[ResolvedField, FieldDef] | None:
        assert self.base_def is not None
        if "." in ref:
            entity_name, field_name = ref.split(".", 1)
            entity_slug = self._find_entity(entity_name)
            if entity_slug is None:
                self.fail("unknown_entity", location, f"no entity {entity_name!r}")
                return None
        else:
            entity_slug, field_name = self.base, ref
        entity = self.registry.entities[entity_slug]
        field_slug = self._find_field(entity, field_name)
        if field_slug is None:
            self.fail("unknown_field", location, f"no field {field_name!r} on {entity_slug}")
            return None
        fdef = entity.fields[field_slug]
        if fdef.hidden:
            self.fail("hidden_field", location, f"{entity_slug}.{field_slug} is hidden")
            return None
        info = self.paths.get(entity_slug)
        if info is None:
            self.fail(
                "unreachable_field",
                location,
                f"{entity_slug} has no path from {self.base} within {MAX_HOPS} hops",
            )
            return None
        if info.count > 1:
            self.fail(
                "ambiguous_path",
                location,
                f"{info.count} equally short paths from {self.base} to {entity_slug}",
            )
            return None
        if any(edge.down for edge in info.path):
            if self.aggregated:
                self.fail(
                    "fan_out",
                    location,
                    f"joining {self.base} to {entity_slug} crosses a one-to-many edge "
                    "while aggregating, which would double count",
                )
            else:
                self.fail(
                    "one_to_many_join",
                    location,
                    f"{entity_slug} is on the many side of {self.base}; re-base the question",
                )
            return None
        alias = self._alias_for(info.path)
        resolved = ResolvedField(
            alias=alias,
            entity=entity_slug,
            name=field_slug,
            column=fdef.column,
            type=fdef.type,
            is_base=not info.path,
        )
        return resolved, fdef

    # values

    def convert(self, value: Scalar | None, ftype: FieldType, location: str) -> Value | None:
        ok = True
        out: Value | None = None
        if ftype == "integer":
            ok = isinstance(value, int) and not isinstance(value, bool)
            out = value
        elif ftype == "number":
            ok = isinstance(value, int | float) and not isinstance(value, bool)
            out = value
        elif ftype == "text":
            ok = isinstance(value, str)
            out = value
        elif ftype == "boolean":
            ok = isinstance(value, bool)
            out = value
        elif ftype == "date":
            try:
                out = date.fromisoformat(value) if isinstance(value, str) else None
            except ValueError:
                out = None
            ok = out is not None
        else:
            try:
                out = naive_utc(datetime.fromisoformat(value)) if isinstance(value, str) else None
            except ValueError:
                out = None
            ok = out is not None
        if not ok:
            self.fail("value_type", location, f"{value!r} is not a valid {ftype}")
            return None
        return out

    def categorical(self, value: Value, fdef: FieldDef, location: str) -> Value | None:
        """An exact allowed value wins. Otherwise a case-insensitive match is used only if
        exactly one value (or alias target) matches; two that differ only by case are
        ambiguous, never silently swapped."""
        if not (fdef.categorical and fdef.allowed_values and isinstance(value, str)):
            return value
        if value in fdef.allowed_values:
            return value
        lowered = value.lower()
        matches = {allowed for allowed in fdef.allowed_values if allowed.lower() == lowered}
        if not matches:
            matches = {t for alias, t in fdef.value_aliases.items() if alias.lower() == lowered}
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            self.fail(
                "ambiguous_value",
                location,
                f"{value!r} matches {sorted(matches)} in {fdef.column}; use the exact value",
            )
            return None
        self.fail(
            "value_not_allowed",
            location,
            f"{value!r} is not one of {fdef.column}'s allowed values",
        )
        return None

    # sections

    def check_shape(self) -> bool:
        intent = self.intent
        loc = "intent_type"
        if intent.intent_type == "unanswerable":
            populated = (
                intent.select
                or intent.metrics
                or intent.filters
                or intent.having
                or intent.group_by
                or intent.date_range
                or intent.order_by
                or intent.limit is not None
            )
            if not intent.unanswerable_reason:
                self.fail("intent_shape", loc, "unanswerable needs an unanswerable_reason")
            if populated:
                self.fail("intent_shape", loc, "unanswerable takes no query fields")
            return False
        if intent.unanswerable_reason is not None:
            self.fail("intent_shape", loc, "only unanswerable takes an unanswerable_reason")
        if intent.entity is None:
            self.fail("intent_shape", "entity", f"{intent.intent_type} needs an entity")
        if intent.intent_type == "row_list":
            if not intent.select:
                self.fail("intent_shape", loc, "row_list needs select")
            if intent.metrics or intent.group_by or intent.having:
                self.fail("intent_shape", loc, "row_list takes no metrics, group_by or having")
        else:
            if not intent.metrics:
                self.fail("intent_shape", loc, f"{intent.intent_type} needs metrics")
            if intent.select:
                self.fail("intent_shape", loc, f"{intent.intent_type} takes no select")
            if intent.intent_type == "summary" and intent.group_by:
                self.fail("intent_shape", loc, "summary takes no group_by; use grouped_summary")
            if intent.intent_type == "grouped_summary" and not intent.group_by:
                self.fail("intent_shape", loc, "grouped_summary needs group_by")
        if intent.having and not intent.group_by:
            self.fail("having_without_group_by", "having", "having needs a group_by")
        return intent.entity is not None

    def check_condition(self, cond: Condition, loc: str) -> Predicate | None:
        resolved = self.resolve(cond.field, f"{loc}.field")
        if resolved is None:
            return None
        rfield, fdef = resolved
        if not fdef.filterable:
            self.fail("not_filterable", f"{loc}.field", f"{cond.field} is not filterable")
            return None
        op = cond.op
        if op in _RANGE_OPS and rfield.type not in _ORDERABLE:
            self.fail("operator_type", f"{loc}.op", f"{op} does not apply to {rfield.type}")
            return None
        if op == "ilike_contains" and rfield.type != "text":
            self.fail("operator_type", f"{loc}.op", "ilike_contains needs a text field")
            return None

        if cond.other_field is not None:
            return self.check_comparison(cond, rfield, loc)

        if op == "in":
            if cond.values is None or cond.value is not None:
                self.fail("value_shape", loc, "in takes `values`")
                return None
            if not cond.values:
                self.fail("empty_in", f"{loc}.values", "in needs at least one value")
                return None
            return self._values_predicate(rfield, fdef, op, cond.values, loc)
        if op == "between":
            if cond.values is None or len(cond.values) != 2 or cond.value is not None:
                self.fail("value_shape", loc, "between takes `values: [low, high]`")
                return None
            predicate = self._values_predicate(rfield, fdef, op, cond.values, loc)
            if predicate is None:
                return None
            low, high = predicate.values
            if low > high:  # type: ignore[operator]
                self.fail("reversed_between", f"{loc}.values", f"{low!r} > {high!r}")
                return None
            return predicate
        if op == "is_null":
            if cond.values is not None or not isinstance(cond.value, bool | None):
                self.fail("value_shape", loc, "is_null takes `value: true|false` or nothing")
                return None
            return Predicate(rfield, op, (cond.value is not False,))
        # eq, neq, gt, gte, lt, lte, ilike_contains
        if cond.values is not None or cond.value is None:
            self.fail("value_shape", loc, f"{op} takes one `value`")
            return None
        if op == "ilike_contains":
            if not isinstance(cond.value, str) or not cond.value:
                self.fail("value_type", f"{loc}.value", "ilike_contains needs non-empty text")
                return None
            return Predicate(rfield, op, (cond.value,))
        return self._values_predicate(rfield, fdef, op, [cond.value], loc)

    def _values_predicate(
        self, rfield: ResolvedField, fdef: FieldDef, op: str, raw: list[Scalar], loc: str
    ) -> Predicate | None:
        values: list[Value] = []
        for index, item in enumerate(raw):
            converted = self.convert(item, rfield.type, f"{loc}.values[{index}]")
            if converted is None:
                return None
            if op in ("eq", "neq", "in"):
                converted = self.categorical(converted, fdef, f"{loc}.values[{index}]")
                if converted is None:
                    return None
            values.append(converted)
        return Predicate(rfield, op, tuple(values))

    def check_comparison(
        self, cond: Condition, rfield: ResolvedField, loc: str
    ) -> Predicate | None:
        assert cond.other_field is not None
        if cond.op not in COMPARISON_OPS or cond.value is not None or cond.values is not None:
            self.fail("value_shape", loc, "other_field works with eq..lte and no value")
            return None
        resolved = self.resolve(cond.other_field, f"{loc}.other_field")
        if resolved is None:
            return None
        other, other_def = resolved
        if not other_def.filterable:
            self.fail("not_filterable", f"{loc}.other_field", f"{cond.other_field} not filterable")
            return None
        if _family(rfield.type) != _family(other.type):
            self.fail(
                "column_comparison_type",
                loc,
                f"cannot compare {rfield.type} with {other.type}",
            )
            return None
        return Predicate(rfield, cond.op, (), other)

    def check_filters(self) -> list[Predicate | PredicateGroup]:
        out: list[Predicate | PredicateGroup] = []
        for index, item in enumerate(self.intent.filters):
            loc = f"filters[{index}]"
            if isinstance(item, Condition):
                predicate = self.check_condition(item, loc)
                if predicate is not None:
                    out.append(predicate)
                continue
            out_group = self.check_group(item, loc)
            if out_group is not None:
                out.append(out_group)
        return out

    def check_group(self, group: FilterGroup, loc: str) -> PredicateGroup | None:
        if (group.any_of is None) == (group.all_of is None):
            self.fail("value_shape", loc, "a filter group has exactly one of any_of / all_of")
            return None
        mode: Literal["any_of", "all_of"] = "any_of" if group.any_of is not None else "all_of"
        conditions = group.any_of if group.any_of is not None else group.all_of
        assert conditions is not None
        if not conditions:
            self.fail("value_shape", loc, f"{mode} needs at least one condition")
            return None
        predicates: list[Predicate] = []
        for index, cond in enumerate(conditions):
            predicate = self.check_condition(cond, f"{loc}.{mode}[{index}]")
            if predicate is not None:
                predicates.append(predicate)
        if len(predicates) != len(conditions):
            return None
        return PredicateGroup(mode, tuple(predicates))

    def check_date_range(self, where: list[Predicate | PredicateGroup]) -> list[Predicate]:
        dr = self.intent.date_range
        if dr is None:
            return []
        loc = "date_range"
        resolved = self.resolve(dr.field, f"{loc}.field")
        if resolved is None:
            return []
        rfield, fdef = resolved
        if rfield.type not in TEMPORAL_TYPES:
            self.fail("date_range_field_type", loc, f"{dr.field} is {rfield.type}, not a date")
            return []
        if not fdef.filterable:
            self.fail("not_filterable", f"{loc}.field", f"{dr.field} is not filterable")
            return []
        filtered = {p.field.key for p in _flatten(where)}
        if rfield.key in filtered:
            self.fail(
                "date_range_duplicate",
                loc,
                f"{dr.field} is filtered twice; use date_range or a filter, not both",
            )
            return []
        absolute = dr.start is not None or dr.end is not None
        if (dr.relative is None) == (not absolute):
            self.fail("invalid_date_range", loc, "give either relative or start+end")
            return []
        if dr.relative is not None:
            try:
                start, end = resolve_relative(dr.relative, dr.n, self.now)
            except ValueError as exc:
                self.fail("invalid_date_range", loc, str(exc))
                return []
        else:
            if dr.n is not None or dr.start is None or dr.end is None:
                self.fail("invalid_date_range", loc, "absolute ranges need start and end")
                return []
            try:
                start = naive_utc(datetime.fromisoformat(dr.start))
                end = naive_utc(datetime.fromisoformat(dr.end))
            except ValueError:
                self.fail("invalid_date_range", loc, "start/end must be ISO dates")
                return []
            if start >= end:
                self.fail("reversed_between", loc, f"start {dr.start} is not before end {dr.end}")
                return []
        low: Value = start.date() if rfield.type == "date" else start
        high: Value = end.date() if rfield.type == "date" else end
        if rfield.type == "date" and end != datetime.combine(end.date(), datetime.min.time()):
            # A date column and a mid-day end: include that day.
            high = date.fromordinal(end.date().toordinal() + 1)
        return [Predicate(rfield, "gte", (low,)), Predicate(rfield, "lt", (high,))]

    def check_metrics(self, group_labels: set[str]) -> list[PlanMetric]:
        """Metric labels must be unique and must not reuse a group_by label: a metric
        labelled like a group would shadow it in HAVING and ORDER BY."""
        out: list[PlanMetric] = []
        labels: set[str] = set()
        for index, metric in enumerate(self.intent.metrics):
            loc = f"metrics[{index}]"
            rfield: ResolvedField | None = None
            if metric.field is None:
                if metric.agg != "count":
                    self.fail("value_shape", loc, f"{metric.agg} needs a field")
                    continue
            else:
                resolved = self.resolve(metric.field, f"{loc}.field")
                if resolved is None:
                    continue
                rfield, fdef = resolved
                if metric.agg in ("sum", "avg") and rfield.type not in NUMERIC_TYPES:
                    self.fail("aggregate_type", loc, f"{metric.agg} needs a numeric field")
                    continue
                if metric.agg in ("min", "max") and rfield.type not in _ORDERABLE:
                    self.fail("aggregate_type", loc, f"{metric.agg} needs a number or date")
                    continue
                if metric.agg not in ("count", "count_distinct") and not fdef.aggregatable:
                    self.fail("not_aggregatable", loc, f"{metric.field} is not aggregatable")
                    continue
            if metric.alias is not None:
                if not _ALIAS.match(metric.alias):
                    self.fail("invalid_alias", f"{loc}.alias", f"{metric.alias!r} is not a slug")
                    continue
                label = metric.alias
                if label in group_labels:
                    self.fail(
                        "alias_collision",
                        f"{loc}.alias",
                        f"{label!r} is already a group_by label",
                    )
                    continue
            else:
                label = metric.agg if rfield is None else f"{metric.agg}_{rfield.name}"
                suffix = 2
                base_label = label
                while label in labels or label in group_labels:
                    label = f"{base_label}_{suffix}"
                    suffix += 1
            if label in labels:
                self.fail("duplicate_alias", f"{loc}.alias", f"{label!r} is used twice")
                continue
            labels.add(label)
            distinct = metric.distinct or metric.agg == "count_distinct"
            out.append(PlanMetric(label, metric.agg, rfield, distinct))
        return out

    def check_group_by(self) -> list[PlanGroup]:
        out: list[PlanGroup] = []
        for index, group in enumerate(self.intent.group_by):
            loc = f"group_by[{index}]"
            resolved = self.resolve(group.field, f"{loc}.field")
            if resolved is None:
                continue
            rfield, _ = resolved
            if group.grain is not None and rfield.type not in TEMPORAL_TYPES:
                self.fail("grain_type", loc, f"{group.grain} needs a date field")
                continue
            label = rfield.label if group.grain is None else f"{rfield.label}_{group.grain}"
            if label in {g.label for g in out}:
                self.fail("alias_collision", loc, f"{group.field} is grouped twice")
                continue
            out.append(PlanGroup(label, rfield, group.grain))
        return out

    def check_having(self, metrics: list[PlanMetric]) -> list[PlanHaving]:
        out: list[PlanHaving] = []
        labels = {metric.label for metric in metrics}
        for index, having in enumerate(self.intent.having):
            loc = f"having[{index}]"
            if having.metric not in labels:
                self.fail("unknown_metric", loc, f"no metric labelled {having.metric!r}")
                continue
            if having.op == "between":
                if having.values is None or len(having.values) != 2 or having.value is not None:
                    self.fail("value_shape", loc, "between takes `values: [low, high]`")
                    continue
                if having.values[0] > having.values[1]:
                    self.fail("reversed_between", loc, "having between is reversed")
                    continue
                out.append(PlanHaving(having.metric, "between", tuple(having.values)))
                continue
            if having.value is None or having.values is not None:
                self.fail("value_shape", loc, f"{having.op} takes one `value`")
                continue
            out.append(PlanHaving(having.metric, having.op, (having.value,)))
        return out

    def check_order(self, metrics: list[PlanMetric], groups: list[PlanGroup]) -> list[PlanOrder]:
        out: list[PlanOrder] = []
        metric_labels = {metric.label for metric in metrics}
        for index, order in enumerate(self.intent.order_by):
            loc = f"order_by[{index}]"
            if self.intent.intent_type == "row_list":
                resolved = self.resolve(order.target, f"{loc}.target")
                if resolved is not None:
                    out.append(PlanOrder(None, resolved[0], order.direction))
                continue
            if order.target in metric_labels:
                out.append(PlanOrder(order.target, None, order.direction))
                continue
            match = [g for g in groups if order.target in (g.label, _ref(g.field))]
            if not match:
                self.fail(
                    "invalid_order_by",
                    loc,
                    f"{order.target!r} is neither a metric alias nor a group_by field",
                )
                continue
            out.append(PlanOrder(match[0].label, None, order.direction))
        return out

    def check_limit(self) -> int | None:
        limit = self.intent.limit
        if limit is not None and not 0 < limit <= self.row_cap:
            self.fail("limit_out_of_range", "limit", f"limit must be 1..{self.row_cap}")
            return None
        return limit

    def run(self, allow_draft: bool) -> ValidationResult:
        if self.registry.draft and not allow_draft:
            self.fail("draft_registry", "registry", "the registry is a draft; pass allow_draft")
            return ValidationResult(self.issues)
        if not self.check_shape():
            if self.intent.intent_type == "unanswerable" and not self.issues:
                return ValidationResult(refusal_reason=self.intent.unanswerable_reason)
            return ValidationResult(self.issues)
        assert self.intent.entity is not None
        base = self._find_entity(self.intent.entity)
        if base is None:
            self.fail("unknown_entity", "entity", f"no entity {self.intent.entity!r}")
            return ValidationResult(self.issues)
        self.base = base
        self.base_def = self.registry.entities[base]
        self.paths = _shortest_paths(self.registry, base)

        select: list[ResolvedField] = []
        for index, ref in enumerate(self.intent.select):
            resolved = self.resolve(ref, f"select[{index}]")
            if resolved is not None:
                select.append(resolved[0])
        groups = self.check_group_by()
        metrics = self.check_metrics({g.label for g in groups})
        where = self.check_filters()
        where_dates = self.check_date_range(where)
        having = self.check_having(metrics)
        order = self.check_order(metrics, groups)
        limit = self.check_limit()
        if self.issues:
            return ValidationResult(self.issues)
        plan = QueryPlan(
            intent_type=self.intent.intent_type,
            base_entity=base,
            base_table=self.base_def.table,
            base_schema=self.base_def.db_schema,
            base_alias="t0",
            joins=tuple(self.joins),
            select=tuple(select),
            metrics=tuple(metrics),
            where=(*where, *where_dates),
            group_by=tuple(groups),
            having=tuple(having),
            order_by=tuple(order),
            limit=limit,
        )
        return ValidationResult(plan=plan)


def _family(ftype: str) -> str:
    if ftype in NUMERIC_TYPES:
        return "number"
    if ftype in TEMPORAL_TYPES:
        return "time"
    return ftype


def _ref(rfield: ResolvedField) -> str:
    return f"{rfield.entity}.{rfield.name}"


def _flatten(where: list[Predicate | PredicateGroup]) -> list[Predicate]:
    out: list[Predicate] = []
    for item in where:
        if isinstance(item, Predicate):
            out.append(item)
        else:
            out.extend(item.predicates)
    return out


def validate(
    intent: Intent,
    registry: Registry,
    *,
    now: datetime,
    allow_draft: bool = False,
    row_cap: int = DEFAULT_ROW_CAP,
) -> ValidationResult:
    """Validate `intent` against `registry`. Never raises for a bad intent."""
    return _Validator(intent, registry, now, row_cap).run(allow_draft)
