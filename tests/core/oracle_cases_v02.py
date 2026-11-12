"""Differential oracle, grammar v0.2: hand-written intents with conditional and ratio
metrics (and, from Phase 2, date series), each with a reference query written by hand
from the question, not from the builder's output. Postgres. Reference time
2026-06-30T00:00Z."""

from __future__ import annotations

from typing import Any


def _count(alias: str, *where: dict[str, Any]) -> dict[str, Any]:
    return {"agg": "count", "alias": alias, "where": list(where)}


def _ratio(alias: str, numerator: str, denominator: str, pct: bool = False) -> dict[str, Any]:
    return {
        "agg": "ratio",
        "alias": alias,
        "numerator": numerator,
        "denominator": denominator,
        "as_percent": pct,
    }


def _eq(field: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": "eq", "value": value}


TOTAL = {"agg": "count", "alias": "total"}

RATIO_CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "v01_cancelled_share_overall",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [
                _count("cancelled", _eq("status", "cancelled")),
                TOTAL,
                _ratio("pct_cancelled", "cancelled", "total", pct=True),
            ],
        },
        "SELECT count(*) FILTER (WHERE status = 'cancelled'), count(*), "
        "100.0 * count(*) FILTER (WHERE status = 'cancelled') / count(*) FROM work_orders",
    ),
    (
        "v02_completed_share_by_job_type",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                _count("done", _eq("status", "completed")),
                TOTAL,
                _ratio("share_done", "done", "total"),
            ],
            "group_by": [{"field": "job_type"}],
        },
        "SELECT job_type, sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), count(*), "
        "sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)::float / count(*) "
        "FROM work_orders GROUP BY job_type",
    ),
    (
        "v03_overdue_share_by_month_2025",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [
                _count("overdue", _eq("status", "overdue")),
                TOTAL,
                _ratio("pct_overdue", "overdue", "total", pct=True),
            ],
            "group_by": [{"field": "issued_at", "grain": "month"}],
            "date_range": {"field": "issued_at", "start": "2025-01-01", "end": "2026-01-01"},
            "order_by": [{"target": "issued_at_month"}],
        },
        "SELECT CAST(date_trunc('month', issued_at) AS DATE) AS m, "
        "count(*) FILTER (WHERE status = 'overdue'), count(*), "
        "100.0 * count(*) FILTER (WHERE status = 'overdue') / count(*) "
        "FROM invoices WHERE issued_at >= DATE '2025-01-01' AND issued_at < DATE '2026-01-01' "
        "GROUP BY m ORDER BY m",
    ),
    (
        "v04_share_as_fraction_and_percent",
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [
                _count("paid", _eq("status", "paid")),
                TOTAL,
                _ratio("paid_fraction", "paid", "total"),
                _ratio("paid_percent", "paid", "total", pct=True),
            ],
        },
        "SELECT (SELECT count(*) FROM invoices WHERE status = 'paid'), "
        "(SELECT count(*) FROM invoices), "
        "(SELECT count(*) FROM invoices WHERE status = 'paid')::float "
        "/ (SELECT count(*) FROM invoices), "
        "(SELECT count(*) FROM invoices WHERE status = 'paid') * 100.0 "
        "/ (SELECT count(*) FROM invoices)",
    ),
    (
        "v05_zero_denominator_is_null",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                TOTAL,
                _count("cancelled", _eq("status", "cancelled")),
                _ratio("per_cancelled", "total", "cancelled"),
            ],
            "group_by": [{"field": "status"}],
        },
        "SELECT status, count(*), "
        "CASE WHEN status = 'cancelled' THEN count(*) ELSE 0 END, "
        "CASE WHEN status = 'cancelled' THEN 1.0 ELSE NULL END "
        "FROM work_orders GROUP BY status",
    ),
    (
        "v06_paid_share_of_invoiced_amount",
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [
                {
                    "agg": "sum",
                    "field": "amount",
                    "alias": "paid",
                    "where": [_eq("status", "paid")],
                },
                {"agg": "sum", "field": "amount", "alias": "billed"},
                _ratio("pct_paid", "paid", "billed", pct=True),
            ],
        },
        "WITH p AS (SELECT sum(amount) AS a FROM invoices WHERE status = 'paid'), "
        "b AS (SELECT sum(amount) AS a FROM invoices) "
        "SELECT p.a, b.a, 100 * p.a::float / b.a::float FROM p, b",
    ),
    (
        "v07_states_with_many_urgent_orders",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [_count("urgent", _eq("priority", "urgent")), TOTAL],
            "group_by": [{"field": "sites.state"}],
            "having": [{"metric": "urgent", "op": "gte", "value": 5}],
        },
        "SELECT s.state, count(*) FILTER (WHERE w.priority = 'urgent'), count(*) "
        "FROM work_orders w JOIN sites s ON s.id = w.site_id GROUP BY s.state "
        "HAVING count(*) FILTER (WHERE w.priority = 'urgent') >= 5",
    ),
    (
        "v08_senior_share_by_job_type_across_a_join",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                _count("senior", _eq("technicians.skill_level", "senior")),
                TOTAL,
                _ratio("pct_senior", "senior", "total", pct=True),
            ],
            "group_by": [{"field": "job_type"}],
            "order_by": [{"target": "pct_senior", "direction": "desc"}],
        },
        # Unassigned work orders stay in the total: the technician join is outer.
        "SELECT w.job_type, count(*) FILTER (WHERE t.skill_level = 'senior'), count(*), "
        "100.0 * count(*) FILTER (WHERE t.skill_level = 'senior') / count(*) AS pct "
        "FROM work_orders w LEFT JOIN technicians t ON t.id = w.technician_id "
        "GROUP BY w.job_type ORDER BY pct DESC",
    ),
]


