"""The validator. Every rule in plan.md P2.4 (plus the two P2 grammar additions) has a
test named `test_rule_<code>`; `test_every_rule_has_a_named_test` keeps it that way."""

from __future__ import annotations

import sys
from datetime import date, datetime
from typing import Any, get_args

import pytest

from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry
from ledgerline.core.validate import (
    ErrorCode,
    Predicate,
    PredicateGroup,
    QueryPlan,
    validate,
)
from tests.core.conftest import NOW, check, make_registry

COUNT = [{"agg": "count"}]


def codes(registry: Registry, **intent: Any) -> list[str]:
    return check(registry, **intent).codes


def plan_of(registry: Registry, **intent: Any) -> QueryPlan:
    result = check(registry, **intent)
    assert result.ok, result.issues
    assert result.plan is not None
    return result.plan


def with_field(registry: Registry, entity: str, field: str, **changes: Any) -> Registry:
    ent = registry.entities[entity]
    fields = dict(ent.fields)
    fields[field] = fields[field].model_copy(update=changes)
    entities = dict(registry.entities)
    entities[entity] = ent.model_copy(update={"fields": fields})
    return registry.model_copy(update={"entities": entities})


def test_every_rule_has_a_named_test() -> None:
    module = sys.modules[__name__]
    missing = [c for c in get_args(ErrorCode) if not hasattr(module, f"test_rule_{c}")]
    assert missing == []


# --- one named test per rule ---


def test_rule_draft_registry(registry: Registry) -> None:
    draft = registry.model_copy(update={"draft": True})
    intent = Intent(intent_type="summary", entity="work_orders", metrics=[{"agg": "count"}])  # type: ignore[list-item]
    assert validate(intent, draft, now=NOW).codes == ["draft_registry"]
    assert validate(intent, draft, now=NOW, allow_draft=True).ok


@pytest.mark.parametrize(
    "intent",
    [
        {"intent_type": "summary", "entity": "work_orders"},
        {"intent_type": "summary", "metrics": COUNT},
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": COUNT,
            "group_by": [{"field": "status"}],
        },
        {"intent_type": "summary", "entity": "work_orders", "metrics": COUNT, "select": ["status"]},
        {"intent_type": "grouped_summary", "entity": "work_orders", "metrics": COUNT},
        {"intent_type": "row_list", "entity": "work_orders"},
        {"intent_type": "row_list", "entity": "work_orders", "select": ["id"], "metrics": COUNT},
        {"intent_type": "unanswerable"},
        {"intent_type": "unanswerable", "unanswerable_reason": "x", "metrics": COUNT},
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": COUNT,
            "unanswerable_reason": "x",
        },
    ],
)
def test_rule_intent_shape(registry: Registry, intent: dict[str, Any]) -> None:
    assert "intent_shape" in codes(registry, **intent)


def test_rule_unknown_entity(registry: Registry) -> None:
    assert codes(registry, intent_type="summary", entity="competitors", metrics=COUNT) == [
        "unknown_entity"
    ]
    assert codes(
        registry, intent_type="row_list", entity="parts", select=["competitors.price"]
    ) == ["unknown_entity"]


def test_rule_unknown_field(registry: Registry) -> None:
    assert codes(registry, intent_type="row_list", entity="work_orders", select=["mileage"]) == [
        "unknown_field"
    ]


@pytest.mark.parametrize(
    "intent",
    [
        {"intent_type": "row_list", "entity": "users", "select": ["email"]},
        {
            "intent_type": "row_list",
            "entity": "users",
            "select": ["username"],
            "filters": [{"field": "users.password_hash", "op": "is_null"}],
        },
        {
            "intent_type": "summary",
            "entity": "users",
            "metrics": [{"agg": "count_distinct", "field": "email"}],
        },
        {
            "intent_type": "grouped_summary",
            "entity": "users",
            "metrics": COUNT,
            "group_by": [{"field": "email"}],
        },
        {
            "intent_type": "row_list",
            "entity": "users",
            "select": ["username"],
            "order_by": [{"target": "password_hash"}],
        },
    ],
)
def test_rule_hidden_field(registry: Registry, intent: dict[str, Any]) -> None:
    assert codes(registry, **intent) == ["hidden_field"]


