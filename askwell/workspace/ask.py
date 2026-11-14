"""Ask on a workspace: the same pipeline, pointed at the workspace's own registry,
read-only SQLite file and `ask_log`.

Relative dates ("last month") resolve against the wall clock in the workspace's time
zone. Workspace dates have no time zone of their own, so "now" is that zone's local time
without a zone. The evals never come through here; they keep the pinned reference time.

Answers need a live model: a new workspace's prompt has never been recorded, so replay
could never answer it. Without one, the ask is refused with a pointer to the README.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine

from askwell.core.audit import AuditLog
from askwell.core.executor import readonly_engine
from askwell.core.features import ALL, Features
from askwell.core.registry import Registry, load_registry
from askwell.llm.daily import DailyCapReachedError
from askwell.llm.errors import LiveAnswersOffError
from askwell.pipeline.prompt import registry_view, system_message
from askwell.pipeline.service import AskService, AskTarget
from askwell.workspace.store import (
    PRIVATE_FILE,
    Workspace,
    WorkspaceError,
    WrongStateError,
)

log = logging.getLogger("askwell.workspace")

NEEDS_KEY = "Live answers need a model key; see the README."


class LiveAnswersUnavailableError(WorkspaceError):
    """The kill switch is on, or today's spending cap is reached."""

    status = 503


CONFIRM_FIRST = "Confirm your fields first."
WORKSPACE_SCHEMA_ID = "workspace"


class NeedsModelKeyError(WorkspaceError):
    status = 503


class ModelFailedError(WorkspaceError):
    status = 502


def local_now(time_zone: str, clock: Callable[[], datetime]) -> datetime:
    """The wall-clock time in `time_zone`, without a zone (like the workspace's dates)."""
    return clock().astimezone(ZoneInfo(time_zone)).replace(tzinfo=None)


def prompt_preview(
    registry: Registry,
    time_zone: str,
    clock: Callable[[], datetime],
    budget_chars: int,
    features: Features = ALL,
) -> dict[str, Any]:
    """The system message the model would get for this registry, built by the same
    function the interpret step uses, with the same truncation."""
    view = registry_view(registry, local_now(time_zone, clock), budget_chars, time_zone, features)
    return {"prompt": system_message(view), "truncation": view.truncation}


@contextmanager
def workspace_target(workspace: Workspace, clock: Callable[[], datetime]) -> Generator[AskTarget]:
    """The ask target for a confirmed workspace; its engines close on exit."""
    registry = load_registry(workspace.registry_path)
    engine = readonly_engine(f"sqlite:///{workspace.db_path}")
    # Created by hand first, so the file is private from the start (SQLite gives its
    # journal files the same mode).
    with contextlib.suppress(FileExistsError):
        os.close(os.open(workspace.audit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE))
    audit_engine = create_engine(f"sqlite:///{workspace.audit_path}")
    try:
        yield AskTarget(
            schema_id=WORKSPACE_SCHEMA_ID,
            registry=registry,
            engine=engine,
            allow_draft=False,
            now=local_now(workspace.meta.time_zone, clock),
            time_zone=workspace.meta.time_zone,
            audit=AuditLog(audit_engine),
        )
    finally:
        engine.dispose()
        audit_engine.dispose()


