from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Mapping

from decision_capture_executor import execute_decision_capture
from deep_search_executor import execute_deep_search
from lint_executor import execute_lint
from role_registry import ensure_role_can_handle_command


CommandHandler = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class CommandSpec:
    message_type: str
    capability: str
    target_role: str
    inference_mode: str
    write_scope: str
    allowed_packet_types: FrozenSet[str]
    handler: CommandHandler


def handle_execute_lint(
    message: Dict[str, Any],
    profile: str,
    session_id: str | None,
    mailbox_namespace: str | None = None,
) -> Dict[str, Any]:
    result = execute_lint(
        profile=profile,
        session_id=session_id,
        parent_question_id=message.get("parent_question_id"),
        mailbox_namespace=mailbox_namespace,
    )
    packet = result["packet"]
    return {"routed_type": "execute_lint", "packet_id": packet["message_id"]}


def handle_execute_deep_search(
    message: Dict[str, Any],
    profile: str,
    session_id: str | None,
    mailbox_namespace: str | None = None,
) -> Dict[str, Any]:
    payload = message.get("payload", {})
    question = str(payload.get("question") or "").strip()
    if not question:
        raise RuntimeError("execute_deep_search missing payload.question")
    result = execute_deep_search(
        profile=profile,
        session_id=session_id,
        question=question,
        parent_question_id=message.get("parent_question_id"),
        mailbox_namespace=mailbox_namespace,
    )
    packet = result["packet"]
    return {"routed_type": "execute_deep_search", "packet_id": packet["message_id"]}


def handle_execute_decision_capture(
    message: Dict[str, Any],
    profile: str,
    session_id: str | None,
    mailbox_namespace: str | None = None,
) -> Dict[str, Any]:
    payload = message.get("payload", {})
    decision_surface = payload.get("decision_surface")
    if not isinstance(decision_surface, dict):
        raise RuntimeError("execute_decision_capture missing payload.decision_surface")
    result = execute_decision_capture(
        profile=profile,
        session_id=session_id,
        decision_surface=decision_surface,
        parent_question_id=message.get("parent_question_id"),
        mailbox_namespace=mailbox_namespace,
    )
    packet = result["packet"]
    return {"routed_type": "execute_decision_capture", "packet_id": packet["message_id"]}


COMMAND_REGISTRY: Dict[str, CommandSpec] = {
    "execute_lint": CommandSpec(
        message_type="execute_lint",
        capability="lint",
        target_role="lint_executor",
        inference_mode="deterministic",
        write_scope="result",
        allowed_packet_types=frozenset({"lint_alert"}),
        handler=handle_execute_lint,
    ),
    "execute_deep_search": CommandSpec(
        message_type="execute_deep_search",
        capability="query",
        target_role="deep_search_executor",
        inference_mode="deterministic",
        write_scope="result",
        allowed_packet_types=frozenset({"graph_hint"}),
        handler=handle_execute_deep_search,
    ),
    "execute_decision_capture": CommandSpec(
        message_type="execute_decision_capture",
        capability="ingest",
        target_role="decision_capture_executor",
        inference_mode="subagent_headless",
        write_scope="result",
        allowed_packet_types=frozenset({"decision_candidate"}),
        handler=handle_execute_decision_capture,
    ),
}


def get_command_spec(message_type: str) -> CommandSpec:
    try:
        return COMMAND_REGISTRY[message_type]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported command message_type: {message_type}") from exc


def get_command_handler(message_type: str) -> CommandHandler:
    return get_command_spec(message_type).handler


def resolve_command_spec(
    message_type: str,
    *,
    registry: Mapping[str, CommandSpec] | None = None,
) -> CommandSpec:
    return (registry or COMMAND_REGISTRY).get(message_type) or get_command_spec(message_type)


def validate_command_message(
    message: Dict[str, Any],
    *,
    registry: Mapping[str, CommandSpec] | None = None,
) -> CommandSpec:
    message_type = str(message.get("message_type") or "")
    spec = resolve_command_spec(message_type, registry=registry)
    payload = message.get("payload", {})

    capability = str(payload.get("capability") or spec.capability)
    target_role = str(payload.get("target_role") or spec.target_role)
    inference_mode = str(payload.get("inference_mode") or spec.inference_mode)
    write_scope = str(payload.get("write_scope") or spec.write_scope)

    if capability != spec.capability:
        raise RuntimeError(
            f"Command capability mismatch for '{message_type}': expected '{spec.capability}', got '{capability}'"
        )
    if target_role != spec.target_role:
        raise RuntimeError(
            f"Command target_role mismatch for '{message_type}': expected '{spec.target_role}', got '{target_role}'"
        )
    if inference_mode != spec.inference_mode:
        raise RuntimeError(
            f"Command inference_mode mismatch for '{message_type}': expected '{spec.inference_mode}', got '{inference_mode}'"
        )
    if write_scope != spec.write_scope:
        raise RuntimeError(
            f"Command write_scope mismatch for '{message_type}': expected '{spec.write_scope}', got '{write_scope}'"
        )

    ensure_role_can_handle_command(
        role=target_role,
        message_type=message_type,
        capability=capability,
        inference_mode=inference_mode,
        write_scope=write_scope,
    )
    return spec