def test_rule_unreachable_field(registry: Registry) -> None:
    # users has no relationship to anything.
    assert codes(
        registry, intent_type="row_list", entity="work_orders", select=["users.username"]
    ) == ["unreachable_field"]
    # Four hops is past the limit: customers -> sites -> work_orders -> work_order_parts -> parts.
    assert codes(registry, intent_type="row_list", entity="customers", select=["parts.name"]) == [
        "unreachable_field"
    ]


def test_rule_ambiguous_path() -> None:
    reg = make_registry(
        {"flights": ["origin_id", "dest_id"], "airports": ["elevation"]},
        [("flights", "origin_id", "airports", "id"), ("flights", "dest_id", "airports", "id")],
    )
    assert codes(reg, intent_type="row_list", entity="flights", select=["airports.elevation"]) == [
        "ambiguous_path"
    ]


def test_rule_ambiguous_path_at_three_hops() -> None:
    # a -> b -> c -> e and a -> b -> d -> e: two shortest 3-hop paths to e.
    reg = make_registry(
        {"a": ["b_id"], "b": ["c_id", "d_id"], "c": ["e_id"], "d": ["e_id"], "e": ["v"]},
        [
            ("a", "b_id", "b", "id"),
            ("b", "c_id", "c", "id"),
            ("b", "d_id", "d", "id"),
            ("c", "e_id", "e", "id"),
            ("d", "e_id", "e", "id"),
        ],
    )
    assert codes(reg, intent_type="row_list", entity="a", select=["e.v"]) == ["ambiguous_path"]
    assert check(reg, intent_type="row_list", entity="a", select=["c.e_id"]).ok


def test_rule_fan_out(registry: Registry) -> None:
    # work_orders -> invoices is one-to-many: summing invoice amounts per work order
    # rows would double count.
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "sum", "field": "invoices.amount"}],
    ) == ["fan_out"]


def test_rule_fan_out_at_three_hops(registry: Registry) -> None:
    # parts -> work_order_parts (one-to-many) -> work_orders -> sites: 3 hops, one fan-out edge.
    assert codes(
        registry,
        intent_type="summary",
        entity="parts",
        metrics=COUNT,
        filters=[{"field": "sites.city", "op": "eq", "value": "Austin"}],
    ) == ["fan_out"]
    # customers -> sites -> work_orders -> invoices: 3 one-to-many edges.
    assert codes(
        registry,
        intent_type="summary",
        entity="customers",
        metrics=COUNT,
        filters=[{"field": "invoices.status", "op": "eq", "value": "paid"}],
    ) == ["fan_out"]


def test_three_hop_many_to_one_path_is_allowed(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="grouped_summary",
        entity="invoices",
        metrics=[{"agg": "sum", "field": "amount"}],
        group_by=[{"field": "customers.region"}],
    )
    assert [j.table for j in plan.joins] == ["work_orders", "sites", "customers"]


def test_rule_one_to_many_join(registry: Registry) -> None:
    assert codes(
        registry, intent_type="row_list", entity="customers", select=["name", "invoices.amount"]
    ) == ["one_to_many_join"]


def test_rule_not_filterable(registry: Registry) -> None:
    reg = with_field(registry, "work_orders", "status", filterable=False)
    assert codes(
        reg,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[{"field": "status", "op": "eq", "value": "open"}],
    ) == ["not_filterable"]
    reg = with_field(registry, "work_orders", "opened_at", filterable=False)
    assert codes(
        reg,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        date_range={"field": "opened_at", "relative": "last_month"},
    ) == ["not_filterable"]
    reg = with_field(registry, "invoices", "due_at", filterable=False)
    assert codes(
        reg,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "paid_at", "op": "gt", "other_field": "due_at"}],
    ) == ["not_filterable"]


def test_rule_not_aggregatable(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "sum", "field": "id"}],
    ) == ["not_aggregatable"]


def test_count_works_on_non_aggregatable_fields(registry: Registry) -> None:
    assert check(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count_distinct", "field": "technician_id"}],
    ).ok