def ask_workspace(
    service: AskService,
    workspace: Workspace,
    question: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    if workspace.meta.state != "confirmed":
        raise WrongStateError(CONFIRM_FIRST)
    if service.gateway.mode != "live":
        raise NeedsModelKeyError(NEEDS_KEY)
    with workspace_target(workspace, clock) as target:
        try:
            result = service.ask_target(target, question).to_dict()
        except (LiveAnswersOffError, DailyCapReachedError) as exc:
            raise LiveAnswersUnavailableError(str(exc)) from exc
        except Exception as exc:
            log.exception("workspace ask failed")
            raise ModelFailedError(
                "The question could not be answered right now. Try again in a minute."
            ) from exc
    result["explanation"] = explain(result)
    return result


_PLAIN: list[tuple[frozenset[str], str, str]] = [
    (
        frozenset({"fan_out", "one_to_many_join"}),
        "Adding up across a one-to-many link would count some rows more than once.",
        "Ask about one table at a time, or count from the 'many' side (for example, "
        "count order lines per order).",
    ),
    (
        frozenset({"ambiguous_path", "unknown_link"}),
        "Two tables are linked in more than one way, so the question could mean either.",
        "Say which link you mean (for example, 'by the billing customer').",
    ),
    (
        frozenset({"unreachable_field"}),
        "The question needs tables that are not linked to each other closely enough.",
        "Ask about tables that share an ID column, or add a <table>_id column that links them.",
    ),
    (
        frozenset({"hidden_field"}),
        "The question needs a field you hid.",
        "Unhide it on the Confirm page if the model may use it.",
    ),
    (
        frozenset({"unknown_entity", "unknown_field"}),
        "The question mentions data that is not in your files.",
        "Use the tables and columns shown on the Confirm page.",
    ),
    (
        frozenset({"value_not_allowed", "ambiguous_value"}),
        "A value in the question is not one of the values in that column.",
        "Check its spelling against your data.",
    ),
    (
        frozenset({"date_range_field_type", "date_range_duplicate", "invalid_date_range"}),
        "The date range could not be applied.",
        "Name a date column and a period, like 'orders last month by order date'.",
    ),
    (
        frozenset({"ratio_ref", "ratio_shape"}),
        "The question asks for a share or a rate, and its two parts did not line up.",
        "Name both parts, like 'paid orders as a share of all orders'.",
    ),
    (
        frozenset({"series_shape", "series_date_field"}),
        "The question asks for counts over time by more than one date, and they could not "
        "be lined up by period.",
        "Name each date column and one period, like 'orders placed and orders shipped per month'.",
    ),
    (
        frozenset({"placeholder_reason"}),
        "The model gave no real reason for its answer.",
        "Ask again, or put the question another way.",
    ),
    (
        frozenset({"limit_out_of_range"}),
        "The question asks for more rows than one answer can show.",
        "Ask for fewer rows (at most 1,000).",
    ),
    (
        frozenset(
            {
                "not_filterable",
                "not_aggregatable",
                "aggregate_type",
                "operator_type",
                "value_type",
                "value_shape",
                "column_comparison_type",
                "having_type",
                "grain_type",
            }
        ),
        "The question asks for a calculation that does not fit the column (for example, "
        "a total of a text column).",
        "Use a number column for totals and averages, and a date column for periods.",
    ),
]
_GENERAL = (
    "The question could not be turned into a safe query.",
    "Ask it more simply, about one table at a time.",
)


def explain(result: dict[str, Any]) -> dict[str, str] | None:
    """A refusal in plain English, with a suggestion; None for an answer."""
    if result.get("refusal") is None:
        return None
    validation: dict[str, Any] = result.get("validation") or {}
    if validation.get("stopped"):
        return {
            "message": "This question hit the spending limit.",
            "suggestion": "Try a simpler question.",
        }
    intent: dict[str, Any] = result.get("intent") or {}
    if intent.get("intent_type") == "unanswerable":
        return {
            "message": "The model found no way to answer this from your data: "
            f"{intent.get('unanswerable_reason') or 'no reason given'}",
            "suggestion": "Check that the data is in your files and its fields are not "
            "hidden on the Confirm page.",
        }
    attempts: list[dict[str, Any]] = validation.get("attempts") or []
    last: dict[str, Any] = attempts[-1] if attempts else {}
    if last.get("parse_error"):
        return {
            "message": "The model's answer could not be read.",
            "suggestion": "Ask again, or put the question another way.",
        }
    if str(result["refusal"]).startswith("the query failed"):
        return {
            "message": "The database could not run the query.",
            "suggestion": "Put the question another way.",
        }
    issues: list[dict[str, str]] = last.get("issues", [])
    codes = {issue["code"] for issue in issues}
    for group, message, suggestion in _PLAIN:
        if codes & group:
            return {"message": message, "suggestion": suggestion}
    return {"message": _GENERAL[0], "suggestion": _GENERAL[1]}
