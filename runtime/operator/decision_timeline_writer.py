from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from runtime.common.contract_validation import validate_contract_payload
from harness_common import utc_now_iso


SCHEMA_VERSION = "decision_timeline_event.v1"
DECISION_TIMELINE_EVENT_SCHEMA = "decision_timeline_event.v1.schema.json"


def _timeline_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, default=str)
    return "dte-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_decision_timeline_event(
    *,
    decision_owner: str,
    decision_kind: str,
    provider_source_event_ref: str,
    previous_decision_ref: str | None = None,
    new_decision_ref: str | None = None,
    reason_codes: Sequence[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "decision_owner": str(decision_owner),
        "event_kind": str(decision_kind),
        "decision_kind": str(decision_kind),
        "provider_source_event_ref": str(provider_source_event_ref),
        "previous_decision_ref": str(previous_decision_ref or ""),
        "new_decision_ref": str(new_decision_ref or ""),
        "reason_codes": [str(item) for item in (reason_codes or []) if str(item).strip()],
        "created_at": created_at or utc_now_iso(),
    }
    event["timeline_event_id"] = _timeline_id(event)
    validate_decision_timeline_event(event)
    return event


def validate_decision_timeline_event(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, DECISION_TIMELINE_EVENT_SCHEMA)


def build_memory_ticket_decision_timeline(
    *,
    provider_source_event: Mapping[str, Any],
    ring_id: str,
    node_id: str,
    category_path: Mapping[str, Any],
) -> list[dict[str, Any]]:
    provider_event_ref = str(provider_source_event.get("event_id") or "")
    category_ref = str((category_path.get("category_authority") or {}).get("decision_ref") or category_path.get("path") or "")
    return [
        build_decision_timeline_event(
            decision_owner="provider",
            decision_kind="initial_claim",
            provider_source_event_ref=provider_event_ref,
            new_decision_ref=str(provider_source_event.get("source_ref") or ""),
            reason_codes=["provider_source_event_captured"],
        ),
        build_decision_timeline_event(
            decision_owner="ms",
            decision_kind="storage_admission",
            provider_source_event_ref=provider_event_ref,
            previous_decision_ref=str(provider_source_event.get("source_ref") or ""),
            new_decision_ref=f"ring:{ring_id}",
            reason_codes=["source_ref_resolved", "memory_ticket_admitted"],
        ),
        build_decision_timeline_event(
            decision_owner="amundsen",
            decision_kind="category_attach",
            provider_source_event_ref=provider_event_ref,
            previous_decision_ref=f"ring:{ring_id}",
            new_decision_ref=category_ref,
            reason_codes=[
                "semantic_category_path_present",
                "graphify_is_advisory_not_sot",
                f"node:{node_id}",
            ],
        ),
    ]


__all__ = [
    "DECISION_TIMELINE_EVENT_SCHEMA",
    "SCHEMA_VERSION",
    "build_decision_timeline_event",
    "build_memory_ticket_decision_timeline",
    "validate_decision_timeline_event",
]