@pytest.mark.parametrize(
    "metric",
    [
        {"agg": "sum", "field": "customers.name"},
        {"agg": "avg", "field": "customers.created_at"},
        {"agg": "max", "field": "customers.is_active"},
    ],
)
def test_rule_aggregate_type(registry: Registry, metric: dict[str, Any]) -> None:
    assert codes(registry, intent_type="summary", entity="customers", metrics=[metric]) == [
        "aggregate_type"
    ]


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "name", "op": "gt", "value": "M"},
        {"field": "is_active", "op": "between", "values": [False, True]},
        {"field": "id", "op": "ilike_contains", "value": "1"},
    ],
)
def test_rule_operator_type(registry: Registry, condition: dict[str, Any]) -> None:
    assert codes(
        registry, intent_type="summary", entity="customers", metrics=COUNT, filters=[condition]
    ) == ["operator_type"]


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "id", "op": "eq", "value": "seven"},
        {"field": "id", "op": "eq", "value": True},
        {"field": "id", "op": "eq", "value": 7.5},
        {"field": "is_active", "op": "eq", "value": "yes"},
        {"field": "name", "op": "eq", "value": 3},
        {"field": "created_at", "op": "gt", "value": "last tuesday"},
        {"field": "created_at", "op": "gt", "value": 20250101},
        {"field": "name", "op": "ilike_contains", "value": ""},
        {"field": "id", "op": "in", "values": [1, "two"]},
    ],
)
def test_rule_value_type(registry: Registry, condition: dict[str, Any]) -> None:
    assert codes(
        registry, intent_type="summary", entity="customers", metrics=COUNT, filters=[condition]
    ) == ["value_type"]


def test_value_types_that_pass(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[
            {"field": "amount", "op": "gt", "value": 10},
            {"field": "amount", "op": "lt", "value": 99.5},
            {"field": "issued_at", "op": "gte", "value": "2025-01-01"},
            {"field": "work_orders.opened_at", "op": "lt", "value": "2025-01-01T08:00:00+02:00"},
        ],
    )
    values = [p.values[0] for p in plan.where if isinstance(p, Predicate)]
    assert values == [10, 99.5, date(2025, 1, 1), datetime(2025, 1, 1, 6, 0)]
    with pytest.raises(AssertionError):
        plan_of(
            registry,
            intent_type="summary",
            entity="work_orders",
            metrics=COUNT,
            filters=[{"field": "opened_at", "op": "gt", "value": "2025-13-45T00:00"}],
        )


@pytest.mark.parametrize(
    "item",
    [
        {"field": "status", "op": "in", "value": "open"},
        {"field": "id", "op": "between", "values": [1]},
        {"field": "id", "op": "between", "value": 1},
        {"field": "status", "op": "eq", "values": ["open"]},
        {"field": "status", "op": "eq"},
        {"field": "status", "op": "is_null", "value": "yes"},
        {"field": "status", "op": "is_null", "values": [True]},
        {"field": "opened_at", "op": "in", "other_field": "completed_at"},
        {"field": "opened_at", "op": "lt", "value": "2025-01-01", "other_field": "completed_at"},
        {
            "any_of": [{"field": "status", "op": "eq", "value": "open"}],
            "all_of": [{"field": "status", "op": "eq", "value": "open"}],
        },
        {},
        {"any_of": []},
    ],
)
def test_rule_value_shape(registry: Registry, item: dict[str, Any]) -> None:
    assert codes(
        registry, intent_type="summary", entity="work_orders", metrics=COUNT, filters=[item]
    ) == ["value_shape"]


def test_rule_value_shape_in_metrics_and_having(registry: Registry) -> None:
    assert codes(
        registry, intent_type="summary", entity="work_orders", metrics=[{"agg": "sum"}]
    ) == ["value_shape"]
    base: dict[str, Any] = {
        "intent_type": "grouped_summary",
        "entity": "work_orders",
        "metrics": [{"agg": "count", "alias": "n"}],
        "group_by": [{"field": "status"}],
    }
    for having in (
        {"metric": "n", "op": "between", "values": [1]},
        {"metric": "n", "op": "gt"},
        {"metric": "n", "op": "gt", "value": 1, "values": [1, 2]},
    ):
        assert codes(registry, **base, having=[having]) == ["value_shape"]


def test_rule_value_not_allowed(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[{"field": "status", "op": "eq", "value": "teleported"}],
    ) == ["value_not_allowed"]
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[{"field": "priority", "op": "in", "values": ["high", "critical"]}],
    ) == ["value_not_allowed"]


