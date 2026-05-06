from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POSTMAN_DIR_NAME = "postman"
SESSIONS_DIR_NAME = "sessions"


def _ygg_root() -> Path:
    return Path.home() / ".yggdrasil"


def _postman_dir() -> Path:
    return _ygg_root() / POSTMAN_DIR_NAME


def _sessions_dir() -> Path:
    return _ygg_root() / SESSIONS_DIR_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _recipient_mailbox(recipient: str) -> Path:
    recipient = recipient.upper()
    if not recipient.startswith("OP"):
        raise ValueError(f"recipient must be OP#, got {recipient!r}")
    mailbox = _sessions_dir() / recipient
    mailbox.mkdir(parents=True, exist_ok=True)
    return mailbox


def submit_live_delivery(
    *,
    recipient: str,
    message_type: str,
    payload: dict[str, Any],
    provider_id: str,
    mail_id: str | None = None,
) -> dict[str, Any]:
    """Provider 요청을 Postman live-delivery packet으로 위탁하고 수신인 OP mailbox/live_inbox에 전달한다.

    Postman이 OP mailbox append 책임을 가진다. Provider/ygg는 이 함수를 호출해
    Postman에게 위탁할 뿐, OP mailbox 파일 형식을 직접 소유하지 않는다.
    """
    recipient = recipient.upper()
    mailbox = _recipient_mailbox(recipient)
    delivery_id = f"postman-{uuid.uuid4().hex[:8]}"
    timestamp = _now()

    if message_type == "save":
        mail_id = mail_id or f"tell-{uuid.uuid4().hex[:6]}"
        message_file_name = "intents.jsonl"
        message_row = {
            "mail_id": mail_id,
            "intent": "save",
            "payload": payload,
            "timestamp": timestamp,
            "provider_id": provider_id,
            "postman_delivery_id": delivery_id,
        }
        live_intent = "save"
    elif message_type == "query":
        mail_id = mail_id or f"ask-{uuid.uuid4().hex[:6]}"
        message_file_name = "queries.jsonl"
        message_row = {
            "mail_id": mail_id,
            "payload": payload,
            "timestamp": timestamp,
            "provider_id": provider_id,
            "postman_delivery_id": delivery_id,
        }
        live_intent = "query"
    elif message_type == "memory_ticket":
        mail_id = mail_id or f"memticket-{uuid.uuid4().hex[:6]}"
        message_file_name = "intents.jsonl"
        message_row = {
            "mail_id": mail_id,
            "intent": "memory_ticket",
            "payload": payload,
            "timestamp": timestamp,
            "provider_id": provider_id,
            "postman_delivery_id": delivery_id,
        }
        live_intent = "memory_ticket"
    else:
        raise ValueError(f"unsupported live delivery message_type={message_type!r}")

    packet = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "sender": "Provider",
        "recipient": recipient,
        "message_type": message_type,
        "payload": payload,
        "provider_id": provider_id,
        "created_at": timestamp,
        "status": "accepted",
    }
    live_event = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "sender": "Provider",
        "recipient": recipient,
        "intent": live_intent,
        "message_type": message_type,
        "payload": payload,
        "status": "delivered_to_live_inbox",
        "timestamp": timestamp,
    }
    message_file = mailbox / message_file_name
    delivery_log = {
        **packet,
        "status": "delivered",
        "mailbox": str(mailbox),
        "message_file": str(message_file),
        "intent_file": str(message_file) if message_type in ("save", "memory_ticket") else None,
        "query_file": str(message_file) if message_type == "query" else None,
        "live_inbox": str(mailbox / "live_inbox.jsonl"),
        "delivered_at": _now(),
    }

    postman_dir = _postman_dir()
    _append_jsonl(postman_dir / "outbox.jsonl", packet)
    _append_jsonl(message_file, message_row)
    _append_jsonl(mailbox / "live_inbox.jsonl", live_event)
    _append_jsonl(postman_dir / "delivery_log.jsonl", delivery_log)

    return {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "recipient": recipient,
        "message_type": message_type,
        "mailbox": str(mailbox),
        "message_file": str(message_file),
        "intent_file": str(message_file) if message_type in ("save", "memory_ticket") else None,
        "query_file": str(message_file) if message_type == "query" else None,
        "live_inbox": str(mailbox / "live_inbox.jsonl"),
        "outbox": str(postman_dir / "outbox.jsonl"),
        "delivery_log": str(postman_dir / "delivery_log.jsonl"),
        "status": "delivered",
    }


__all__ = ["submit_live_delivery"]
