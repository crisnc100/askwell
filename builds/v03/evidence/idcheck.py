import psycopg
from askwell.bench.compare import results_match
c=psycopg.connect("host=localhost port=56452 user=askwell_ro password=askwell_ro dbname=askwell")
def q(s): return [tuple(r) for r in c.execute(s).fetchall()]
cases={
"ho-020":("SELECT c.id, c.name, SUM(i.amount) AS billed FROM invoices i JOIN work_orders w ON w.id = i.work_order_id JOIN sites s ON s.id = w.site_id JOIN customers c ON c.id = s.customer_id WHERE i.status <> 'void' AND i.issued_at >= '2025-01-01' AND i.issued_at < '2026-01-01' GROUP BY c.id, c.name ORDER BY billed DESC, c.id LIMIT 5",
 "SELECT c.name, SUM(i.amount) FROM invoices i JOIN work_orders w ON w.id = i.work_order_id JOIN sites s ON s.id = w.site_id JOIN customers c ON c.id = s.customer_id WHERE i.status <> 'void' AND i.issued_at >= '2025-01-01' AND i.issued_at < '2026-01-01' GROUP BY c.name ORDER BY 2 DESC NULLS LAST LIMIT 5"),
"ho-024":("SELECT p.id, p.name, SUM(x.quantity) AS units FROM work_order_parts x JOIN parts p ON p.id = x.part_id JOIN work_orders w ON w.id = x.work_order_id WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-06-30' GROUP BY p.id, p.name ORDER BY units DESC, p.id LIMIT 10",
 "SELECT p.name, SUM(x.quantity) FROM work_order_parts x JOIN parts p ON p.id = x.part_id JOIN work_orders w ON w.id = x.work_order_id WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-06-30' GROUP BY p.name ORDER BY 2 DESC NULLS LAST LIMIT 10"),
"ho-028":("SELECT t.id, t.full_name, COUNT(*) AS completed_jobs FROM work_orders w JOIN technicians t ON t.id = w.technician_id WHERE w.status = 'completed' AND w.completed_at >= '2026-04-01' AND w.completed_at < '2026-06-30' GROUP BY t.id, t.full_name ORDER BY completed_jobs DESC, t.id LIMIT 5",
 "SELECT t.full_name, COUNT(*) FROM work_orders w JOIN technicians t ON t.id = w.technician_id WHERE w.status = 'completed' AND w.completed_at >= '2026-04-01' AND w.completed_at < '2026-06-30' GROUP BY t.full_name ORDER BY 2 DESC NULLS LAST LIMIT 5"),
"ho-022":("SELECT s.city, COUNT(*) AS jobs FROM work_orders w JOIN sites s ON s.id = w.site_id WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-04-01' GROUP BY s.city ORDER BY jobs DESC, s.city LIMIT 10",
 "SELECT s.city, COUNT(*) FROM work_orders w JOIN sites s ON s.id = w.site_id WHERE w.opened_at >= '2026-01-01' AND w.opened_at < '2026-04-01' GROUP BY s.city ORDER BY 2 DESC NULLS LAST LIMIT 10"),
}
for k,(g,a) in cases.items():
    G=q(g); A=q(a)
    print(k,"as-scored:",results_match(A,G,ordered=True),
      "| gold-minus-id ordered:", results_match(A,[r[1:] for r in G],ordered=True) if k!='ho-022' else '-',
      "| multiset:", results_match(A,[r[1:] for r in G] if k!='ho-022' else G,ordered=False))
    print("  ans:",A)
