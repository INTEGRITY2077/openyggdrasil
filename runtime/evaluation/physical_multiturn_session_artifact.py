from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "physical_multiturn_session_artifact_bundle.v1.schema.json"

PHYSICAL_SESSION_SURFACE = "physical_hermes_multiturn_session"
LATER_LANE_REF_FIELDS = {
    "knowledge_forest_delta": "knowledge_forest_delta_refs",
    "graphify_snapshot": "graphify_snapshot_refs",
    "mailbox_receipt": "mailbox_receipt_refs",
    "reasoning_lease_isolation": "reasoning_lease_isolation_refs",
}
EVIDENCE_REQUIREMENTS = {
    PHYSICAL_SESSION_SURFACE: "physical_multiturn_session_artifact_bundle_ref_non_empty",
    "knowledge_forest_delta": "knowledge_forest_delta_ref_non_empty",
    "graphify_snapshot": "graphify_snapshot_ref_non_empty",
    "mailbox_receipt": "mailbox_receipt_ref_non_empty",
    "reasoning_lease_isolation": "reasoning_lease_isolation_ref_non_empty",
}


@lru_cache(maxsize=1)
def load_physical_multiturn_session_artifact_bundle_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _refs(payload: Mapping[str, Any], key: str) -> list[str]:
    return [str(item).strip() for item in payload.get(key) or [] if str(item).strip()]


def _missing_later_lane_surfaces(payload: Mapping[str, Any]) -> list[str]:
    return [
        surface
        for surface, ref_field in LATER_LANE_REF_FIELDS.items()
        if not _refs(payload, ref_field)
    ]


def _evidence_set(payload: Mapping[str, Any]) -> set[str]:
    return {str(item).strip() for item in payload.get("evidence_required") or [] if str(item).strip()}


