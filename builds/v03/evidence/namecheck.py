"""The seen golds that group by a customer or technician: each groups by id, shows the
name, and none of their rows is a customer named "Garcia Ltd" (ids 56 and 144).

    uv run python builds/v03/evidence/namecheck.py <read-only database URL>
"""

import json
import sys

import psycopg

conn = psycopg.connect(sys.argv[1])
WANTED = {"fs-032", "fs-034", "fs-037", "fs-038", "fs-041", "fs-043"}

with open("evals/gold/fieldservice.jsonl", encoding="utf-8") as fh:
    for line in fh:
        item = json.loads(line)
        if item["id"] not in WANTED:
            continue
        found = conn.execute(item["gold_sql"]).fetchall()
        garcia = [r for r in found if "Garcia Ltd" in map(str, r)]
        print(item["id"], item["question"])
        print("  ", item["gold_sql"][:300])
        print("   rows", len(found), garcia)
