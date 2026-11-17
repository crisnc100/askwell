"""The front page ships the first demo question's answer (web/src/recorded-answer.json) so
it can show a whole answered slip without calling the API. This keeps that copy equal to
what the API answers today, replayed through the real pipeline and database."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from askwell.api import create_app
from askwell.config import get_settings
from askwell.core.audit import AuditLog
from askwell.pipeline.service import AskService, build_gateway, load_schemas

RECORDED = Path(__file__).resolve().parents[2] / "web" / "src" / "recorded-answer.json"


def test_the_front_page_answer_is_what_the_api_answers(tmp_path: Path, pg_seeded: Engine) -> None:
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    settings = get_settings()
    app_db = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    service = AskService(
        settings, load_schemas(settings), build_gateway(settings, "replay"), AuditLog(app_db)
    )
    try:
        with TestClient(create_app(service)) as client:
            examples = client.get("/schemas/fieldservice/examples").json()
            assert recorded["question"] == examples[0]
            response = client.post(
                "/ask", json={"schema_id": "fieldservice", "question": recorded["question"]}
            )
    finally:
        app_db.dispose()
    assert response.status_code == 200, response.text
    live = response.json()
    assert {key: live[key] for key in recorded} == recorded
    assert recorded["refusal"] is None
    assert recorded["rows"]
