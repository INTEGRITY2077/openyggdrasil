from __future__ import annotations

import uuid
import re
from typing import Any, Mapping

from jsonschema.exceptions import ValidationError

from admission.decision_contracts import (
    validate_provider_runtime_integrity_result,
    validate_session_structure_signal,
)
from admission.session_admission_gate import evaluate_session_structure_signal
from harness_common import utc_now_iso


RECOVERABLE_RUNTIME_EVENTS = {
    "tool_call_arguments_repaired": "use_repaired_tool_call_arguments",
    "streaming_tool_call_repaired": "use_reassembled_streaming_tool_call",
    "codex_tool_call_id_recovered": "use_recovered_tool_call_id",
    "skill_preprocessed": "use_preprocessed_skill_payload",
    "raw_content_deduplicated": "use_deduplicated_runtime_context",
    "write_origin_metadata_present": "preserve_write_origin_metadata",
    "no_proxy_bypass_applied": "preserve_provider_network_route",
}

QUARANTINE_RUNTIME_EVENTS = {
    "interrupted_turn": "wait_for_stable_turn",
    "client_disconnect_snapshot_incomplete": "wait_for_complete_snapshot",
    "stream_cancelled_incomplete": "wait_for_complete_stream",
}

REJECT_RUNTIME_EVENTS = {
    "raw_payload_detected": "reject_raw_payload",
    "provider_session_mutation_requested": "reject_provider_session_mutation",
    "mailbox_mutation_requested": "reject_provider_mailbox_mutation",
    "canonical_claim_written_by_provider": "reject_provider_canonical_write",
}

SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
EVIDENCE_REF_KINDS = {
    "provider_session_source_ref",
    "provider_runtime_event",
    "provider_snapshot",
    "local_source_sot",
    "upstream_source_sot",
    "test_artifact",
}


def _clean_label(value: Any) -> str:
    return str(value or "").strip()


def _safe_label(value: Any) -> str:
    label = _clean_label(value)
    if not label:
        return ""
    if not SAFE_LABEL_RE.fullmatch(label):
        return "invalid_runtime_event_label"
    return label


