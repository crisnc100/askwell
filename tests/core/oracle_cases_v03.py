"""Differential oracle, grammar v0.3: computed values, durations, has / has none and
comparison with an aggregate. Each intent's reference query is written by hand from the
question, not from the builder's output. Postgres. Reference time 2026-06-30T00:00Z."""

from __future__ import annotations

from typing import Any

NOW_SQL = "TIMESTAMP '2026-06-30 00:00:00'"
DAYS = "EXTRACT(EPOCH FROM ({end} - {start})) / 86400.0"

# (id, intent, reference SQL, whether the reference may return no rows)
CASES: list[tuple[str, dict[str, Any], str, bool]] = [
    (
        "c01_part_revenue_across_a_join",
        {
            "intent_type": "summary",
            "entity": "work_order_parts",
            "metrics": [
                {
                    "agg": "sum",
                    "field": {"op": "multiply", "left": "quantity", "right": "parts.unit_price"},
                }
            ],
        },
        "SELECT sum(wop.quantity * p.unit_price) FROM work_order_parts wop "
        "JOIN parts p ON p.id = wop.part_id",
        False,
    ),
    (
        "c02_top_margin_parts",
        {
            "intent_type": "row_list",
            "entity": "parts",
            "select": [
                "name",
                {"op": "subtract", "left": "unit_price", "right": "unit_cost", "alias": "margin"},
            ],
            "order_by": [{"target": "margin", "direction": "desc"}],
            "limit": 5,
        },
        "SELECT name, unit_price - unit_cost AS margin FROM parts ORDER BY margin DESC, id LIMIT 5",
        False,
    ),
    (
        "c03_lines_worth_over_500",
        {
            "intent_type": "summary",
            "entity": "work_order_parts",
            "metrics": [{"agg": "count"}],
            "filters": [
                {
                    "field": {"op": "multiply", "left": "quantity", "right": "parts.unit_price"},
                    "op": "gt",
                    "value": 500,
                }
            ],
        },
        "SELECT count(*) FROM work_order_parts wop JOIN parts p ON p.id = wop.part_id "
        "WHERE wop.quantity * p.unit_price > 500",
        False,
    ),
    (
        "d01_average_days_to_complete_by_job_type",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [{"agg": "avg", "field": {"days_between": ["opened_at", "completed_at"]}}],
            "group_by": [{"field": "job_type"}],
            "filters": [{"field": "status", "op": "eq", "value": "completed"}],
        },
        "SELECT job_type, avg("
        + DAYS.format(start="opened_at", end="completed_at")
        + ") FROM work_orders WHERE status = 'completed' GROUP BY job_type",
        False,
    ),
    (
        "d02_unpaid_invoices_older_than_three_weeks",
        {
            "intent_type": "row_list",
            "entity": "invoices",
            "select": ["id", {"days_between": ["issued_at", "now"], "alias": "age_days"}],
            "filters": [
                {"field": "status", "op": "eq", "value": "unpaid"},
                {"field": {"days_between": ["issued_at", "now"]}, "op": "gt", "value": 21},
            ],
            "order_by": [{"target": "age_days", "direction": "desc"}],
        },
        "SELECT id, "
        + DAYS.format(start="CAST(issued_at AS TIMESTAMP)", end=NOW_SQL)
        + " AS age FROM invoices WHERE status = 'unpaid' AND "
        + DAYS.format(start="CAST(issued_at AS TIMESTAMP)", end=NOW_SQL)
        + " > 21 ORDER BY age DESC, id",
        False,
    ),
    (
        "h01_customers_with_a_site_in_ca",
        {
            "intent_type": "summary",
            "entity": "customers",
            "metrics": [{"agg": "count"}],
            "filters": [{"has": "sites", "where": [{"field": "state", "op": "eq", "value": "CA"}]}],
        },
        "SELECT count(*) FROM customers c WHERE EXISTS "
        "(SELECT 1 FROM sites s WHERE s.customer_id = c.id AND s.state = 'CA')",
        False,
    ),
    (
        "h02_technicians_with_no_work_orders",
        {
            "intent_type": "row_list",
            "entity": "technicians",
            "select": ["full_name"],
            "filters": [{"has": "work_orders", "none": True}],
        },
        "SELECT full_name FROM technicians t WHERE NOT EXISTS "
        "(SELECT 1 FROM work_orders w WHERE w.technician_id = t.id)",
        True,
    ),
    (
        "h03_completed_jobs_with_no_overdue_invoice_by_region",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count", "alias": "n"}],
            "group_by": [{"field": "customers.region"}],
            "filters": [
                {"field": "status", "op": "eq", "value": "completed"},
                {
                    "has": "invoices",
                    "none": True,
                    "where": [{"field": "status", "op": "eq", "value": "overdue"}],
                },
            ],
        },
        "SELECT c.region, count(*) FROM work_orders w JOIN sites s ON s.id = w.site_id "
        "JOIN customers c ON c.id = s.customer_id WHERE w.status = 'completed' AND NOT EXISTS "
        "(SELECT 1 FROM invoices i WHERE i.work_order_id = w.id AND i.status = 'overdue') "
        "GROUP BY c.region",
        False,
    ),
    (
        "h04_parts_used_on_a_repair_by_a_senior",
        {
            "intent_type": "summary",
            "entity": "parts",
            "metrics": [{"agg": "count"}],
            "filters": [
                {
                    "has": "work_order_parts",
                    "where": [
                        {"field": "work_orders.job_type", "op": "eq", "value": "repair"},
                        {"field": "technicians.skill_level", "op": "eq", "value": "senior"},
                    ],
                }
            ],
        },
        "SELECT count(*) FROM parts p WHERE EXISTS (SELECT 1 FROM work_order_parts x "
        "JOIN work_orders w ON w.id = x.work_order_id "
        "JOIN technicians t ON t.id = w.technician_id "
        "WHERE x.part_id = p.id AND w.job_type = 'repair' AND t.skill_level = 'senior')",
        False,
    ),
    (
        "a01_repairs_longer_than_average_this_half",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count"}],
            "filters": [
                {"field": "job_type", "op": "eq", "value": "repair"},
                {"field": "labor_hours", "op": "gt", "value": {"of": "avg"}},
            ],
            "date_range": {"field": "opened_at", "start": "2026-01-01", "end": "2026-07-01"},
        },
        "SELECT count(*) FROM work_orders w WHERE job_type = 'repair' "
        "AND opened_at >= '2026-01-01' AND opened_at < '2026-07-01' AND labor_hours > "
        "(SELECT avg(labor_hours) FROM work_orders WHERE job_type = 'repair' "
        "AND opened_at >= '2026-01-01' AND opened_at < '2026-07-01')",
        False,
    ),
    (
        "a02_smallest_overdue_invoices",
        {
            "intent_type": "row_list",
            "entity": "invoices",
            "select": ["id", "amount"],
            "filters": [
                {"field": "status", "op": "eq", "value": "overdue"},
                {"field": "amount", "op": "eq", "value": {"of": "min"}},
            ],
        },
        "SELECT id, amount FROM invoices WHERE status = 'overdue' AND amount = "
        "(SELECT min(amount) FROM invoices WHERE status = 'overdue') ORDER BY id",
        False,
    ),
]
