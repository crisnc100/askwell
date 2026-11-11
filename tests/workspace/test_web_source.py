"""The page inserts every user string as text (L22). The browser test proves it on real
payloads (web/e2e/xss.spec.ts); this check keeps any new code from reaching for an HTML
sink, which that test might not exercise."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.store import WorkspaceStore
from tests.workspace.conftest import _NoService

WEB = Path(__file__).resolve().parents[2] / "web"
HTML_SINKS = re.compile(
    r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
    r"DOMParser|srcdoc|\beval\(|new Function\("
)


def test_the_page_source_has_no_html_sinks() -> None:
    sources = sorted((WEB / "src").rglob("*.ts"))
    assert sources
    for path in sources:
        code = path.read_text(encoding="utf-8")
        if path.name == "dom.ts":
            # Its comment names the sink it exists to avoid.
            code = "\n".join(line for line in code.splitlines() if not line.startswith("//"))
        assert not HTML_SINKS.search(code), path


def test_built_pages_are_served_at_the_root_after_the_api(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>pages</title>", encoding="utf-8")
    workspaces = WorkspaceApp(WorkspaceStore(tmp_path / "ws"))
    app = create_app(service=_NoService(), workspaces=workspaces, web_dir=dist)  # type: ignore[arg-type]
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "pages" in page.text
        assert page.headers["referrer-policy"] == "no-referrer"
        assert client.get("/api/limits").json()["max_files"] == 10


def test_without_a_build_there_is_no_page(tmp_path: Path) -> None:
    workspaces = WorkspaceApp(WorkspaceStore(tmp_path / "ws"))
    app = create_app(service=_NoService(), workspaces=workspaces, web_dir=tmp_path / "none")  # type: ignore[arg-type]
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