def test_categorical_values_are_case_insensitive_and_alias_resolved(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[
            {"field": "status", "op": "eq", "value": "Done"},
            {"field": "sites.state", "op": "in", "values": ["Texas", "ca"]},
            {"field": "job_type", "op": "neq", "value": "REPAIR"},
            # ilike_contains is free text: no allowed-value check.
            {"field": "priority", "op": "ilike_contains", "value": "urg"},
        ],
    )
    assert [p.values for p in plan.where if isinstance(p, Predicate)] == [
        ("completed",),
        ("TX", "CA"),
        ("repair",),
        ("urg",),
    ]


def test_rule_column_comparison_type(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "paid_at", "op": "gt", "other_field": "amount"}],
    ) == ["column_comparison_type"]


def test_column_comparison_across_a_join(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[
            {"field": "paid_at", "op": "gt", "other_field": "due_at"},
            {"field": "issued_at", "op": "gte", "other_field": "work_orders.completed_at"},
        ],
    )
    first, second = plan.where
    assert isinstance(first, Predicate)
    assert isinstance(second, Predicate)
    assert first.other is not None
    assert first.other.name == "due_at"
    assert second.other is not None
    assert second.other.entity == "work_orders"


def test_column_comparison_respects_fan_out(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[{"field": "completed_at", "op": "lt", "other_field": "invoices.issued_at"}],
    ) == ["fan_out"]


def test_rule_empty_in(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[{"field": "status", "op": "in", "values": []}],
    ) == ["empty_in"]


def test_rule_reversed_between(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "amount", "op": "between", "values": [500, 100]}],
    ) == ["reversed_between"]
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        date_range={"field": "issued_at", "start": "2026-01-01", "end": "2025-01-01"},
    ) == ["reversed_between"]
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="invoices",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "status"}],
        having=[{"metric": "n", "op": "between", "values": [9, 1]}],
    ) == ["reversed_between"]


def test_between_with_equal_bounds_is_allowed(registry: Registry) -> None:
    assert check(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "amount", "op": "between", "values": [100, 100]}],
    ).ok


def test_rule_date_range_field_type(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        date_range={"field": "amount", "relative": "last_month"},
    ) == ["date_range_field_type"]


def test_rule_date_range_duplicate(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "issued_at", "op": "gte", "value": "2025-01-01"}],
        date_range={"field": "issued_at", "relative": "last_year"},
    ) == ["date_range_duplicate"]
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"any_of": [{"field": "issued_at", "op": "lt", "value": "2025-01-01"}]}],
        date_range={"field": "issued_at", "relative": "last_year"},
    ) == ["date_range_duplicate"]


@pytest.mark.parametrize(
    "date_range",
    [
        {"field": "issued_at", "relative": "last_n_days"},
        {"field": "issued_at", "relative": "last_n_days", "n": 0},
        {"field": "issued_at", "relative": "last_month", "n": 2},
        {"field": "issued_at"},
        {"field": "issued_at", "relative": "last_month", "start": "2025-01-01"},
        {"field": "issued_at", "start": "2025-01-01"},
        {"field": "issued_at", "start": "2025-01-01", "end": "2025-02-01", "n": 3},
        {"field": "issued_at", "start": "January", "end": "2025-02-01"},
    ],
)
def test_rule_invalid_date_range(registry: Registry, date_range: dict[str, Any]) -> None:
    assert codes(
        registry, intent_type="summary", entity="invoices", metrics=COUNT, date_range=date_range
    ) == ["invalid_date_range"]


def test_date_range_resolves_against_reference_time(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        date_range={"field": "issued_at", "relative": "last_quarter"},
    )
    assert [(p.op, p.values) for p in plan.where if isinstance(p, Predicate)] == [
        ("gte", (date(2026, 1, 1),)),
        ("lt", (date(2026, 4, 1),)),
    ]
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        date_range={"field": "opened_at", "relative": "last_n_days", "n": 90},
    )
    assert [p.values for p in plan.where if isinstance(p, Predicate)] == [
        (datetime(2026, 4, 1),),
        (datetime(2026, 6, 30),),
    ]


def test_date_range_on_a_date_field_includes_a_partial_last_day(registry: Registry) -> None:
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": COUNT,
            "date_range": {"field": "issued_at", "relative": "last_n_days", "n": 1},
        }
    )
    result = validate(intent, registry, now=datetime(2026, 6, 30, 15, 30))
    assert result.plan is not None
    assert [p.values for p in result.plan.where if isinstance(p, Predicate)] == [
        (date(2026, 6, 29),),
        (date(2026, 7, 1),),
    ]


