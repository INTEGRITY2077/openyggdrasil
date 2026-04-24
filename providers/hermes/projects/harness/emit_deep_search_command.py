from __future__ import annotations

import argparse
import json
import uuid

from harness_common import DEFAULT_GRAPHIFY_SANDBOX, DEFAULT_VAULT, utc_now_iso
from mailbox_schema import validate_message
from plugin_logger import record_plugin_event
from postman_gateway import submit_command


def build_command(
    *,
    profile: str,
    session_id: str | None,
    question: str,
    parent_question_id: str | None = None,
) -> dict:
    scope = {
        "provider_id": "hermes",
        "profile": profile,
        "vault_path": str(DEFAULT_VAULT),
        "graph_path": str(DEFAULT_GRAPHIFY_SANDBOX / "graphify-out" / "graph.json"),
        "topic": question,
    }
    if session_id:
        scope["session_id"] = session_id
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "execute_deep_search",
        "kind": "command",
        "parent_question_id": parent_question_id,
        "producer": "hermes",
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "high",
        "scope": scope,
        "payload": {
            "capability": "query",
            "target_role": "deep_search_executor",
            "question": question,
            "inference_mode": "deterministic",
            "write_scope": "result",
        }
    }
    validate_message(message)
    return message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a bounded deep-search command into the mailbox.")
    parser.add_argument("--profile", default="wiki")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--question", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    message = build_command(
        profile=args.profile,
        session_id=args.session_id,
        question=args.question,
        parent_question_id=args.parent_question_id,
    )
    submit_command(message, namespace=args.mailbox_namespace)
    record_plugin_event(
        event_type="deep_search_command_emitted",
        actor="hermes",
        parent_question_id=message.get("parent_question_id"),
        profile=message.get("scope", {}).get("profile"),
        session_id=message.get("scope", {}).get("session_id"),
        query_text=args.question,
        artifacts={
            "command_id": message["message_id"],
            "target_role": message.get("payload", {}).get("target_role"),
            "mailbox_namespace": args.mailbox_namespace,
        },
        state={
            "capability": message.get("payload", {}).get("capability"),
            "write_scope": message.get("payload", {}).get("write_scope"),
        },
    )
    print(json.dumps(message, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

