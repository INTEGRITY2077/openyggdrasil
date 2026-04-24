from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import validate_session_structure_signal
from attachments.provider_attachment import build_session_uid
from harness_common import utc_now_iso


ALLOWED_TRIGGER_TYPES = {
    "hard_trigger",
    "boundary_trigger",
    "correction_supersession_trigger",
    "context_pressure_trigger",
    "retrieval_need_trigger",
}
ALLOWED_PRIORITIES = {"immediate", "deferred", "review"}


def _normalize_reason_labels(value: list[str] | tuple[str, ...]) -> list[str]:
    labels: list[str] = []
    for item in value:
        label = str(item).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def build_session_structure_signal(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    turn_start: int,
    turn_end: int,
    trigger_type: str,
    reason_labels: list[str] | tuple[str, ...],
    surface_reason: str,
    source_path_hint: str,
    priority: str = "deferred",
    anchor_hash: str | None = None,
    symlink_hint: str | None = None,
    emitted_at: str | None = None,
) -> dict[str, Any]:
    """Build the small provider-emitted signal that starts structuring.

    This helper intentionally accepts no raw transcript, summary blob, claim,
    category, canonical path, or mailbox payload fields.
    """

    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    payload: dict[str, Any] = {
        "schema_version": "session_structure_signal.v1",
        "signal_id": uuid.uuid4().hex,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "turn_range": {"from": int(turn_start), "to": int(turn_end)},
        "trigger_type": trigger_type,
        "reason_labels": _normalize_reason_labels(reason_labels),
        "surface_reason": str(surface_reason).strip(),
        "priority": priority,
        "source_ref": {
            "kind": "provider_session",
            "path_hint": str(source_path_hint).strip(),
            "range_hint": f"turn:{int(turn_start)}-{int(turn_end)}",
            "symlink_hint": symlink_hint,
        },
        "anchor_hash": anchor_hash,
        "emitted_at": emitted_at or utc_now_iso(),
    }
    validate_session_structure_signal(payload)
    return payload


def assert_signal_only_payload(payload: Mapping[str, Any]) -> None:
    """Validate that a provider signal stayed within the signal-only boundary."""

    validate_session_structure_signal(payload)