def test_rule_grain_type(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=COUNT,
        group_by=[{"field": "status", "grain": "month"}],
    ) == ["grain_type"]


def test_rule_having_without_group_by(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "n"}],
        having=[{"metric": "n", "op": "gt", "value": 3}],
    ) == ["having_without_group_by"]


def test_rule_unknown_metric(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=COUNT,
        group_by=[{"field": "status"}],
        having=[{"metric": "total", "op": "gt", "value": 3}],
    ) == ["unknown_metric"]


def test_rule_invalid_alias(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "Total Orders"}],
    ) == ["invalid_alias"]


def test_rule_duplicate_alias(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=[{"agg": "count", "alias": "x"}, {"agg": "sum", "field": "amount", "alias": "x"}],
    ) == ["duplicate_alias"]


def test_default_metric_labels_never_collide(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=[{"agg": "count"}, {"agg": "count"}, {"agg": "sum", "field": "amount"}],
    )
    assert [m.label for m in plan.metrics] == ["count", "count_2", "sum_amount"]


def test_rule_invalid_order_by(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=COUNT,
        group_by=[{"field": "priority"}],
        order_by=[{"target": "status"}],
    ) == ["invalid_order_by"]


def test_order_by_metric_group_label_and_field(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "opened_at", "grain": "month"}, {"field": "sites.state"}],
        order_by=[
            {"target": "n", "direction": "desc"},
            {"target": "opened_at_month"},
            {"target": "sites.state"},
        ],
    )
    assert [(o.label, o.direction) for o in plan.order_by] == [
        ("n", "desc"),
        ("opened_at_month", "asc"),
        ("sites__state", "asc"),
    ]
    rows = plan_of(
        registry,
        intent_type="row_list",
        entity="technicians",
        select=["full_name"],
        order_by=[{"target": "hourly_rate", "direction": "desc"}],
    )
    assert rows.order_by[0].field is not None
    assert rows.order_by[0].field.name == "hourly_rate"


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_rule_limit_out_of_range(registry: Registry, limit: int) -> None:
    assert codes(
        registry, intent_type="row_list", entity="parts", select=["name"], limit=limit
    ) == ["limit_out_of_range"]


def test_limit_at_the_cap_is_allowed(registry: Registry) -> None:
    assert check(
        registry, row_cap=50, intent_type="row_list", entity="parts", select=["name"], limit=50
    ).ok


# --- valid intents and resolution ---


def test_unanswerable_is_a_refusal_not_an_error(registry: Registry) -> None:
    result = check(registry, intent_type="unanswerable", unanswerable_reason="no competitor data")
    assert result.ok
    assert result.plan is None
    assert result.refusal_reason == "no competitor data"


def test_entity_and_field_aliases_resolve(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="Jobs",
        metrics=[{"agg": "sum", "field": "hours"}],
        filters=[{"field": "Techs.Seniority", "op": "eq", "value": "senior"}],
    )
    assert plan.base_entity == "work_orders"
    assert plan.metrics[0].field is not None
    assert plan.metrics[0].field.name == "labor_hours"
    first = plan.where[0]
    assert isinstance(first, Predicate)
    assert first.field.key == ("technicians", "skill_level")


def test_filter_groups_and_is_null(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[
            {
                "any_of": [
                    {"field": "priority", "op": "eq", "value": "urgent"},
                    {"field": "technician_id", "op": "is_null"},
                ]
            },
            {"all_of": [{"field": "completed_at", "op": "is_null", "value": False}]},
        ],
    )
    group, other = plan.where
    assert isinstance(group, PredicateGroup)
    assert group.mode == "any_of"
    assert group.predicates[1].values == (True,)
    assert isinstance(other, PredicateGroup)
    assert other.predicates[0].values == (False,)


def test_a_group_with_one_bad_condition_is_rejected_whole(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        filters=[
            {
                "any_of": [
                    {"field": "priority", "op": "eq", "value": "urgent"},
                    {"field": "mileage", "op": "gt", "value": 3},
                ]
            }
        ],
    ) == ["unknown_field"]


