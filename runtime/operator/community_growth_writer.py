from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from runtime.common.contract_validation import validate_contract_payload
from harness_common import utc_now_iso


SCHEMA_VERSION = "community_growth_event.v1"
COMMUNITY_GROWTH_EVENT_SCHEMA = "community_growth_event.v1.schema.json"


def _growth_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, default=str)
    return "cge-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_community_growth_event(
    *,
    community_id: str,
    event_kind: str,
    provider_source_event_ref: str,
    decision_timeline_event_ref: str,
    topic_key: str,
    reason_codes: Sequence[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "community_id": str(community_id),
        "event_kind": str(event_kind),
        "provider_source_event_ref": str(provider_source_event_ref),
        "decision_timeline_event_ref": str(decision_timeline_event_ref),
        "topic_key": str(topic_key),
        "reason_codes": [str(item) for item in (reason_codes or []) if str(item).strip()],
        "created_at": created_at or utc_now_iso(),
    }
    event["growth_event_id"] = _growth_id(event)
    validate_community_growth_event(event)
    return event


def validate_community_growth_event(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, COMMUNITY_GROWTH_EVENT_SCHEMA)


__all__ = [
    "COMMUNITY_GROWTH_EVENT_SCHEMA",
    "SCHEMA_VERSION",
    "build_community_growth_event",
    "validate_community_growth_event",
]
