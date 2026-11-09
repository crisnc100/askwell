"""The ask pipeline as a LangGraph graph (ADR-002: orchestration only).

interpret -> validate -> (one retry with the typed errors) -> execute -> present.
`interpret` is the only model call. `present` is deterministic and never sends result
rows anywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ledgerline.core.executor import Execution, ExecutionError
from ledgerline.core.intent import Intent
from ledgerline.core.validate import Issue, QueryPlan, ValidationResult
from ledgerline.llm.errors import ParseError
from ledgerline.llm.types import ChatMessage, LLMResult
from ledgerline.pipeline.prompt import retry_messages

MAX_ATTEMPTS = 2


class Attempt(TypedDict):
    answer: str
    intent: dict[str, Any] | None
    parse_error: str | None
    issues: list[dict[str, str]]


class AskState(TypedDict, total=False):
    question: str
    messages: list[ChatMessage]
    attempts: list[Attempt]
    intent: Intent | None
    answer: str
    parse_error: str | None
    issues: list[Issue]
    plan: QueryPlan | None
    refusal: str | None
    execution: Execution | None
    execution_error: str | None
    cost_usd: float
    provenance: dict[str, str] | None


Interpret = Callable[[list[ChatMessage]], LLMResult[Intent]]
Validate = Callable[[Intent], ValidationResult]
Execute = Callable[[QueryPlan, AskState], Execution]


def build_graph(interpret: Interpret, check: Validate, execute: Execute) -> Any:
    def interpret_node(state: AskState) -> AskState:
        try:
            result = interpret(state.get("messages", []))
        except ParseError as exc:
            return {
                "intent": None,
                "answer": exc.raw,
                "parse_error": exc.reason,
                "cost_usd": state.get("cost_usd", 0.0) + exc.cost_usd,
                "provenance": exc.provenance,
            }
        return {
            "intent": result.value,
            "answer": result.raw.content,
            "parse_error": None,
            "cost_usd": state.get("cost_usd", 0.0) + result.cost_usd,
            "provenance": result.provenance,
        }

    def validate_node(state: AskState) -> AskState:
        intent = state.get("intent")
        issues: list[Issue] = []
        out: AskState = {"plan": None, "refusal": None}
        if intent is not None:
            result = check(intent)
            issues = result.issues
            out["plan"] = result.plan
            out["refusal"] = result.refusal_reason
        attempt: Attempt = {
            "answer": state.get("answer", ""),
            "intent": intent.model_dump(mode="json", exclude_defaults=True) if intent else None,
            "parse_error": state.get("parse_error"),
            "issues": [
                {"code": i.code, "location": i.location, "message": i.message} for i in issues
            ],
        }
        out["attempts"] = [*state.get("attempts", []), attempt]
        out["issues"] = issues
        return out

    def route(state: AskState) -> str:
        if state.get("plan") is not None:
            return "execute"
        if state.get("refusal") is not None:
            return "present"
        if len(state.get("attempts", [])) < MAX_ATTEMPTS:
            return "retry"
        return "present"

    def retry_node(state: AskState) -> AskState:
        return {
            "messages": retry_messages(
                state.get("messages", []),
                state.get("answer", ""),
                state.get("issues", []),
                state.get("parse_error"),
            )
        }

    def execute_node(state: AskState) -> AskState:
        plan = state.get("plan")
        assert plan is not None
        try:
            return {"execution": execute(plan, state), "execution_error": None}
        except ExecutionError as exc:
            return {"execution": None, "execution_error": str(exc)}

    def present_node(state: AskState) -> AskState:
        if state.get("plan") is not None:
            return {}
        if state.get("refusal") is not None:
            return {}
        last = state.get("attempts", [])[-1]
        if last["parse_error"] is not None:
            reason = f"could not read the model's answer as an intent: {last['parse_error']}"
        else:
            codes = ", ".join(sorted({i["code"] for i in last["issues"]}))
            reason = f"no valid query after {MAX_ATTEMPTS} attempts ({codes})"
        return {"refusal": reason}

    graph = StateGraph(AskState)
    graph.add_node("interpret", interpret_node)
    graph.add_node("validate", validate_node)
    graph.add_node("retry", retry_node)
    graph.add_node("execute", execute_node)
    graph.add_node("present", present_node)
    graph.add_edge(START, "interpret")
    graph.add_edge("interpret", "validate")
    graph.add_conditional_edges("validate", route, ["execute", "present", "retry"])
    graph.add_edge("retry", "interpret")
    graph.add_edge("execute", "present")
    graph.add_edge("present", END)
    return graph.compile()