def test_joins_are_shared_and_many_to_one(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="row_list",
        entity="work_orders",
        select=["id", "sites.city", "customers.name", "sites.state", "technicians.full_name"],
    )
    assert [(j.alias, j.parent_alias, j.table) for j in plan.joins] == [
        ("t1", "t0", "sites"),
        ("t2", "t1", "customers"),
        ("t3", "t0", "technicians"),
    ]
    assert [f.label for f in plan.select] == [
        "id",
        "sites__city",
        "customers__name",
        "sites__state",
        "technicians__full_name",
    ]


def test_self_references_are_ignored_for_paths() -> None:
    reg = make_registry(
        {"employees": ["manager_id", "dept_id"], "depts": ["budget"]},
        [("employees", "manager_id", "employees", "id"), ("employees", "dept_id", "depts", "id")],
    )
    plan = plan_of(reg, intent_type="row_list", entity="employees", select=["depts.budget"])
    assert len(plan.joins) == 1


def test_multiple_issues_are_all_reported(registry: Registry) -> None:
    result = check(
        registry,
        intent_type="row_list",
        entity="users",
        select=["email", "mileage"],
        limit=0,
    )
    assert result.codes == ["hidden_field", "unknown_field", "limit_out_of_range"]
    assert all(issue.location for issue in result.issues)


def test_between_values_are_type_checked(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        filters=[{"field": "amount", "op": "between", "values": [1, "lots"]}],
    ) == ["value_type"]


def test_date_range_on_an_unknown_field(registry: Registry) -> None:
    assert codes(
        registry,
        intent_type="summary",
        entity="invoices",
        metrics=COUNT,
        date_range={"field": "sent_at", "relative": "last_month"},
    ) == ["unknown_field"]


def test_absolute_date_range_with_datetimes(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        date_range={"field": "opened_at", "start": "2026-01-01", "end": "2026-01-01T12:00"},
    )
    assert [p.values for p in plan.where if isinstance(p, Predicate)] == [
        (datetime(2026, 1, 1),),
        (datetime(2026, 1, 1, 12),),
    ]


def test_having_between_and_comparison(registry: Registry) -> None:
    plan = plan_of(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "status"}],
        having=[
            {"metric": "n", "op": "between", "values": [10, 500]},
            {"metric": "n", "op": "neq", "value": 41},
        ],
    )
    assert [(h.op, h.values) for h in plan.having] == [("between", (10.0, 500.0)), ("neq", (41,))]


def test_text_and_boolean_column_comparisons(registry: Registry) -> None:
    assert check(
        registry,
        intent_type="summary",
        entity="technicians",
        metrics=COUNT,
        filters=[
            {"field": "home_region", "op": "eq", "other_field": "full_name"},
            {"field": "is_active", "op": "neq", "other_field": "is_active"},
        ],
    ).ok
    assert codes(
        registry,
        intent_type="summary",
        entity="technicians",
        metrics=COUNT,
        filters=[{"field": "is_active", "op": "eq", "other_field": "full_name"}],
    ) == ["column_comparison_type"]


def test_rule_alias_collision(registry: Registry) -> None:
    # A metric alias equal to a group label would shadow the group in ORDER BY.
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "status"}],
        group_by=[{"field": "status"}],
        order_by=[{"target": "work_orders.status"}],
    ) == ["alias_collision"]
    # The same field grouped twice gives two identical labels.
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=COUNT,
        group_by=[{"field": "status"}, {"field": "work_orders.status"}],
    ) == ["alias_collision"]


def test_default_metric_labels_step_around_group_labels() -> None:
    reg = make_registry({"t": ["count"]}, [])
    plan = plan_of(
        reg,
        intent_type="grouped_summary",
        entity="t",
        metrics=[{"agg": "count"}],
        group_by=[{"field": "count"}],
    )
    assert [g.label for g in plan.group_by] == ["count"]
    assert [m.label for m in plan.metrics] == ["count_2"]


