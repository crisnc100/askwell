"""The server the Playwright tests drive: the real app and pages, with a fake model.

    uv run python -m tests.e2e.serve --port 8765 --export-dir web/.e2e/export

The fake model answers a few fixed questions and writes every request it receives to
`--export-dir`, one JSON file per request, so a browser test can read exactly what the
model was sent. Workspaces live in a fresh temporary folder. Nothing calls a real model.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import uvicorn

from ledgerline.api import create_app
from ledgerline.config import get_settings
from ledgerline.core.intent import Intent
from ledgerline.core.registry import slugify
from ledgerline.llm.types import ChatMessage, LLMResult
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.store import WorkspaceStore
from tests.workspace.fake_model import FakeModel, fake_service

# Kept in step with web/e2e/xss.spec.ts.
XSS_FILE = '<img src=x onerror="window.__xss=1">.csv'
XSS_HEADER = "<script>window.__xss=1</script>"

ANSWERS: dict[str, dict[str, Any]] = {
    "How many orders?": {
        "intent_type": "summary",
        "entity": "orders",
        "metrics": [{"agg": "count"}],
    },
    "Show the odd table": {
        "intent_type": "row_list",
        "entity": slugify(XSS_FILE.removesuffix(".csv")),
        "select": ["id", slugify(XSS_HEADER)],
    },
}


class ExportingModel(FakeModel):
    def __init__(self, export_dir: Path) -> None:
        super().__init__(ANSWERS)
        self.export_dir = export_dir

    def complete(self, *, messages: list[ChatMessage], **kwargs: Any) -> LLMResult[Intent]:
        path = self.export_dir / f"{len(self.calls) + 1:03d}.json"
        path.write_text(
            json.dumps({"messages": [m.model_dump() for m in messages]}, indent=2),
            encoding="utf-8",
        )
        return super().complete(messages=messages, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args()
    shutil.rmtree(args.export_dir, ignore_errors=True)
    args.export_dir.mkdir(parents=True)
    workspaces = Path(tempfile.mkdtemp(prefix="ledgerline-e2e-"))
    service = fake_service(get_settings(), ExportingModel(args.export_dir))
    app = create_app(service=service, workspaces=WorkspaceApp(WorkspaceStore(workspaces)))
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        shutil.rmtree(workspaces, ignore_errors=True)


if __name__ == "__main__":
    main()