def _unique(values: list[Any] | tuple[Any, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = _safe_label(value)
        if item and item not in result:
            result.append(item)
    return result


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = _clean_label(payload.get(key))
    return value or fallback


def _source_ref_evidence(signal: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = signal.get("source_ref")
    if isinstance(source_ref, Mapping):
        return {
            "kind": "provider_session_source_ref",
            "path_hint": _string_field(source_ref, "path_hint"),
            "range_hint": source_ref.get("range_hint"),
            "commit_ref": None,
            "source_url": None,
        }
    return {
        "kind": "provider_session_source_ref",
        "path_hint": "missing-source-ref",
        "range_hint": None,
        "commit_ref": None,
        "source_url": None,
    }


def _normalise_evidence_refs(
    signal: Mapping[str, Any],
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in evidence_refs or ():
        kind = _string_field(ref, "kind", "provider_runtime_event")
        if kind not in EVIDENCE_REF_KINDS:
            kind = "provider_runtime_event"
        refs.append(
            {
                "kind": kind,
                "path_hint": _string_field(ref, "path_hint"),
                "range_hint": ref.get("range_hint"),
                "commit_ref": ref.get("commit_ref"),
                "source_url": ref.get("source_url"),
            }
        )
    refs.append(_source_ref_evidence(signal))
    return refs[:12]


def _base_result(
    *,
    signal: Mapping[str, Any],
    status: str,
    admission_allowed: bool,
    reason_codes: list[str],
    runtime_event_labels: list[str],
    recovery_actions: list[str],
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    next_action: str,
) -> dict[str, Any]:
    result = {
        "schema_version": "provider_runtime_integrity_result.v1",
        "integrity_id": uuid.uuid4().hex,
        "signal_id": _string_field(signal, "signal_id", "invalid-signal"),
        "provider_id": _string_field(signal, "provider_id"),
        "provider_profile": _string_field(signal, "provider_profile"),
        "provider_session_id": _string_field(signal, "provider_session_id"),
        "session_uid": _string_field(signal, "session_uid"),
        "status": status,
        "admission_allowed": admission_allowed,
        "reason_codes": _unique(reason_codes),
        "runtime_event_labels": _unique(runtime_event_labels),
        "recovery_actions": _unique(recovery_actions),
        "evidence_refs": _normalise_evidence_refs(signal, evidence_refs),
        "next_action": next_action,
        "created_at": utc_now_iso(),
    }
    validate_provider_runtime_integrity_result(result)
    return result


def evaluate_provider_runtime_integrity(
    signal: Mapping[str, Any],
    *,
    runtime_event_labels: list[str] | tuple[str, ...] | None = None,
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Check provider-runtime safety before the admission gate.

    This layer is intentionally not semantic. It only decides whether the
    signal is safe to hand to admission after provider-runtime recovery events.
    """

    labels = _unique(list(runtime_event_labels or ()))
    try:
        validate_session_structure_signal(signal)
    except ValidationError:
        return _base_result(
            signal=signal,
            status="reject",
            admission_allowed=False,
            reason_codes=["signal_schema_invalid"],
            runtime_event_labels=labels,
            recovery_actions=[],
            evidence_refs=evidence_refs,
            next_action="reject_signal",
        )

    unknown_events = [
        label
        for label in labels
        if label not in RECOVERABLE_RUNTIME_EVENTS
        and label not in QUARANTINE_RUNTIME_EVENTS
        and label not in REJECT_RUNTIME_EVENTS
    ]
    reject_events = [label for label in labels if label in REJECT_RUNTIME_EVENTS]
    quarantine_events = [label for label in labels if label in QUARANTINE_RUNTIME_EVENTS]
    recoverable_events = [label for label in labels if label in RECOVERABLE_RUNTIME_EVENTS]

    if reject_events:
        return _base_result(
            signal=signal,
            status="reject",
            admission_allowed=False,
            reason_codes=["signal_schema_valid", "runtime_integrity_rejected"] + reject_events,
            runtime_event_labels=labels,
            recovery_actions=[REJECT_RUNTIME_EVENTS[label] for label in reject_events],
            evidence_refs=evidence_refs,
            next_action="reject_signal",
        )

    if unknown_events:
        return _base_result(
            signal=signal,
            status="quarantine",
            admission_allowed=False,
            reason_codes=["signal_schema_valid", "runtime_event_unknown"] + unknown_events,
            runtime_event_labels=labels,
            recovery_actions=["manual_runtime_review_required"],
            evidence_refs=evidence_refs,
            next_action="manual_review",
        )

    if quarantine_events:
        return _base_result(
            signal=signal,
            status="quarantine",
            admission_allowed=False,
            reason_codes=["signal_schema_valid", "runtime_integrity_quarantine"] + quarantine_events,
            runtime_event_labels=labels,
            recovery_actions=[QUARANTINE_RUNTIME_EVENTS[label] for label in quarantine_events],
            evidence_refs=evidence_refs,
            next_action="retry_after_stable_turn",
        )

    if recoverable_events:
        return _base_result(
            signal=signal,
            status="recovered",
            admission_allowed=True,
            reason_codes=["signal_schema_valid", "runtime_integrity_recovered"] + recoverable_events,
            runtime_event_labels=labels,
            recovery_actions=[RECOVERABLE_RUNTIME_EVENTS[label] for label in recoverable_events],
            evidence_refs=evidence_refs,
            next_action="run_session_admission_gate",
        )

    return _base_result(
        signal=signal,
        status="pass",
        admission_allowed=True,
        reason_codes=["signal_schema_valid", "runtime_integrity_clean"],
        runtime_event_labels=[],
        recovery_actions=[],
        evidence_refs=evidence_refs,
        next_action="run_session_admission_gate",
    )


def evaluate_integrity_then_admission(
    signal: Mapping[str, Any],
    *,
    runtime_event_labels: list[str] | tuple[str, ...] | None = None,
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    source_ref_exists: bool = True,
    source_ref_unavailable: bool = False,
    duplicate_signal: bool = False,
    privacy_risk_detected: bool = False,
) -> dict[str, Any]:
    integrity = evaluate_provider_runtime_integrity(
        signal,
        runtime_event_labels=runtime_event_labels,
        evidence_refs=evidence_refs,
    )
    if not integrity["admission_allowed"]:
        return {
            "integrity_result": integrity,
            "admission_verdict": None,
        }
    return {
        "integrity_result": integrity,
        "admission_verdict": evaluate_session_structure_signal(
            signal,
            source_ref_exists=source_ref_exists,
            source_ref_unavailable=source_ref_unavailable,
            duplicate_signal=duplicate_signal,
            privacy_risk_detected=privacy_risk_detected,
        ),
    }
