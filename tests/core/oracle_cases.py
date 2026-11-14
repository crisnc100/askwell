"""The differential oracle: 30 hand-written intents, each with a hand-written reference
query (Postgres) whose rows are the expected answer. The reference SQL is written from
the question, not from the builder's output. Reference time 2026-06-30T00:00Z."""

from __future__ import annotations

from typing import Any

C: list[dict[str, Any]] = [{"agg": "count", "alias": "n"}]

CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "o01_orders_last_month",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": C,
            "date_range": {"field": "opened_at", "relative": "last_month"},
        },
        "SELECT count(*) FROM work_orders "
        "WHERE opened_at >= '2026-05-01' AND opened_at < '2026-06-01'",
    ),
    (
        "o02_overdue_total",
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [{"agg": "sum", "field": "amount"}],
            "filters": [{"field": "status", "op": "eq", "value": "overdue"}],
        },
        "SELECT sum(amount) FROM invoices WHERE status = 'overdue'",
    ),
    (
        "o03_rate_by_skill",
        {
            "intent_type": "grouped_summary",
            "entity": "technicians",
            "metrics": [{"agg": "avg", "field": "hourly_rate"}],
            "group_by": [{"field": "skill_level"}],
        },
        "SELECT skill_level, avg(hourly_rate) FROM technicians GROUP BY skill_level",
    ),
    (
        "o04_job_types_last_year",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": C,
            "group_by": [{"field": "job_type"}],
            "date_range": {"field": "opened_at", "relative": "last_year"},
        },
        "SELECT job_type, count(*) FROM work_orders "
        "WHERE opened_at >= '2025-01-01' AND opened_at < '2026-01-01' GROUP BY job_type",
    ),
    (
        "o05_monthly_invoiced_2025",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [{"agg": "sum", "field": "amount"}],
            "filters": [{"field": "status", "op": "neq", "value": "void"}],
            "group_by": [{"field": "issued_at", "grain": "month"}],
            "date_range": {"field": "issued_at", "start": "2025-01-01", "end": "2026-01-01"},
            "order_by": [{"target": "issued_at_month"}],
        },
        "SELECT CAST(date_trunc('month', issued_at) AS DATE), sum(amount) FROM invoices "
        "WHERE status <> 'void' AND issued_at >= '2025-01-01' AND issued_at < '2026-01-01' "
        "GROUP BY 1 ORDER BY 1",
    ),
    (
        "o06_top_parts_by_quantity",
        {
            "intent_type": "grouped_summary",
            "entity": "work_order_parts",
            "metrics": [{"agg": "sum", "field": "quantity", "alias": "qty"}],
            "group_by": [{"field": "parts.name"}],
            "order_by": [{"target": "qty", "direction": "desc"}, {"target": "parts.name"}],
            "limit": 5,
        },
        "SELECT p.id, p.name, sum(wp.quantity) AS qty FROM work_order_parts wp "
        "JOIN parts p ON p.id = wp.part_id GROUP BY p.id, p.name "
        "ORDER BY qty DESC, p.name, p.id LIMIT 5",
    ),
    (
        "o07_states_with_25_sites",
        {
            "intent_type": "grouped_summary",
            "entity": "sites",
            "metrics": C,
            "group_by": [{"field": "state"}],
            "having": [{"metric": "n", "op": "gte", "value": 25}],
        },
        "SELECT state, count(*) FROM sites GROUP BY state HAVING count(*) >= 25",
    ),
    (
        "o08_distinct_customers_last_month",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count_distinct", "field": "sites.customer_id"}],
            "date_range": {"field": "opened_at", "relative": "last_month"},
        },
        "SELECT count(DISTINCT s.customer_id) FROM work_orders w JOIN sites s ON s.id = w.site_id "
        "WHERE w.opened_at >= '2026-05-01' AND w.opened_at < '2026-06-01'",
    ),
    (
        "o09_active_west_technicians",
        {
            "intent_type": "row_list",
            "entity": "technicians",
            "select": ["full_name"],
            "filters": [
                {"field": "is_active", "op": "eq", "value": True},
                {"field": "home_region", "op": "eq", "value": "west"},
            ],
            "order_by": [{"target": "full_name"}, {"target": "id"}],
        },
        "SELECT full_name FROM technicians WHERE is_active AND home_region = 'west' "
        "ORDER BY full_name, id",
    ),
    (
        "o10_completed_this_year_by_priority",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": C,
            "group_by": [{"field": "priority"}],
            "filters": [{"field": "status", "op": "eq", "value": "completed"}],
            "date_range": {"field": "completed_at", "relative": "ytd"},
        },
        "SELECT priority, count(*) FROM work_orders WHERE status = 'completed' "
        "AND completed_at >= '2026-01-01' AND completed_at < '2026-06-30' GROUP BY priority",
    ),
    (
        "o11_paid_late_2025",
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": C,
            "filters": [{"field": "paid_at", "op": "gt", "other_field": "due_at"}],
            "date_range": {"field": "issued_at", "relative": "last_year"},
        },
        "SELECT count(*) FROM invoices WHERE paid_at > due_at "
        "AND issued_at >= '2025-01-01' AND issued_at < '2026-01-01'",
    ),
    (
        "o12_top_technicians_by_invoiced",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [{"agg": "sum", "field": "amount", "alias": "invoiced"}],
            "group_by": [{"field": "technicians.full_name"}],
            "filters": [{"field": "status", "op": "neq", "value": "void"}],
            "date_range": {"field": "issued_at", "relative": "last_n_months", "n": 12},
            "order_by": [
                {"target": "invoiced", "direction": "desc"},
                {"target": "technicians.full_name"},
            ],
            "limit": 3,
        },
        "SELECT t.id, t.full_name, sum(i.amount) AS invoiced FROM invoices i "
        "JOIN work_orders w ON w.id = i.work_order_id JOIN technicians t ON t.id = w.technician_id "
        "WHERE i.status <> 'void' AND i.issued_at >= '2025-06-30' AND i.issued_at < '2026-06-30' "
        "GROUP BY t.id, t.full_name ORDER BY invoiced DESC, t.full_name, t.id LIMIT 3",
    ),
    (
        "o13_region_by_quarter_2025",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [{"agg": "sum", "field": "amount"}],
            "group_by": [{"field": "customers.region"}, {"field": "issued_at", "grain": "quarter"}],
            "filters": [{"field": "status", "op": "neq", "value": "void"}],
            "date_range": {"field": "issued_at", "relative": "last_year"},
        },
        "SELECT c.region, CAST(date_trunc('quarter', i.issued_at) AS DATE), sum(i.amount) "
        "FROM invoices i JOIN work_orders w ON w.id = i.work_order_id "
        "JOIN sites s ON s.id = w.site_id JOIN customers c ON c.id = s.customer_id "
        "WHERE i.status <> 'void' AND i.issued_at >= '2025-01-01' AND i.issued_at < '2026-01-01' "
        "GROUP BY 1, 2",
    ),
    (
        "o14_busy_customers",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": C,
            "group_by": [{"field": "customers.name"}],
            "date_range": {"field": "opened_at", "relative": "last_n_months", "n": 12},
            "having": [{"metric": "n", "op": "gt", "value": 15}],
        },
        "SELECT c.id, c.name, count(*) FROM work_orders w JOIN sites s ON s.id = w.site_id "
        "JOIN customers c ON c.id = s.customer_id "
        "WHERE w.opened_at >= '2025-06-30' AND w.opened_at < '2026-06-30' "
        "GROUP BY c.id, c.name HAVING count(*) > 15",
    ),
    (
        "o15_avg_invoice_by_job_type_q1",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [{"agg": "avg", "field": "amount"}, {"agg": "count", "alias": "n"}],
            "group_by": [{"field": "work_orders.job_type"}],
            "date_range": {"field": "work_orders.completed_at", "relative": "last_quarter"},
            "having": [{"metric": "n", "op": "gte", "value": 100}],
        },
        "SELECT w.job_type, avg(i.amount), count(*) FROM invoices i "
        "JOIN work_orders w ON w.id = i.work_order_id "
        "WHERE w.completed_at >= '2026-01-01' AND w.completed_at < '2026-04-01' "
        "GROUP BY w.job_type HAVING count(*) >= 100",
    ),
    (
        "o16_slowest_technician_2025",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                {"agg": "avg", "field": "labor_hours", "alias": "avg_hours"},
                {"agg": "count", "alias": "jobs"},
            ],
            "group_by": [{"field": "technicians.full_name"}],
            "filters": [{"field": "status", "op": "eq", "value": "completed"}],
            "date_range": {"field": "completed_at", "relative": "last_year"},
            "having": [{"metric": "jobs", "op": "gte", "value": 20}],
            "order_by": [
                {"target": "avg_hours", "direction": "desc"},
                {"target": "technicians.full_name"},
            ],
            "limit": 1,
        },
        "SELECT t.id, t.full_name, avg(w.labor_hours) AS avg_hours, count(*) FROM work_orders w "
        "JOIN technicians t ON t.id = w.technician_id WHERE w.status = 'completed' "
        "AND w.completed_at >= '2025-01-01' AND w.completed_at < '2026-01-01' "
        "GROUP BY t.id, t.full_name HAVING count(*) >= 20 "
        "ORDER BY avg_hours DESC, t.full_name, t.id LIMIT 1",
    ),
    (
        "o17_weekly_orders_last_4_weeks",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": C,
            "group_by": [{"field": "opened_at", "grain": "iso_week"}],
            "date_range": {"field": "opened_at", "relative": "last_n_weeks", "n": 4},
            "order_by": [{"target": "opened_at_iso_week"}],
        },
        "SELECT CAST(date_trunc('week', opened_at) AS DATE), count(*) FROM work_orders "
        "WHERE opened_at >= '2026-06-02' AND opened_at < '2026-06-30' GROUP BY 1 ORDER BY 1",
    ),
    (
        "o18_invoice_range_by_status",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [
                {"agg": "min", "field": "amount"},
                {"agg": "max", "field": "amount"},
                {"agg": "max", "field": "issued_at"},
            ],
            "group_by": [{"field": "status"}],
        },
        "SELECT status, min(amount), max(amount), max(issued_at) FROM invoices GROUP BY status",
    ),
    (
        "o19_unassigned_orders",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": C,
            "filters": [{"field": "technician_id", "op": "is_null"}],
        },
        "SELECT count(*) FROM work_orders WHERE technician_id IS NULL",
    ),
    (
        "o20_urgent_or_high_open_work",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": C,
            "group_by": [{"field": "status"}],
            "filters": [
                {
                    "any_of": [
                        {"field": "priority", "op": "eq", "value": "urgent"},
                        {"field": "priority", "op": "eq", "value": "high"},
                    ]
                },
                {
                    "field": "status",
                    "op": "in",
                    "values": ["open", "scheduled", "in_progress", "cancelled"],
                },
            ],
        },
        "SELECT status, count(*) FROM work_orders WHERE (priority = 'urgent' OR priority = 'high') "
        "AND status IN ('open', 'scheduled', 'in_progress', 'cancelled') GROUP BY status",
    ),
    (
        "o21_valve_parts",
        {
            "intent_type": "row_list",
            "entity": "parts",
            "select": ["sku", "name", "unit_price"],
            "filters": [{"field": "name", "op": "ilike_contains", "value": "VALVE"}],
            "order_by": [{"target": "sku"}],
        },
        "SELECT sku, name, unit_price FROM parts WHERE name ILIKE '%valve%' ORDER BY sku",
    ),
    (
        "o22_big_invoices_with_customer",
        {
            "intent_type": "row_list",
            "entity": "invoices",
            "select": ["id", "amount", "customers.name", "sites.city"],
            "filters": [{"field": "amount", "op": "gt", "value": 5000}],
            "order_by": [{"target": "amount", "direction": "desc"}, {"target": "id"}],
            "limit": 10,
        },
        "SELECT i.id, i.amount, c.name, s.city FROM invoices i "
        "JOIN work_orders w ON w.id = i.work_order_id JOIN sites s ON s.id = w.site_id "
        "JOIN customers c ON c.id = s.customer_id WHERE i.amount > 5000 "
        "ORDER BY i.amount DESC, i.id LIMIT 10",
    ),
    (
        "o23_completed_after_scheduled_day",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": C,
            "filters": [{"field": "completed_at", "op": "gt", "other_field": "scheduled_for"}],
        },
        "SELECT count(*) FROM work_orders WHERE completed_at > scheduled_for",
    ),
    (
        "o24_quarterly_labor_2025",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [{"agg": "avg", "field": "labor_hours"}],
            "group_by": [{"field": "opened_at", "grain": "quarter"}],
            "date_range": {"field": "opened_at", "relative": "last_year"},
            "order_by": [{"target": "opened_at_quarter"}],
        },
        "SELECT CAST(date_trunc('quarter', opened_at) AS DATE), avg(labor_hours) FROM work_orders "
        "WHERE opened_at >= '2025-01-01' AND opened_at < '2026-01-01' GROUP BY 1 ORDER BY 1",
    ),
    (
        "o25_customers_by_signup_year",
        {
            "intent_type": "grouped_summary",
            "entity": "customers",
            "metrics": C,
            "group_by": [{"field": "created_at", "grain": "year"}],
            "order_by": [{"target": "created_at_year"}],
        },
        "SELECT CAST(date_trunc('year', created_at) AS DATE), count(*) FROM customers "
        "GROUP BY 1 ORDER BY 1",
    ),
    (
        "o26_daily_invoices_last_week",
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": C,
            "group_by": [{"field": "issued_at", "grain": "day"}],
            "date_range": {"field": "issued_at", "relative": "last_n_days", "n": 7},
            "order_by": [{"target": "issued_at_day"}],
        },
        "SELECT issued_at, count(*) FROM invoices "
        "WHERE issued_at >= '2026-06-23' AND issued_at < '2026-06-30' GROUP BY 1 ORDER BY 1",
    ),
    (
        "o27_repair_parts_by_category",
        {
            "intent_type": "grouped_summary",
            "entity": "work_order_parts",
            "metrics": [{"agg": "sum", "field": "quantity"}],
            "group_by": [{"field": "parts.category"}],
            "filters": [{"field": "work_orders.job_type", "op": "eq", "value": "repair"}],
        },
        "SELECT p.category, sum(wp.quantity) FROM work_order_parts wp "
        "JOIN parts p ON p.id = wp.part_id JOIN work_orders w ON w.id = wp.work_order_id "
        "WHERE w.job_type = 'repair' GROUP BY p.category",
    ),
    (
        "o28_active_customers_by_segment",
        {
            "intent_type": "grouped_summary",
            "entity": "customers",
            "metrics": C,
            "group_by": [{"field": "segment"}],
            "filters": [{"field": "is_active", "op": "eq", "value": True}],
        },
        "SELECT segment, count(*) FROM customers WHERE is_active GROUP BY segment",
    ),
    (
        "o29_hired_2020_to_2022",
        {
            "intent_type": "row_list",
            "entity": "technicians",
            "select": ["full_name", "hired_at"],
            "filters": [
                {"field": "hired_at", "op": "between", "values": ["2020-01-01", "2022-12-31"]}
            ],
            "order_by": [{"target": "hired_at"}, {"target": "id"}],
        },
        "SELECT full_name, hired_at FROM technicians "
        "WHERE hired_at BETWEEN '2020-01-01' AND '2022-12-31' ORDER BY hired_at, id",
    ),
    (
        "o30_busy_job_types_and_technicians",
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [
                {"agg": "count", "alias": "n"},
                {"agg": "count_distinct", "field": "technician_id", "alias": "techs"},
            ],
            "group_by": [{"field": "job_type"}],
            "filters": [{"field": "status", "op": "neq", "value": "cancelled"}],
            "having": [{"metric": "n", "op": "between", "values": [500, 2000]}],
        },
        "SELECT job_type, count(*) AS n, count(DISTINCT technician_id) FROM work_orders "
        "WHERE status <> 'cancelled' GROUP BY job_type HAVING count(*) BETWEEN 500 AND 2000",
    ),
]
