from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from evaluation.physical_multiturn_session_artifact import (
    validate_physical_multiturn_session_artifact_bundle,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "knowledge_forest_delta_from_live_session.v1.schema.json"

DELTA_SURFACE = "knowledge_forest_delta"
LATER_LANE_REF_FIELDS = {
    "graphify_snapshot": "graphify_snapshot_refs",
    "mailbox_receipt": "mailbox_receipt_refs",
    "reasoning_lease_isolation": "reasoning_lease_isolation_refs",
}
EVIDENCE_REQUIREMENTS = {
    DELTA_SURFACE: "knowledge_forest_delta_ref_non_empty",
    "graphify_snapshot": "graphify_snapshot_ref_non_empty",
    "mailbox_receipt": "mailbox_receipt_ref_non_empty",
    "reasoning_lease_isolation": "reasoning_lease_isolation_ref_non_empty",
}


@lru_cache(maxsize=1)
def load_knowledge_forest_delta_from_live_session_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _refs(payload: Mapping[str, Any], key: str) -> list[Any]:
    return [item for item in payload.get(key) or [] if item]


def _string_refs(payload: Mapping[str, Any], key: str) -> list[str]:
    return [str(item).strip() for item in payload.get(key) or [] if str(item).strip()]


def _typed_surfaces(payload: Mapping[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in payload.get("typed_unavailable_surfaces") or []
        if str(item).strip()
    }


def _evidence_set(payload: Mapping[str, Any]) -> set[str]:
    return {str(item).strip() for item in payload.get("evidence_required") or [] if str(item).strip()}


def _missing_later_lane_surfaces(payload: Mapping[str, Any]) -> list[str]:
    return [
        surface
        for surface, ref_field in LATER_LANE_REF_FIELDS.items()
        if not _string_refs(payload, ref_field)
    ]


def _require_source_bundle(payload: Mapping[str, Any], source_bundle: Mapping[str, Any] | None) -> None:
    if source_bundle is None:
        return
    if source_bundle.get("session_kind") != "physical_live":
        raise ValueError("source_bundle must be physical_live")
    if source_bundle.get("readiness_state") != "ready_for_e2e2":
        raise ValueError("source_bundle must be ready_for_e2e2")
    validate_physical_multiturn_session_artifact_bundle(source_bundle)
    if payload.get("source_artifact_bundle_id") != source_bundle.get("artifact_bundle_id"):
        raise ValueError("source_artifact_bundle_id must match source_bundle.artifact_bundle_id")
    if payload.get("provider_name") != source_bundle.get("provider_name"):
        raise ValueError("provider_name must match source_bundle")
    if payload.get("provider_profile") != source_bundle.get("provider_profile"):
        raise ValueError("provider_profile must match source_bundle")
    if payload.get("session_ref") != source_bundle.get("session_ref"):
        raise ValueError("session_ref must match source_bundle")


def _require_durable_delta_rules(payload: Mapping[str, Any]) -> None:
    required_ref_fields = (
        "canonical_refs",
        "provenance_refs",
        "lifecycle_refs",
        "source_turn_refs",
    )
    for field in required_ref_fields:
        if not _refs(payload, field):
            raise ValueError(f"{field} are required for durable knowledge forest delta")

    if int(payload.get("safe_evidence_pointer_count") or 0) < 4:
        raise ValueError("safe_evidence_pointer_count must be >= 4 for durable delta")
    if str(payload.get("source_session_kind")) != "physical_live":
        raise ValueError("durable delta requires source_session_kind=physical_live")
    if str(payload.get("canonicality")) != "sot":
        raise ValueError("durable delta requires canonicality=sot")
    if str(payload.get("mutation_scope")) != "vault_topic_page_with_provenance":
        raise ValueError("durable delta requires vault_topic_page_with_provenance mutation_scope")
    if str(payload.get("decision")) != "e2e2_knowledge_forest_delta_valid":
        raise ValueError("durable delta decision must be e2e2_knowledge_forest_delta_valid")
    if str(payload.get("readiness_state")) != "ready_for_e2e3":
        raise ValueError("durable delta readiness_state must be ready_for_e2e3")
    if DELTA_SURFACE in _typed_surfaces(payload):
        raise ValueError("durable delta cannot mark knowledge_forest_delta unavailable")

    missing_lanes = _missing_later_lane_surfaces(payload)
    typed_surfaces = _typed_surfaces(payload)
    missing_typed = [surface for surface in missing_lanes if surface not in typed_surfaces]
    if missing_typed:
        raise ValueError(f"typed_unavailable_surfaces must include: {', '.join(missing_typed)}")

    evidence = _evidence_set(payload)
    missing_evidence = [
        EVIDENCE_REQUIREMENTS[surface]
        for surface in missing_lanes
        if EVIDENCE_REQUIREMENTS[surface] not in evidence
    ]
    if missing_evidence:
        raise ValueError(f"missing evidence_required entries: {', '.join(missing_evidence)}")
    if missing_lanes:
        if str(payload.get("claim_scope")) != "e2e2_knowledge_forest_delta_only":
            raise ValueError("missing later E2E lanes require claim_scope=e2e2_knowledge_forest_delta_only")
        if str(payload.get("rerun_condition")) != "provide_live_e2e_visibility_and_consumption_artifacts":
            raise ValueError(
                "missing later E2E lanes require rerun_condition=provide_live_e2e_visibility_and_consumption_artifacts"
            )


def _require_typed_unavailable_rules(payload: Mapping[str, Any]) -> None:
    if str(payload.get("durability_state")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable delta durability_state must be typed_unavailable_not_live_proven")
    if str(payload.get("canonicality")) != "not_available":
        raise ValueError("typed unavailable delta canonicality must be not_available")
    if str(payload.get("mutation_scope")) != "not_available":
        raise ValueError("typed unavailable delta mutation_scope must be not_available")
    if str(payload.get("decision")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable delta decision must be typed_unavailable_not_live_proven")
    if str(payload.get("readiness_state")) != "not_ready":
        raise ValueError("typed unavailable delta readiness_state must be not_ready")
    if str(payload.get("claim_scope")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable delta claim_scope must be typed_unavailable_not_live_proven")
    if str(payload.get("rerun_condition")) != "provide_knowledge_forest_delta_from_live_session":
        raise ValueError("typed unavailable delta must require provide_knowledge_forest_delta_from_live_session")

    typed_surfaces = _typed_surfaces(payload)
    required_surfaces = {DELTA_SURFACE, *LATER_LANE_REF_FIELDS}
    missing_surfaces = sorted(required_surfaces - typed_surfaces)
    if missing_surfaces:
        raise ValueError(f"typed_unavailable_surfaces must include: {', '.join(missing_surfaces)}")

    evidence = _evidence_set(payload)
    missing_evidence = [
        EVIDENCE_REQUIREMENTS[surface]
        for surface in required_surfaces
        if EVIDENCE_REQUIREMENTS[surface] not in evidence
    ]
    if missing_evidence:
        raise ValueError(f"missing evidence_required entries: {', '.join(missing_evidence)}")


def validate_knowledge_forest_delta_from_live_session(
    payload: Mapping[str, Any],
    *,
    source_bundle: Mapping[str, Any] | None = None,
) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_knowledge_forest_delta_from_live_session_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    _require_source_bundle(payload, source_bundle)

    durability_state = str(payload.get("durability_state") or "")
    if durability_state == "durable":
        _require_durable_delta_rules(payload)
    elif durability_state == "typed_unavailable_not_live_proven":
        _require_typed_unavailable_rules(payload)
    else:
        raise ValueError(f"unknown durability_state: {durability_state}")


def build_knowledge_forest_delta_from_live_session(
    *,
    source_bundle: Mapping[str, Any],
    delta_id: str,
    canonical_refs: Sequence[Mapping[str, Any]],
    provenance_refs: Sequence[Mapping[str, Any]],
    lifecycle_refs: Sequence[Mapping[str, Any]],
    source_turn_refs: Sequence[str],
    checked_at: str | None = None,
) -> dict[str, Any]:
    validate_physical_multiturn_session_artifact_bundle(source_bundle)
    payload = {
        "schema_version": "knowledge_forest_delta_from_live_session.v1",
        "delta_id": str(delta_id),
        "source_artifact_bundle_id": str(source_bundle["artifact_bundle_id"]),
        "provider_name": str(source_bundle["provider_name"]),
        "provider_profile": str(source_bundle["provider_profile"]),
        "session_ref": str(source_bundle["session_ref"]),
        "source_session_kind": str(source_bundle["session_kind"]),
        "delta_kind": "knowledge_forest_delta",
        "durability_state": "durable",
        "canonicality": "sot",
        "mutation_scope": "vault_topic_page_with_provenance",
        "canonical_refs": [dict(ref) for ref in canonical_refs],
        "provenance_refs": [dict(ref) for ref in provenance_refs],
        "lifecycle_refs": [dict(ref) for ref in lifecycle_refs],
        "source_turn_refs": [str(ref) for ref in source_turn_refs],
        "safe_evidence_pointer_count": (
            len(canonical_refs) + len(provenance_refs) + len(lifecycle_refs) + len(source_turn_refs)
        ),
        "raw_transcript_included": False,
        "graphify_snapshot_refs": [],
        "mailbox_receipt_refs": [],
        "reasoning_lease_isolation_refs": [],
        "typed_unavailable_surfaces": list(LATER_LANE_REF_FIELDS.keys()),
        "rerun_condition": "provide_live_e2e_visibility_and_consumption_artifacts",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in LATER_LANE_REF_FIELDS],
        "claim_scope": "e2e2_knowledge_forest_delta_only",
        "decision": "e2e2_knowledge_forest_delta_valid",
        "readiness_state": "ready_for_e2e3",
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_knowledge_forest_delta_from_live_session(payload, source_bundle=source_bundle)
    return payload


def build_typed_unavailable_knowledge_forest_delta_from_live_session(
    *,
    source_bundle: Mapping[str, Any],
    delta_id: str,
    reason_code: str,
    checked_at: str | None = None,
) -> dict[str, Any]:
    validate_physical_multiturn_session_artifact_bundle(source_bundle)
    surfaces = [DELTA_SURFACE, *LATER_LANE_REF_FIELDS.keys()]
    payload = {
        "schema_version": "knowledge_forest_delta_from_live_session.v1",
        "delta_id": str(delta_id),
        "source_artifact_bundle_id": str(source_bundle["artifact_bundle_id"]),
        "provider_name": str(source_bundle["provider_name"]),
        "provider_profile": str(source_bundle["provider_profile"]),
        "session_ref": str(source_bundle["session_ref"]),
        "source_session_kind": str(source_bundle["session_kind"]),
        "delta_kind": "knowledge_forest_delta",
        "durability_state": "typed_unavailable_not_live_proven",
        "canonicality": "not_available",
        "mutation_scope": "not_available",
        "canonical_refs": [],
        "provenance_refs": [],
        "lifecycle_refs": [],
        "source_turn_refs": [],
        "safe_evidence_pointer_count": 0,
        "raw_transcript_included": False,
        "graphify_snapshot_refs": [],
        "mailbox_receipt_refs": [],
        "reasoning_lease_isolation_refs": [],
        "typed_unavailable_surfaces": surfaces,
        "rerun_condition": "provide_knowledge_forest_delta_from_live_session",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in surfaces],
        "claim_scope": "typed_unavailable_not_live_proven",
        "decision": "typed_unavailable_not_live_proven",
        "readiness_state": "not_ready",
        "checked_at": checked_at or utc_now_iso(),
    }
    if reason_code:
        payload["evidence_required"] = list(dict.fromkeys(payload["evidence_required"]))
    validate_knowledge_forest_delta_from_live_session(payload, source_bundle=source_bundle)
    return payload
