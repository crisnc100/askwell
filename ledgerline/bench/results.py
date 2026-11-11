"""The routes behind the Results page: the committed eval reports and triage files, read
only from `evals/reports/` and `evals/triage/`.

A request names a report or a schema by id, and only an id found by listing the folder is
ever opened, so no request text becomes part of a file path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from ledgerline.bench.report import REPORTS_DIR, TRIAGE_DIR


def report_files(reports_dir: Path = REPORTS_DIR) -> dict[str, Path]:
    return {p.stem: p for p in sorted(reports_dir.glob("*.json"))}


def triage_files(triage_dir: Path = TRIAGE_DIR) -> dict[str, Path]:
    return {p.stem: p for p in sorted(triage_dir.glob("*.yaml"))}


def summary(report_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": report_id,
        "simulation": report.get("simulation"),
        "schemas": sorted({row["schema"] for row in report["table"]}),
    }


def install(app: FastAPI, reports_dir: Path = REPORTS_DIR, triage_dir: Path = TRIAGE_DIR) -> None:
    @app.get("/api/reports")
    def reports() -> list[dict[str, Any]]:  # pyright: ignore[reportUnusedFunction]
        """Every committed report, the one covering the most schemas first (the page
        opens that one), then by id."""
        out = [
            summary(report_id, json.loads(path.read_text(encoding="utf-8")))
            for report_id, path in report_files(reports_dir).items()
        ]
        return sorted(out, key=lambda r: (-len(r["schemas"]), r["id"]))

    @app.get("/api/reports/{report_id}")
    def report(report_id: str) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        path = report_files(reports_dir).get(report_id)
        if path is None:
            raise HTTPException(404, "No report has that name.")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        data["triage_files"] = sorted(
            {row["schema"] for row in data["table"]} & set(triage_files(triage_dir))
        )
        return data

    @app.get("/api/triage/{schema_id}", response_class=PlainTextResponse)
    def triage(schema_id: str) -> str:  # pyright: ignore[reportUnusedFunction]
        path = triage_files(triage_dir).get(schema_id)
        if path is None:
            raise HTTPException(404, "No triage file for that schema.")
        return path.read_text(encoding="utf-8")
