"""ho-020, ho-022, ho-024 and ho-028: the gold against Askwell's recorded SQL shape,
scored as the eval does, without the id column, and as a multiset.

    uv run python builds/v03/evidence/idcheck.py <read-only database URL>
"""

import sys

import psycopg

from askwell.bench.compare import results_match

conn = psycopg.connect(sys.argv[1])

BILLED = (
    " FROM invoices i JOIN work_orders w ON w.id = i.work_order_id"
    " JOIN sites s ON s.id = w.site_id JOIN customers c ON c.id = s.customer_id"
    " WHERE i.status <> 'void' AND i.issued_at >= '2025-01-01' AND i.issued_at < '2026-01-01'"
)
UNITS = (
    " FROM work_order_parts x JOIN parts p ON p.id = x.part_id"
    " JOIN work_orders w ON w.id = x.work_order_id"
    " WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-06-30'"
)
BUSY = (
    " FROM work_orders w JOIN technicians t ON t.id = w.technician_id"
    " WHERE w.status = 'completed' AND w.completed_at >= '2026-04-01'"
    " AND w.completed_at < '2026-06-30'"
)
CITIES = (
    " FROM work_orders w JOIN sites s ON s.id = w.site_id"
    " WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-04-01'"
)
CASES = {
    "ho-020": (
        f"SELECT c.id, c.name, SUM(i.amount) AS billed{BILLED}"
        " GROUP BY c.id, c.name ORDER BY billed DESC, c.id LIMIT 5",
        f"SELECT c.name, SUM(i.amount){BILLED} GROUP BY c.name ORDER BY 2 DESC NULLS LAST LIMIT 5",
        True,
    ),
    "ho-024": (
        f"SELECT p.id, p.name, SUM(x.quantity) AS units{UNITS}"
        " GROUP BY p.id, p.name ORDER BY units DESC, p.id LIMIT 10",
        f"SELECT p.name, SUM(x.quantity){UNITS}"
        " GROUP BY p.name ORDER BY 2 DESC NULLS LAST LIMIT 10",
        True,
    ),
    "ho-028": (
        f"SELECT t.id, t.full_name, COUNT(*) AS completed_jobs{BUSY}"
        " GROUP BY t.id, t.full_name ORDER BY completed_jobs DESC, t.id LIMIT 5",
        f"SELECT t.full_name, COUNT(*){BUSY}"
        " GROUP BY t.full_name ORDER BY 2 DESC NULLS LAST LIMIT 5",
        True,
    ),
    "ho-022": (
        f"SELECT s.city, COUNT(*) AS jobs{CITIES}"
        " GROUP BY s.city ORDER BY jobs DESC, s.city LIMIT 10",
        f"SELECT s.city, COUNT(*){CITIES} GROUP BY s.city ORDER BY 2 DESC NULLS LAST LIMIT 10",
        False,
    ),
}


def rows(sql: str) -> list[tuple[object, ...]]:
    return [tuple(r) for r in conn.execute(sql).fetchall()]


for item_id, (gold_sql, answer_sql, has_id) in CASES.items():
    gold, answer = rows(gold_sql), rows(answer_sql)
    named = [r[1:] for r in gold] if has_id else gold
    print(
        item_id,
        "as scored:",
        results_match(answer, gold, ordered=True),
        "| without id, ordered:",
        results_match(answer, named, ordered=True) if has_id else "-",
        "| as a multiset:",
        results_match(answer, named, ordered=False),
    )
    print("  answer:", answer)
