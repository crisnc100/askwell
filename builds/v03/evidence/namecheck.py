import json, psycopg
c=psycopg.connect("host=localhost port=56452 user=askwell_ro password=askwell_ro dbname=askwell")
for l in open('evals/gold/fieldservice.jsonl'):
    d=json.loads(l)
    s=d['gold_sql'] or ''
    if d['id'] in ('fs-032','fs-034','fs-038','fs-041','fs-043','fs-037'):
        rows=c.execute(s).fetchall()
        print(d['id'], d['question']); print('  ', s[:300]); print('  rows', len(rows), [r for r in rows if 'Garcia Ltd' in map(str,r)])