def test_rule_ambiguous_value() -> None:
    """Two allowed values differ only by case: an exact match wins, anything else is
    ambiguous rather than silently picking one (PR1 review f6)."""
    from ledgerline.core.registry import EntityDef, FieldDef

    reg = Registry(
        schema_version=1,
        draft=False,
        entities={
            "t": EntityDef(
                table="t",
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "grade": FieldDef(
                        column="grade",
                        type="text",
                        categorical=True,
                        allowed_values=["A", "a", "B"],
                    ),
                },
            )
        },
    )
    exact = plan_of(
        reg,
        intent_type="summary",
        entity="t",
        metrics=COUNT,
        filters=[{"field": "grade", "op": "eq", "value": "a"}],
    )
    first = exact.where[0]
    assert isinstance(first, Predicate)
    assert first.values == ("a",)
    upper = plan_of(
        reg,
        intent_type="summary",
        entity="t",
        metrics=COUNT,
        filters=[{"field": "grade", "op": "eq", "value": "A"}],
    )
    assert isinstance(upper.where[0], Predicate)
    assert upper.where[0].values == ("A",)
    folded = plan_of(
        reg,
        intent_type="summary",
        entity="t",
        metrics=COUNT,
        filters=[{"field": "grade", "op": "eq", "value": "b"}],
    )
    assert isinstance(folded.where[0], Predicate)
    assert folded.where[0].values == ("B",)
    reg2 = with_field(reg, "t", "grade", allowed_values=["Ab", "aB"])
    assert codes(
        reg2,
        intent_type="summary",
        entity="t",
        metrics=COUNT,
        filters=[{"field": "grade", "op": "eq", "value": "ab"}],
    ) == ["ambiguous_value"]


def test_rule_having_type(registry: Registry) -> None:
    """HAVING thresholds are numbers; a min/max over a date cannot take one (f8)."""
    assert codes(
        registry,
        intent_type="grouped_summary",
        entity="invoices",
        metrics=[{"agg": "min", "field": "issued_at", "alias": "first_issued"}],
        group_by=[{"field": "status"}],
        having=[{"metric": "first_issued", "op": "gt", "value": 5}],
    ) == ["having_type"]
    assert check(
        registry,
        intent_type="grouped_summary",
        entity="invoices",
        metrics=[{"agg": "max", "field": "amount", "alias": "top"}],
        group_by=[{"field": "status"}],
        having=[{"metric": "top", "op": "gt", "value": 5}],
    ).ok


# --- v0.2: placeholder reasons ---

PLACEHOLDERS = [
    "",
    "   ",
    "none",
    "None",
    " NULL ",
    "n/a",
    "N/A",
    "na",
    "-",
    "unknown",
    "No reason",
]


@pytest.mark.parametrize("reason", PLACEHOLDERS)
def test_rule_placeholder_reason(registry: Registry, reason: str) -> None:
    refusal = check(registry, intent_type="unanswerable", unanswerable_reason=reason)
    assert refusal.codes == ["placeholder_reason"]
    assert refusal.refusal_reason is None
    answer = check(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        unanswerable_reason=reason,
    )
    assert answer.codes == ["placeholder_reason"]
    assert "leave unanswerable_reason out unless the intent is unanswerable" in (
        answer.issues[0].message
    )


@pytest.mark.parametrize("reason", ["no technician data", "nope", "None of the tables hold it"])
def test_a_real_reason_is_not_a_placeholder(registry: Registry, reason: str) -> None:
    assert check(registry, intent_type="unanswerable", unanswerable_reason=reason).ok
    answer = codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        unanswerable_reason=reason,
    )
    assert answer == ["intent_shape"]


# --- v0.2: ratio metrics ---

TOTAL = {"agg": "count", "alias": "total"}
DONE = {
    "agg": "count",
    "alias": "done",
    "where": [{"field": "status", "op": "eq", "value": "completed"}],
}


@pytest.mark.parametrize(
    "ratio",
    [
        {"agg": "ratio", "alias": "share", "numerator": "missing", "denominator": "total"},
        {"agg": "ratio", "alias": "share", "numerator": "done", "denominator": "missing"},
        {"agg": "ratio", "alias": "share", "numerator": "share", "denominator": "total"},
        {"agg": "ratio", "alias": "share", "numerator": "done", "denominator": "other"},
    ],
)
def test_rule_ratio_ref(registry: Registry, ratio: dict[str, Any]) -> None:
    other = {"agg": "ratio", "alias": "other", "numerator": "done", "denominator": "total"}
    result = check(
        registry, intent_type="summary", entity="work_orders", metrics=[TOTAL, DONE, other, ratio]
    )
    assert result.codes == ["ratio_ref"]


