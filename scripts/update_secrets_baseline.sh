#!/usr/bin/env bash
# Rescan for secrets and print every finding for review. It does NOT mark anything as
# a false positive: review each one, then audit with `uv run detect-secrets audit .secrets.baseline`.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run detect-secrets scan --baseline .secrets.baseline \
  --exclude-files '^(\.venv/|\.git/|uv\.lock$|data/|\.pytest_cache/|\.ruff_cache/|evals/gold/MANIFEST\.json$)' --all-files
python3 - <<'PY'
import json
b = json.load(open(".secrets.baseline"))
for path, items in sorted(b["results"].items()):
    for it in items:
        print(f"{path}:{it['line_number']}  {it['type']}  is_secret={it.get('is_secret')}")
PY