def _typed_surfaces(payload: Mapping[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in payload.get("typed_unavailable_surfaces") or []
        if str(item).strip()
    }


def _require_physical_live_rules(payload: Mapping[str, Any]) -> None:
    required_ref_fields = (
        "session_ref",
        "session_started_at",
        "session_finished_at",
        "skill_attachment_ref",
        "safe_transcript_ref",
    )
    for field in required_ref_fields:
        if not _nonempty(payload.get(field)):
            raise ValueError(f"physical_live bundle requires {field}")

    if int(payload.get("turn_count") or 0) < 2:
        raise ValueError("physical_live bundle requires turn_count >= 2")
    if int(payload.get("user_message_count") or 0) < 2:
        raise ValueError("physical_live bundle requires user_message_count >= 2")
    if int(payload.get("assistant_message_count") or 0) < 1:
        raise ValueError("physical_live bundle requires assistant_message_count >= 1")
    if PHYSICAL_SESSION_SURFACE in _typed_surfaces(payload):
        raise ValueError("physical_live bundle cannot mark physical_hermes_multiturn_session unavailable")
    if str(payload.get("decision")) != "e2e1_physical_session_artifact_valid":
        raise ValueError("physical_live bundle decision must be e2e1_physical_session_artifact_valid")
    if str(payload.get("readiness_state")) != "ready_for_e2e2":
        raise ValueError("physical_live bundle readiness_state must be ready_for_e2e2")

    missing_lanes = _missing_later_lane_surfaces(payload)
    evidence = _evidence_set(payload)
    missing_evidence = [
        EVIDENCE_REQUIREMENTS[surface]
        for surface in missing_lanes
        if EVIDENCE_REQUIREMENTS[surface] not in evidence
    ]
    if missing_evidence:
        raise ValueError(f"missing evidence_required entries: {', '.join(missing_evidence)}")
    if missing_lanes:
        if str(payload.get("claim_scope")) != "e2e1_physical_session_only":
            raise ValueError("missing later E2E lanes require claim_scope=e2e1_physical_session_only")
        if str(payload.get("rerun_condition")) != "provide_live_e2e_later_lane_artifacts":
            raise ValueError("missing later E2E lanes require rerun_condition=provide_live_e2e_later_lane_artifacts")


def _require_typed_unavailable_rules(payload: Mapping[str, Any]) -> None:
    if str(payload.get("decision")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable bundle decision must be typed_unavailable_not_live_proven")
    if str(payload.get("readiness_state")) != "not_ready":
        raise ValueError("typed unavailable bundle readiness_state must be not_ready")
    if str(payload.get("claim_scope")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable bundle claim_scope must be typed_unavailable_not_live_proven")
    if str(payload.get("rerun_condition")) != "provide_live_e2e_session_artifact_bundle":
        raise ValueError("typed unavailable bundle must require provide_live_e2e_session_artifact_bundle")
    if PHYSICAL_SESSION_SURFACE not in _typed_surfaces(payload):
        raise ValueError("typed unavailable bundle must name physical_hermes_multiturn_session")

    evidence = _evidence_set(payload)
    missing_evidence = [
        EVIDENCE_REQUIREMENTS[surface]
        for surface in (PHYSICAL_SESSION_SURFACE, *LATER_LANE_REF_FIELDS)
        if EVIDENCE_REQUIREMENTS[surface] not in evidence
    ]
    if missing_evidence:
        raise ValueError(f"missing evidence_required entries: {', '.join(missing_evidence)}")


def validate_physical_multiturn_session_artifact_bundle(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_physical_multiturn_session_artifact_bundle_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")

    session_kind = str(payload.get("session_kind") or "")
    if session_kind == "physical_live":
        _require_physical_live_rules(payload)
    elif session_kind == "typed_unavailable_not_live_proven":
        _require_typed_unavailable_rules(payload)
    else:
        raise ValueError(f"unknown session_kind: {session_kind}")


def build_physical_multiturn_session_artifact_bundle(
    *,
    artifact_bundle_id: str,
    provider_profile: str,
    session_ref: str,
    session_started_at: str,
    session_finished_at: str,
    session_summary: str,
    turn_count: int,
    user_message_count: int,
    assistant_message_count: int,
    skill_attachment_ref: str,
    safe_transcript_ref: str,
    mailbox_receipt_refs: Sequence[str] = (),
    knowledge_forest_delta_refs: Sequence[str] = (),
    graphify_snapshot_refs: Sequence[str] = (),
    reasoning_lease_isolation_refs: Sequence[str] = (),
    checked_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "physical_multiturn_session_artifact_bundle.v1",
        "artifact_bundle_id": str(artifact_bundle_id),
        "provider_name": "hermes",
        "provider_profile": str(provider_profile),
        "session_kind": "physical_live",
        "session_ref": str(session_ref),
        "session_started_at": str(session_started_at),
        "session_finished_at": str(session_finished_at),
        "session_summary": str(session_summary),
        "turn_count": int(turn_count),
        "user_message_count": int(user_message_count),
        "assistant_message_count": int(assistant_message_count),
        "skill_attachment_ref": str(skill_attachment_ref),
        "safe_transcript_ref": str(safe_transcript_ref),
        "raw_transcript_included": False,
        "mailbox_receipt_refs": [str(ref) for ref in mailbox_receipt_refs],
        "knowledge_forest_delta_refs": [str(ref) for ref in knowledge_forest_delta_refs],
        "graphify_snapshot_refs": [str(ref) for ref in graphify_snapshot_refs],
        "reasoning_lease_isolation_refs": [str(ref) for ref in reasoning_lease_isolation_refs],
        "decision": "e2e1_physical_session_artifact_valid",
        "readiness_state": "ready_for_e2e2",
        "checked_at": checked_at or utc_now_iso(),
    }
    missing_lanes = _missing_later_lane_surfaces(payload)
    payload["typed_unavailable_surfaces"] = missing_lanes
    payload["evidence_required"] = [EVIDENCE_REQUIREMENTS[surface] for surface in missing_lanes]
    payload["claim_scope"] = (
        "e2e1_physical_session_only"
        if missing_lanes
        else "full_live_e2e_artifact_bundle_candidate"
    )
    payload["rerun_condition"] = (
        "provide_live_e2e_later_lane_artifacts" if missing_lanes else None
    )
    validate_physical_multiturn_session_artifact_bundle(payload)
    return payload


def build_typed_unavailable_physical_multiturn_session_artifact_bundle(
    *,
    artifact_bundle_id: str,
    provider_profile: str,
    reason_code: str,
    provider_name: str = "hermes",
    checked_at: str | None = None,
) -> dict[str, Any]:
    surfaces = [PHYSICAL_SESSION_SURFACE, *LATER_LANE_REF_FIELDS.keys()]
    payload = {
        "schema_version": "physical_multiturn_session_artifact_bundle.v1",
        "artifact_bundle_id": str(artifact_bundle_id),
        "provider_name": str(provider_name),
        "provider_profile": str(provider_profile),
        "session_kind": "typed_unavailable_not_live_proven",
        "session_ref": None,
        "session_started_at": None,
        "session_finished_at": None,
        "session_summary": f"Physical Hermes multi-turn session artifact is unavailable: {reason_code}.",
        "turn_count": 0,
        "user_message_count": 0,
        "assistant_message_count": 0,
        "skill_attachment_ref": None,
        "safe_transcript_ref": None,
        "raw_transcript_included": False,
        "mailbox_receipt_refs": [],
        "knowledge_forest_delta_refs": [],
        "graphify_snapshot_refs": [],
        "reasoning_lease_isolation_refs": [],
        "typed_unavailable_surfaces": surfaces,
        "rerun_condition": "provide_live_e2e_session_artifact_bundle",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in surfaces],
        "claim_scope": "typed_unavailable_not_live_proven",
        "decision": "typed_unavailable_not_live_proven",
        "readiness_state": "not_ready",
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_physical_multiturn_session_artifact_bundle(payload)
    return payload