@pytest.mark.parametrize(
    "metric",
    [
        {"agg": "ratio", "numerator": "done"},
        {"agg": "ratio", "denominator": "total"},
        {"agg": "ratio", "numerator": "done", "denominator": "total", "field": "labor_hours"},
        {"agg": "ratio", "numerator": "done", "denominator": "total", "distinct": True},
        {
            "agg": "ratio",
            "numerator": "done",
            "denominator": "total",
            "where": [{"field": "priority", "op": "eq", "value": "urgent"}],
        },
        {"agg": "count", "numerator": "done"},
        {"agg": "sum", "field": "labor_hours", "denominator": "total"},
        {"agg": "count", "as_percent": True},
    ],
)
def test_rule_ratio_shape(registry: Registry, metric: dict[str, Any]) -> None:
    result = check(
        registry, intent_type="summary", entity="work_orders", metrics=[TOTAL, DONE, metric]
    )
    assert result.codes == ["ratio_shape"]


# --- v0.2: date_series ---

OPENED = {"metric": {"agg": "count"}, "date_field": "opened_at", "alias": "opened"}
COMPLETED = {"metric": {"agg": "count"}, "date_field": "completed_at", "alias": "completed"}


def _series(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "intent_type": "date_series",
        "entity": "work_orders",
        "grain": "month",
        "series": [OPENED, COMPLETED],
    }
    base.update(changes)
    return base


@pytest.mark.parametrize(
    "intent",
    [
        _series(grain=None),
        _series(series=[]),
        _series(series=[{**OPENED, "alias": f"s{i}"} for i in range(5)]),
        _series(metrics=COUNT),
        _series(select=["id"]),
        _series(group_by=[{"field": "status"}]),
        _series(having=[{"metric": "opened", "op": "gt", "value": 1}]),
        _series(order_by=[{"target": "opened"}]),
        _series(limit=5),
        _series(date_range={"field": "opened_at", "relative": "last_year"}),
        _series(series=[{**OPENED, "alias": None}]),
        _series(series=[{**OPENED, "metric": {"agg": "count", "alias": "n"}}]),
        _series(
            series=[
                {
                    **OPENED,
                    "metric": {
                        "agg": "count",
                        "where": [{"field": "status", "op": "eq", "value": "open"}],
                    },
                }
            ]
        ),
        _series(
            series=[{**OPENED, "metric": {"agg": "ratio", "numerator": "a", "denominator": "b"}}]
        ),
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": COUNT,
            "group_by": [{"field": "status"}],
            "series": [OPENED],
        },
        {"intent_type": "summary", "entity": "work_orders", "metrics": COUNT, "grain": "month"},
    ],
)
def test_rule_series_shape(registry: Registry, intent: dict[str, Any]) -> None:
    assert codes(registry, **intent) == ["series_shape"]


@pytest.mark.parametrize("date_field", ["labor_hours", "status", "sites.name"])
def test_rule_series_date_field(registry: Registry, date_field: str) -> None:
    intent = _series(series=[OPENED, {**COMPLETED, "date_field": date_field}])
    assert codes(registry, **intent) == ["series_date_field"]


@pytest.mark.parametrize(
    ("series", "code"),
    [
        ({**COMPLETED, "alias": "opened"}, "duplicate_alias"),
        ({**COMPLETED, "alias": "period"}, "alias_collision"),
        ({**COMPLETED, "alias": "Bad Alias"}, "invalid_alias"),
        ({**COMPLETED, "date_field": "work_order_parts.quantity"}, "fan_out"),
        ({**COMPLETED, "date_field": "mileage_at"}, "unknown_field"),
        ({**COMPLETED, "metric": {"agg": "sum", "field": "status"}}, "aggregate_type"),
        (
            {**COMPLETED, "where": [{"field": "status", "op": "eq", "value": "lost"}]},
            "value_not_allowed",
        ),
    ],
)
def test_series_reuse_the_existing_rules(
    registry: Registry, series: dict[str, Any], code: str
) -> None:
    assert codes(registry, **_series(series=[OPENED, series])) == [code]


def test_a_date_range_outside_date_series_still_needs_a_field(registry: Registry) -> None:
    result = codes(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=COUNT,
        date_range={"relative": "last_year"},
    )
    assert result == ["invalid_date_range"]
