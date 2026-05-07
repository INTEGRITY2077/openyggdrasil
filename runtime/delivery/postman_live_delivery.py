from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POSTMAN_DIR_NAME = "postman"
SESSIONS_DIR_NAME = "sessions"
CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"
MEMORY_TICKET_CONTRACT_FIELDS = {
    "source_ref",
    "intent_field",
    "decomposition_guard",
    "min_split_unit",
    "why_not_atomic",
    "topic_hint",
    "category_community_hint",
    "decision_capsule",
    "claim_capsule",
}
CLASSIC_SAVE_MARKERS = (
    "결정:",
    "확정:",
    "채택:",
    "폐기:",
    "규칙:",
    "정책:",
    "앞으로",
    "반드시",
    "확인:",
    "원인:",
    "구조:",
    "설계:",
    "아키텍처:",
    "패턴:",
)


class PostmanIntegrityError(ValueError):
    """Raised when Postman rejects a malformed Provider→Operator letter."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        super().__init__(str(result.get("reason") or "postman_integrity_rejected"))


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


def _has_classic_save_marker(text: str) -> bool:
    return any(marker in text for marker in CLASSIC_SAVE_MARKERS)


def _looks_like_memory_ticket_text(text: str) -> bool:
    lowered = text.lower()
    return sum(1 for field in MEMORY_TICKET_CONTRACT_FIELDS if f"{field.lower()}:" in lowered) >= 3


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_index_range(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, int) and isinstance(end, int) and start >= 0 and end >= start


def _valid_id_range(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, (int, str)) and isinstance(end, (int, str)) and str(start) != "" and str(end) != ""


def _is_atom_tag_hint(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return True
    if len(normalized) <= 5:
        return True
    if " " not in normalized and "/" not in normalized and "community" not in normalized.lower() and "category" not in normalized.lower():
        return True
    return False


def _admit_memory_ticket_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if payload.get("schema_version") != "memory_ticket.v1":
        return False, "invalid_schema_version"
    for key in ("source_ref", "provider_session_id", "surface_reason", "commit_watermark"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    has_index_range = "message_index_range" in payload
    has_id_range = "message_id_range" in payload
    if has_index_range == has_id_range:
        return False, "invalid_message_range_choice"
    if has_index_range and not _valid_index_range(payload.get("message_index_range")):
        return False, "invalid_message_index_range"
    if has_id_range and not _valid_id_range(payload.get("message_id_range")):
        return False, "invalid_message_id_range"
    if not _is_nonempty_string(payload.get("anchor_hash")):
        return False, "missing_anchor_hash"
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("anchor_hash"))):
        return False, "invalid_anchor_hash"
    for key in ("intent_field", "decomposition_guard", "min_split_unit", "why_not_atomic", "topic_hint", "category_community_hint"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    if str(payload.get("decomposition_guard")) != CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD:
        return False, "invalid_decomposition_guard"
    if str(payload.get("min_split_unit")) not in {"paragraph_intent", "topic_decision_cluster"}:
        return False, "invalid_min_split_unit"
    if _is_atom_tag_hint(str(payload.get("category_community_hint") or "")):
        return False, "category_community_hint_too_atomic"
    return True, "admitted"


def _validate_letter_integrity(*, message_type: str, payload: dict[str, Any]) -> tuple[bool, str, str]:
    """Postman pre-delivery inspection. Returns (accepted, reason, evidence)."""
    if not isinstance(payload, dict):
        return False, "payload_not_object", "Postman requires object payload before mailbox delivery"

    if message_type == "save":
        context_snapshot = payload.get("context_snapshot")
        if not isinstance(context_snapshot, str) or not context_snapshot.strip():
            return False, "missing_context_snapshot", "classic save requires non-empty payload.context_snapshot"
        if _looks_like_memory_ticket_text(context_snapshot):
            return (
                False,
                "memory_ticket_fields_in_classic_context_snapshot",
                "MemoryTicket contract fields must be top-level payload of message_type=memory_ticket, not classic save context_snapshot",
            )
        if not payload.get("ptc") and not _has_classic_save_marker(context_snapshot):
            return (
                False,
                "missing_classic_save_marker",
                "classic save uses extract_decisions(context_snapshot); markerless text would produce zero nodes",
            )
        return True, "accepted", "classic save integrity accepted"

    if message_type == "query":
        query_text = payload.get("query_text") or payload.get("query")
        if not isinstance(query_text, str) or not query_text.strip():
            return False, "missing_query_text", "query delivery requires non-empty payload.query_text"
        return True, "accepted", "query integrity accepted"

    if message_type == "memory_ticket":
        accepted, reason = _admit_memory_ticket_payload(payload)
        if not accepted:
            return False, reason, "memory_ticket requires source_ref/range/hash/paragraph-intent/topic-community contract fields"
        return True, "accepted", "memory_ticket integrity accepted"

    return False, "unsupported_message_type", f"unsupported live delivery message_type={message_type!r}"


def _reject_delivery(
    *,
    delivery_id: str,
    mail_id: str,
    recipient: str,
    message_type: str,
    payload: dict[str, Any],
    provider_id: str,
    reason: str,
    evidence: str,
    timestamp: str,
) -> dict[str, Any]:
    result = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "sender": "Provider",
        "recipient": recipient,
        "message_type": message_type,
        "payload": payload,
        "provider_id": provider_id,
        "created_at": timestamp,
        "status": "rejected",
        "reason": reason,
        "evidence": evidence,
        "hard_nonclaim": "not_delivered_to_operator_mailbox",
    }
    _append_jsonl(_postman_dir() / "rejected.jsonl", result)
    return result


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
    if not recipient.startswith("OP"):
        raise ValueError(f"recipient must be OP#, got {recipient!r}")
    delivery_id = f"postman-{uuid.uuid4().hex[:8]}"
    timestamp = _now()

    if message_type == "save":
        mail_id = mail_id or f"tell-{uuid.uuid4().hex[:6]}"
    elif message_type == "query":
        mail_id = mail_id or f"ask-{uuid.uuid4().hex[:6]}"
    elif message_type == "memory_ticket":
        mail_id = mail_id or f"memticket-{uuid.uuid4().hex[:6]}"
    else:
        mail_id = mail_id or f"mail-{uuid.uuid4().hex[:6]}"

    accepted, reason, evidence = _validate_letter_integrity(message_type=message_type, payload=payload)
    if not accepted:
        rejection = _reject_delivery(
            delivery_id=delivery_id,
            mail_id=mail_id,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            provider_id=provider_id,
            reason=reason,
            evidence=evidence,
            timestamp=timestamp,
        )
        raise PostmanIntegrityError(rejection)

    mailbox = _recipient_mailbox(recipient)

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


__all__ = ["PostmanIntegrityError", "submit_live_delivery"]
