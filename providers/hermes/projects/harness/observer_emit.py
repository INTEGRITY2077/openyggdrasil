from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List

from harness_common import DEFAULT_VAULT, utc_now_iso
from mailbox_schema import validate_message
from plugin_logger import record_plugin_event
from postman_gateway import submit_command


def build_lint_command(
    *,
    profile: str,
    session_id: str | None,
    parent_question_id: str | None = None,
    producer: str = "observer-daemon",
) -> Dict[str, Any]:
    scope = {
        "profile": profile,
        "vault_path": str(DEFAULT_VAULT),
        "topic": "llm-wiki lint",
    }
    if session_id:
        scope["session_id"] = session_id
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "execute_lint",
        "kind": "command",
        "parent_question_id": parent_question_id,
        "producer": producer,
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "medium",
        "scope": scope,
        "payload": {
            "capability": "lint",
            "target_role": "lint_executor",
            "inference_mode": "deterministic",
            "write_scope": "result",
        },
    }
    validate_message(message)
    return message


def emit_observer_commands(
    plans: Iterable[Dict[str, Any]],
    *,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    emitted: List[Dict[str, Any]] = []
    for plan in plans:
        if plan["message_type"] == "execute_lint":
            message = build_lint_command(
                profile=plan["profile"],
                session_id=plan.get("session_id"),
            )
        else:
            raise RuntimeError(f"Unsupported observer plan type: {plan['message_type']}")
        submit_command(message, namespace=namespace)
        record_plugin_event(
            event_type="observer_command_emitted",
            actor="observer",
            parent_question_id=message.get("parent_question_id"),
            profile=message.get("scope", {}).get("profile"),
            session_id=message.get("scope", {}).get("session_id"),
            query_text=message.get("scope", {}).get("topic"),
            artifacts={
                "command_id": message["message_id"],
                "message_type": message["message_type"],
                "target_role": message.get("payload", {}).get("target_role"),
                "mailbox_namespace": namespace,
            },
            state={
                "capability": message.get("payload", {}).get("capability"),
                "write_scope": message.get("payload", {}).get("write_scope"),
                "inference_mode": message.get("payload", {}).get("inference_mode"),
            },
        )
        emitted.append(message)
    return emitted
