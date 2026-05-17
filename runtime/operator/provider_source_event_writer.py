from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from runtime.common.contract_validation import validate_contract_payload
from harness_common import utc_now_iso


SCHEMA_VERSION = "provider_source_event.v1"
PROVIDER_SOURCE_EVENT_SCHEMA = "provider_source_event.v1.schema.json"


def _event_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, default=str)
    return "pse-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_provider_source_event(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    source_ref: str,
    message_index_range: Mapping[str, Any] | None,
    anchor_hash: str,
    event_role: str = "provider_answer",
    redaction_status: str = "pointer_only",
    captured_at: str | None = None,
) -> dict[str, Any]:
    timestamp = captured_at or utc_now_iso()
    event = {
        "schema_version": SCHEMA_VERSION,
        "provider_id": str(provider_id or "unknown"),
        "provider_profile": str(provider_profile or "unknown"),
        "provider_session_id": str(provider_session_id or "unknown"),
        "source_ref": str(source_ref or ""),
        "source_range": {"message_index_range": dict(message_index_range or {})},
        "message_index_range": dict(message_index_range or {}),
        "anchor_hash": str(anchor_hash or ""),
        "event_role": event_role,
        "created_at": timestamp,
        "captured_at": timestamp,
        "redaction_status": redaction_status,
    }
    event["event_id"] = _event_id(event)
    validate_provider_source_event(event)
    return event


def validate_provider_source_event(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, PROVIDER_SOURCE_EVENT_SCHEMA)


__all__ = [
    "PROVIDER_SOURCE_EVENT_SCHEMA",
    "SCHEMA_VERSION",
    "build_provider_source_event",
    "validate_provider_source_event",
]
