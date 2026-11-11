"""Per-module branch coverage floors (plan.md P2 exit, L2).

    uv run python -m scripts.check_coverage coverage.json

Reads coverage.py's JSON report (run with `--cov-branch`) and fails if any listed module
is below its floor. A missing module fails too: a floor nobody measured is not met.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FLOORS: dict[str, float] = {
    "ledgerline/core/validate.py": 95.0,
    "ledgerline/core/sqlbuild.py": 95.0,
    "ledgerline/core/executor.py": 85.0,
    "ledgerline/core/registry_init.py": 85.0,
    "ledgerline/workspace/rules.py": 90.0,
    "ledgerline/workspace/check.py": 95.0,
    "ledgerline/workspace/load.py": 85.0,
    "ledgerline/workspace/store.py": 95.0,
    "ledgerline/workspace/limits.py": 95.0,
    "ledgerline/workspace/api.py": 90.0,
    "ledgerline/workspace/fields.py": 90.0,
    "ledgerline/workspace/ask.py": 90.0,
}


def branch_percent(summary: dict[str, float]) -> float:
    branches = summary.get("num_branches", 0)
    if not branches:
        return 100.0
    return 100.0 * summary.get("covered_branches", 0) / branches


def check(report: dict[str, object], floors: dict[str, float] = FLOORS) -> list[str]:
    files: dict[str, dict[str, dict[str, float]]] = report.get("files", {})  # type: ignore[assignment]
    failures: list[str] = []
    for module, floor in floors.items():
        entry = files.get(module)
        if entry is None:
            failures.append(f"{module}: not in the coverage report")
            continue
        summary = entry["summary"]
        branch = branch_percent(summary)
        line = summary.get("percent_covered", 0.0)
        status = "ok" if branch >= floor else "BELOW FLOOR"
        print(f"{module}: branch {branch:.1f}% (floor {floor:.0f}%), combined {line:.1f}% {status}")
        if branch < floor:
            failures.append(f"{module}: branch coverage {branch:.1f}% < {floor:.0f}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0] if args else "coverage.json")
    failures = check(json.loads(path.read_text()))
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
