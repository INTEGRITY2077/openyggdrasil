from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Mapping

from command_registry import COMMAND_REGISTRY, CommandSpec, validate_command_message
from mailbox_status import write_mailbox_status
from mailbox_store import append_claim, claimed_message_ids, read_messages
from plugin_logger import record_plugin_event
from role_registry import ensure_role_can_route_command
from subagent_telemetry import record_subagent_event


def command_messages(
    *,
    profile: str | None,
    session_id: str | None,
    mailbox_namespace: str | None = None,
) -> List[Dict[str, Any]]:
    claimed = claimed_message_ids(
        consumer="postman",
        claim_type="command_routed",
        namespace=mailbox_namespace,
    )
    messages: List[Dict[str, Any]] = []
    for message in read_messages(namespace=mailbox_namespace):
        if message.get("kind") != "command":
            continue
        if message.get("status") != "new":
            continue
        if message.get("message_id") in claimed:
            continue
        scope = message.get("scope", {})
        if profile and scope.get("profile") != profile:
            continue
        if session_id and scope.get("session_id") != session_id:
            continue
        messages.append(message)
    return messages


def route_command(
    message: Dict[str, Any],
    *,
    registry: Mapping[str, CommandSpec] | None = None,
    mailbox_namespace: str | None = None,
) -> Dict[str, Any]:
    spec = validate_command_message(message, registry=registry)
    message_type = spec.message_type
    scope = message.get("scope", {})
    payload = message.get("payload", {})
    profile = scope.get("profile") or "wiki"
    session_id = scope.get("session_id")
    ensure_role_can_route_command(
        role="postman",
        message_type=message_type,
        capability=spec.capability,
    )

    append_claim(
        message_id=message["message_id"],
        consumer="postman",
        claim_type="command_routed",
        scope=scope,
        namespace=mailbox_namespace,
    )

    record_subagent_event(
        trace_id=message["message_id"],
        capability=str(payload.get("capability") or "system"),
        role="postman",
        actor="postman",
        decider="postman",
        action="command_routed",
        status="success",
        producer="postman",
        parent_question_id=message.get("parent_question_id"),
        artifacts={"message_id": message["message_id"], "command_id": message["message_id"]},
        scope={
            "profile": profile,
            "session_id": session_id,
            "vault_path": scope.get("vault_path"),
            "graph_path": scope.get("graph_path"),
        },
        inference={"mode": "deterministic"},
        details={"message_type": message_type},
    )
    record_plugin_event(
        event_type="command_routed",
        actor="postman",
        parent_question_id=message.get("parent_question_id"),
        profile=profile,
        session_id=session_id,
        query_text=payload.get("question") or scope.get("topic"),
        artifacts={
            "command_id": message["message_id"],
            "message_type": message_type,
            "target_role": spec.target_role,
            "mailbox_namespace": mailbox_namespace,
        },
        state={
            "capability": spec.capability,
            "write_scope": spec.write_scope,
            "inference_mode": spec.inference_mode,
        },
    )

    if mailbox_namespace is None:
        return spec.handler(message, profile, session_id)
    return spec.handler(message, profile, session_id, mailbox_namespace)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route mailbox commands once through the postman.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mailbox-namespace", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    messages = command_messages(
        profile=args.profile,
        session_id=args.session_id,
        mailbox_namespace=args.mailbox_namespace,
    )
    if args.limit:
        messages = messages[: args.limit]
    results = [route_command(message, mailbox_namespace=args.mailbox_namespace) for message in messages]
    status = write_mailbox_status(namespace=args.mailbox_namespace)
    print(json.dumps({"routed": len(results), "results": results, "status": status["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
