"""Re-run the fieldservice eval from the committed recordings and compare the result with
the committed replay report (plan.md P4.3). Exit 1 on any difference.

    uv run python -m scripts.check_replay_report           # check
    uv run python -m scripts.check_replay_report --write   # rewrite the committed report

The run happens in a temporary directory, so it never resumes an old checkpoint. Only the
Markdown report is compared: the JSON also holds replay latencies, which vary run to run.
"""

from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

from ledgerline.bench import report as report_module
from ledgerline.bench import run as run_module
from ledgerline.config import get_settings

RUN_ID = "replay-fieldservice"
COMMITTED = report_module.REPORTS_DIR / f"{RUN_ID}.md"


def render() -> tuple[str, dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        run_module.RUNS_DIR = Path(tmp)
        result = run_module.run_eval(
            get_settings(),
            run_id=RUN_ID,
            schema_ids=["fieldservice"],
            systems=["ledgerline", "oneshot"],
            mode="replay",
            models=[get_settings().default_model or ""],
            trials=1,
            budget_usd=0.0,
        )
    data = report_module.build(result)
    return report_module.render_markdown(data), data


def main(argv: list[str]) -> int:
    text, data = render()
    if "--write" in argv:
        report_module.write(data)
        print(f"wrote {COMMITTED}")
        return 0
    committed = COMMITTED.read_text(encoding="utf-8")
    if text == committed:
        print("replay eval reproduces the committed report")
        return 0
    sys.stdout.writelines(
        difflib.unified_diff(
            committed.splitlines(True), text.splitlines(True), "committed", "replay"
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
