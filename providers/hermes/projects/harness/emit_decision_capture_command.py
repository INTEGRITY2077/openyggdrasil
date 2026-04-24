from __future__ import annotations

import argparse
import json
import uuid

from decision_contracts import validate_decision_surface
from harness_common import DEFAULT_VAULT, utc_now_iso
from mailbox_schema import validate_message
from plugin_logger import record_plugin_event
from postman_gateway import submit_command
from provider_attachment import build_session_uid


def build_decision_surface(
    *,
    profile: str,
    session_id: str,
    turn_start: int,
    turn_end: int,
    surface_summary: str,
    trigger_reason: str,
    topic_hint: str | None,
    conversation_excerpt: list[dict[str, str]],
) -> dict:
    surface = {
        "schema_version": "decision_surface.v1",
        "provider_id": "hermes",
        "provider_profile": profile,
        "provider_session_id": session_id,
        "session_uid": build_session_uid(
            provider_id="hermes",
            provider_profile=profile,
            provider_session_id=session_id,
        ),
        "turn_start": turn_start,
        "turn_end": turn_end,
        "surface_summary": surface_summary,
        "trigger_reason": trigger_reason,
        "topic_hint": topic_hint,
        "source_ref": None,
        "conversation_excerpt": conversation_excerpt,
        "origin_locator": {
            "provider_id": "hermes",
            "provider_profile": profile,
            "provider_session_id": session_id,
            "turn_start": turn_start,
            "turn_end": turn_end,
        },
        "created_at": utc_now_iso(),
    }
    validate_decision_surface(surface)
    return surface


def build_command(
    *,
    profile: str,
    session_id: str,
    parent_question_id: str | None,
    decision_surface: dict,
) -> dict:
    scope = {
        "profile": profile,
        "session_id": session_id,
        "vault_path": str(DEFAULT_VAULT),
        "topic": decision_surface["surface_summary"],
    }
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "execute_decision_capture",
        "kind": "command",
        "parent_question_id": parent_question_id,
        "producer": "hermes",
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "high",
        "scope": scope,
        "payload": {
            "capability": "ingest",
            "target_role": "decision_capture_executor",
            "inference_mode": "subagent_headless",
            "write_scope": "result",
            "decision_surface": decision_surface,
        },
    }
    validate_message(message)
    return message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a decision-surface capture command into the mailbox.")
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--turn-start", type=int, required=True)
    parser.add_argument("--turn-end", type=int, required=True)
    parser.add_argument("--surface-summary", required=True)
    parser.add_argument("--trigger-reason", required=True)
    parser.add_argument("--topic-hint", default=None)
    parser.add_argument(
        "--conversation-line",
        action="append",
        default=[],
        help="Conversation excerpt line formatted as role:text",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excerpt: list[dict[str, str]] = []
    for raw_line in args.conversation_line:
        role, _, text = raw_line.partition(":")
        role = role.strip() or "unknown"
        text = text.strip()
        if text:
            excerpt.append({"role": role, "text": text})
    if not excerpt:
        excerpt = [{"role": "assistant", "text": args.surface_summary}]

    decision_surface = build_decision_surface(
        profile=args.profile,
        session_id=args.session_id,
        turn_start=args.turn_start,
        turn_end=args.turn_end,
        surface_summary=args.surface_summary,
        trigger_reason=args.trigger_reason,
        topic_hint=args.topic_hint,
        conversation_excerpt=excerpt,
    )
    message = build_command(
        profile=args.profile,
        session_id=args.session_id,
        parent_question_id=args.parent_question_id,
        decision_surface=decision_surface,
    )
    submit_command(message, namespace=args.mailbox_namespace)
    record_plugin_event(
        event_type="decision_capture_command_emitted",
        actor="hermes",
        parent_question_id=message.get("parent_question_id"),
        profile=message.get("scope", {}).get("profile"),
        session_id=message.get("scope", {}).get("session_id"),
        query_text=decision_surface.get("surface_summary"),
        artifacts={
            "command_id": message["message_id"],
            "target_role": message.get("payload", {}).get("target_role"),
            "mailbox_namespace": args.mailbox_namespace,
        },
        state={
            "capability": message.get("payload", {}).get("capability"),
            "write_scope": message.get("payload", {}).get("write_scope"),
            "inference_mode": message.get("payload", {}).get("inference_mode"),
        },
    )
    print(json.dumps(message, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