# NULL placement in ORDER BY must be the same on both engines.
ORDER_CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "v13_null_ratios_sort_last_descending",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                _count("urgent", _eq("priority", "urgent")),
                _count("dropped", _eq("status", "cancelled")),
                _ratio("urgent_per_dropped", "urgent", "dropped"),
            ],
            "group_by": [{"field": "status"}],
            "order_by": [
                {"target": "urgent_per_dropped", "direction": "desc"},
                {"target": "status"},
            ],
        },
        # Only the cancelled group has a denominator; the other four are NULL and last.
        "SELECT status, count(*) FILTER (WHERE priority = 'urgent'), "
        "count(*) FILTER (WHERE status = 'cancelled'), "
        "count(*) FILTER (WHERE priority = 'urgent')::float "
        "/ NULLIF(count(*) FILTER (WHERE status = 'cancelled'), 0) AS r "
        "FROM work_orders GROUP BY status ORDER BY r DESC NULLS LAST, status NULLS LAST",
    )
]


SERIES_CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "v09_opened_and_completed_by_month_2025",
        {
            "intent_type": "date_series",
            "entity": "work_orders",
            "grain": "month",
            "date_range": {"start": "2025-01-01", "end": "2026-01-01"},
            "series": [
                {"metric": {"agg": "count"}, "date_field": "opened_at", "alias": "opened"},
                {"metric": {"agg": "count"}, "date_field": "completed_at", "alias": "completed"},
            ],
        },
        "WITH o AS (SELECT date_trunc('month', opened_at)::date AS p, count(*) AS n "
        "FROM work_orders WHERE opened_at >= '2025-01-01' AND opened_at < '2026-01-01' "
        "GROUP BY 1), "
        "c AS (SELECT date_trunc('month', completed_at)::date AS p, count(*) AS n "
        "FROM work_orders WHERE completed_at >= '2025-01-01' AND completed_at < '2026-01-01' "
        "GROUP BY 1) "
        "SELECT coalesce(o.p, c.p) AS p, coalesce(o.n, 0), coalesce(c.n, 0) "
        "FROM o FULL OUTER JOIN c ON o.p = c.p ORDER BY p",
    ),
    (
        "v10_issued_count_and_paid_amount_by_quarter",
        {
            "intent_type": "date_series",
            "entity": "invoices",
            "grain": "quarter",
            "filters": [{"field": "status", "op": "neq", "value": "void"}],
            "series": [
                {"metric": {"agg": "count"}, "date_field": "issued_at", "alias": "issued"},
                {
                    "metric": {"agg": "sum", "field": "amount"},
                    "date_field": "paid_at",
                    "where": [{"field": "status", "op": "eq", "value": "paid"}],
                    "alias": "paid_amount",
                },
            ],
        },
        "WITH i AS (SELECT date_trunc('quarter', issued_at)::date AS p, count(*) AS n "
        "FROM invoices WHERE status <> 'void' GROUP BY 1), "
        "pd AS (SELECT date_trunc('quarter', paid_at)::date AS p, sum(amount) AS s "
        "FROM invoices WHERE status <> 'void' AND status = 'paid' AND paid_at IS NOT NULL "
        "GROUP BY 1) "
        "SELECT coalesce(i.p, pd.p) AS p, coalesce(i.n, 0), pd.s "
        "FROM i FULL OUTER JOIN pd ON i.p = pd.p ORDER BY p",
    ),
    (
        "v11_weeks_with_no_urgent_installations",
        {
            "intent_type": "date_series",
            "entity": "work_orders",
            "grain": "iso_week",
            "date_range": {"start": "2025-01-06", "end": "2025-04-07"},
            "series": [
                {"metric": {"agg": "count"}, "date_field": "opened_at", "alias": "opened"},
                {
                    "metric": {"agg": "count"},
                    "date_field": "completed_at",
                    "where": [
                        {"field": "priority", "op": "eq", "value": "urgent"},
                        {"field": "job_type", "op": "eq", "value": "installation"},
                    ],
                    "alias": "urgent_installs",
                },
            ],
        },
        # Every week in the range has opened work orders, so the opened weeks are all
        # the periods.
        "WITH o AS (SELECT date_trunc('week', opened_at)::date AS p, count(*) AS n "
        "FROM work_orders WHERE opened_at >= '2025-01-06' AND opened_at < '2025-04-07' "
        "GROUP BY 1) "
        "SELECT o.p, o.n, (SELECT count(*) FROM work_orders u WHERE u.priority = 'urgent' "
        "AND u.job_type = 'installation' AND u.completed_at >= '2025-01-06' "
        "AND u.completed_at < '2025-04-07' "
        "AND date_trunc('week', u.completed_at)::date = o.p) "
        "FROM o ORDER BY o.p",
    ),
    (
        "v12_invoices_by_issue_and_work_order_open_date",
        {
            "intent_type": "date_series",
            "entity": "invoices",
            "grain": "year",
            "series": [
                {"metric": {"agg": "count"}, "date_field": "issued_at", "alias": "by_issue"},
                {
                    "metric": {"agg": "sum", "field": "amount"},
                    "date_field": "work_orders.opened_at",
                    "alias": "amount_by_open",
                },
            ],
        },
        "WITH a AS (SELECT date_trunc('year', issued_at)::date AS p, count(*) AS n "
        "FROM invoices GROUP BY 1), "
        "b AS (SELECT date_trunc('year', w.opened_at)::date AS p, sum(i.amount) AS s "
        "FROM invoices i JOIN work_orders w ON w.id = i.work_order_id GROUP BY 1) "
        "SELECT coalesce(a.p, b.p) AS p, coalesce(a.n, 0), b.s "
        "FROM a FULL OUTER JOIN b ON a.p = b.p ORDER BY p",
    ),
]
