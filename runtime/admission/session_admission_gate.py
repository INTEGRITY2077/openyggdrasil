from __future__ import annotations

import uuid
from typing import Any, Mapping

from jsonschema.exceptions import ValidationError

from admission.decision_contracts import (
    validate_session_admission_verdict,
    validate_session_structure_signal,
)
from admission.source_ref_resolver import resolve_signal_source_ref
from harness_common import utc_now_iso


ACCEPT_TRIGGERS = {
    "hard_trigger",
    "boundary_trigger",
    "correction_supersession_trigger",
    "retrieval_need_trigger",
}
DEFER_TRIGGERS = {"context_pressure_trigger"}
REJECT_REASON_LABELS = {
    "ambiguous_chatter",
    "smalltalk",
    "noise",
    "no_structuring_value",
}


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def _base_verdict(
    *,
    signal: Mapping[str, Any],
    verdict: str,
    reason_codes: list[str],
    source_ref_resolution: Mapping[str, Any],
    next_role: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "session_admission_verdict.v1",
        "verdict_id": uuid.uuid4().hex,
        "signal_id": _string_field(signal, "signal_id", "invalid-signal"),
        "provider_id": _string_field(signal, "provider_id"),
        "provider_profile": _string_field(signal, "provider_profile"),
        "provider_session_id": _string_field(signal, "provider_session_id"),
        "session_uid": _string_field(signal, "session_uid"),
        "verdict": verdict,
        "reason_codes": reason_codes,
        "source_ref_resolution": dict(source_ref_resolution),
        "next_role": next_role,
        "created_at": utc_now_iso(),
    }
    validate_session_admission_verdict(payload)
    return payload


def evaluate_session_structure_signal(
    signal: Mapping[str, Any],
    *,
    source_ref_exists: bool = True,
    source_ref_unavailable: bool = False,
    duplicate_signal: bool = False,
    privacy_risk_detected: bool = False,
) -> dict[str, Any]:
    """Deterministically admit, defer, or reject a provider structure signal."""

    source_ref_resolution = resolve_signal_source_ref(
        signal,
        source_ref_exists=source_ref_exists,
        source_ref_unavailable=source_ref_unavailable,
    )
    try:
        validate_session_structure_signal(signal)
    except ValidationError:
        return _base_verdict(
            signal=signal,
            verdict="reject",
            reason_codes=["schema_invalid"],
            source_ref_resolution=source_ref_resolution,
            next_role=None,
        )

    reason_codes = ["schema_valid"]
    if source_ref_resolution["status"] == "reject":
        return _base_verdict(
            signal=signal,
            verdict="reject",
            reason_codes=reason_codes + list(source_ref_resolution["reason_codes"]),
            source_ref_resolution=source_ref_resolution,
            next_role=None,
        )
    if source_ref_resolution["status"] == "unavailable":
        return _base_verdict(
            signal=signal,
            verdict="defer",
            reason_codes=reason_codes + list(source_ref_resolution["reason_codes"]),
            source_ref_resolution=source_ref_resolution,
            next_role="review_queue",
        )
    reason_codes.append("source_ref_resolved")

    if duplicate_signal:
        return _base_verdict(
            signal=signal,
            verdict="reject",
            reason_codes=reason_codes + ["duplicate_signal"],
            source_ref_resolution=source_ref_resolution,
            next_role=None,
        )

    if privacy_risk_detected:
        return _base_verdict(
            signal=signal,
            verdict="reject",
            reason_codes=reason_codes + ["privacy_risk_detected"],
            source_ref_resolution=source_ref_resolution,
            next_role=None,
        )

    labels = {str(label).strip() for label in signal.get("reason_labels", [])}
    if labels & REJECT_REASON_LABELS:
        return _base_verdict(
            signal=signal,
            verdict="reject",
            reason_codes=reason_codes + ["low_structuring_value"],
            source_ref_resolution=source_ref_resolution,
            next_role=None,
        )

    trigger_type = str(signal["trigger_type"])
    if trigger_type in DEFER_TRIGGERS:
        return _base_verdict(
            signal=signal,
            verdict="defer",
            reason_codes=reason_codes + ["context_pressure_only"],
            source_ref_resolution=source_ref_resolution,
            next_role="review_queue",
        )

    if trigger_type in ACCEPT_TRIGGERS:
        return _base_verdict(
            signal=signal,
            verdict="accept",
            reason_codes=reason_codes + [f"{trigger_type}_accepted"],
            source_ref_resolution=source_ref_resolution,
            next_role="seedkeeper",
        )

    return _base_verdict(
        signal=signal,
        verdict="reject",
        reason_codes=reason_codes + ["trigger_not_admissible"],
        source_ref_resolution=source_ref_resolution,
        next_role=None,
    )
