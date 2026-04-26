from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from evaluation.knowledge_forest_delta_from_live_session import (
    validate_knowledge_forest_delta_from_live_session,
)
from harness_common import utc_now_iso
from retrieval.graphify_snapshot_adapter import build_graphify_snapshot_failure_payload
from retrieval.graphify_snapshot_manifest import (
    build_graphify_snapshot_manifest,
    validate_graphify_snapshot_manifest,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "graphify_snapshot_from_live_delta.v1.schema.json"

GRAPHIFY_SURFACE = "graphify_snapshot"
LATER_LANE_REF_FIELDS = {
    "mailbox_receipt": "mailbox_receipt_refs",
    "reasoning_lease_isolation": "reasoning_lease_isolation_refs",
}
EVIDENCE_REQUIREMENTS = {
    GRAPHIFY_SURFACE: "graphify_snapshot_ref_non_empty",
    "mailbox_receipt": "mailbox_receipt_ref_non_empty",
    "reasoning_lease_isolation": "reasoning_lease_isolation_ref_non_empty",
}


@lru_cache(maxsize=1)
def load_graphify_snapshot_from_live_delta_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


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


def _require_false(payload: Mapping[str, Any], key: str) -> None:
    if payload.get(key) is not False:
        raise ValueError(f"{key} must be false")


def _require_source_delta(payload: Mapping[str, Any], source_delta: Mapping[str, Any] | None) -> None:
    if source_delta is None:
        return
    if payload.get("source_delta_id") != source_delta.get("delta_id"):
        raise ValueError("source_delta_id must match source_delta.delta_id")
    if source_delta.get("readiness_state") != "ready_for_e2e3":
        raise ValueError("source_delta must be ready_for_e2e3")
    if source_delta.get("decision") != "e2e2_knowledge_forest_delta_valid":
        raise ValueError("source_delta decision must be e2e2_knowledge_forest_delta_valid")
    validate_knowledge_forest_delta_from_live_session(source_delta)
    if payload.get("source_artifact_bundle_id") != source_delta.get("source_artifact_bundle_id"):
        raise ValueError("source_artifact_bundle_id must match source_delta")
    if payload.get("provider_name") != source_delta.get("provider_name"):
        raise ValueError("provider_name must match source_delta")
    if payload.get("provider_profile") != source_delta.get("provider_profile"):
        raise ValueError("provider_profile must match source_delta")
    if payload.get("session_ref") != source_delta.get("session_ref"):
        raise ValueError("session_ref must match source_delta")


def _require_non_sot_boundaries(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    _require_false(payload, "raw_transcript_included")
    _require_false(payload, "graphify_is_sot")
    _require_false(payload, "provider_may_answer_from_graphify_alone")
    _require_false(payload, "canonical_output_allowed")

    policy = manifest.get("provenance_policy") or {}
    if policy.get("graphify_is_sot") is not False:
        raise ValueError("Graphify manifest graphify_is_sot must be false")
    if policy.get("must_verify_against_sot") is not True:
        raise ValueError("Graphify manifest must_verify_against_sot must be true")
    if policy.get("raw_session_copy_allowed") is not False:
        raise ValueError("Graphify manifest raw_session_copy_allowed must be false")
    if policy.get("provider_may_answer_from_graphify_alone") is not False:
        raise ValueError("Graphify manifest provider_may_answer_from_graphify_alone must be false")


def _require_available_snapshot_rules(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    if GRAPHIFY_SURFACE in _typed_surfaces(payload):
        raise ValueError("available Graphify snapshot cannot mark graphify_snapshot unavailable")
    if str(payload.get("decision")) != "e2e3_graphify_snapshot_valid":
        raise ValueError("available Graphify snapshot decision must be e2e3_graphify_snapshot_valid")
    if str(payload.get("readiness_state")) != "ready_for_e2e4":
        raise ValueError("available Graphify snapshot readiness_state must be ready_for_e2e4")
    if str(payload.get("claim_scope")) != "e2e3_graphify_snapshot_only":
        raise ValueError("available Graphify snapshot requires claim_scope=e2e3_graphify_snapshot_only")
    if str(payload.get("rerun_condition")) != "provide_mailbox_and_reasoning_lease_artifacts":
        raise ValueError(
            "missing later E2E lanes require rerun_condition=provide_mailbox_and_reasoning_lease_artifacts"
        )
    if int(payload.get("safe_evidence_pointer_count") or 0) < 4:
        raise ValueError("safe_evidence_pointer_count must be >= 4 for available Graphify snapshot")
    if not payload.get("snapshot_ref"):
        raise ValueError("available Graphify snapshot requires snapshot_ref")
    if not _string_refs(payload, "source_delta_refs"):
        raise ValueError("available Graphify snapshot requires source_delta_refs")
    for field in ("graph_path", "summary_path", "graphify_manifest_path"):
        if not manifest.get(field):
            raise ValueError(f"available Graphify manifest requires {field}")

    freshness = manifest.get("freshness") or {}
    if freshness.get("status") != "fresh":
        raise ValueError("available Graphify manifest freshness.status must be fresh")
    if freshness.get("graph_is_trusted") is not True:
        raise ValueError("available Graphify manifest freshness.graph_is_trusted must be true")
    if freshness.get("source_delta_id") != payload.get("source_delta_id"):
        raise ValueError("available Graphify manifest freshness.source_delta_id must match source_delta_id")

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


def _require_typed_unavailable_rules(payload: Mapping[str, Any]) -> None:
    if str(payload.get("decision")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable Graphify snapshot decision must be typed_unavailable_not_live_proven")
    if str(payload.get("readiness_state")) != "not_ready":
        raise ValueError("typed unavailable Graphify snapshot readiness_state must be not_ready")
    if str(payload.get("claim_scope")) != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable Graphify snapshot claim_scope must be typed_unavailable_not_live_proven")
    if str(payload.get("rerun_condition")) != "provide_graphify_snapshot_from_live_delta":
        raise ValueError("typed unavailable Graphify snapshot must require provide_graphify_snapshot_from_live_delta")

    required_surfaces = {GRAPHIFY_SURFACE, *LATER_LANE_REF_FIELDS}
    typed_surfaces = _typed_surfaces(payload)
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


def validate_graphify_snapshot_from_live_delta(
    payload: Mapping[str, Any],
    *,
    source_delta: Mapping[str, Any] | None = None,
) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_graphify_snapshot_from_live_delta_schema(),
    )
    manifest = payload.get("snapshot_manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("snapshot_manifest must be an object")
    validate_graphify_snapshot_manifest(manifest)
    _require_source_delta(payload, source_delta)
    _require_non_sot_boundaries(payload, manifest)

    status = str(manifest.get("status") or "")
    if status == "available":
        _require_available_snapshot_rules(payload, manifest)
    elif status == "unavailable":
        _require_typed_unavailable_rules(payload)
    else:
        raise ValueError(f"unknown Graphify snapshot status: {status}")


def _source_delta_refs(source_delta: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in ("canonical_refs", "provenance_refs", "lifecycle_refs"):
        for item in source_delta.get(field) or []:
            if isinstance(item, Mapping) and str(item.get("path") or "").strip():
                refs.append(str(item["path"]).strip())
    for item in source_delta.get("source_turn_refs") or []:
        if str(item).strip():
            refs.append(str(item).strip())
    return list(dict.fromkeys(refs))


def build_typed_unavailable_graphify_snapshot_from_live_delta(
    *,
    source_delta: Mapping[str, Any],
    snapshot_proof_id: str,
    reason_code: str,
    checked_at: str | None = None,
) -> dict[str, Any]:
    if source_delta.get("readiness_state") != "ready_for_e2e3":
        raise ValueError("source_delta must be ready_for_e2e3")
    validate_knowledge_forest_delta_from_live_session(source_delta)
    generated_at = checked_at or utc_now_iso()
    adapter_payload = build_graphify_snapshot_failure_payload(
        graph_path=None,
        summary_path=None,
        manifest_path=None,
        vault_root=Path("not_available"),
        reason_code=str(reason_code),
        message=f"Graphify snapshot is unavailable: {reason_code}",
        freshness={
            "status": "unavailable",
            "graph_is_trusted": False,
            "source_delta_id": str(source_delta["delta_id"]),
        },
        generated_at=generated_at,
    )
    manifest = build_graphify_snapshot_manifest(
        adapter_payload=adapter_payload,
        manifest_id=f"graphify-snapshot:{snapshot_proof_id}",
        generated_at=generated_at,
    )
    surfaces = [GRAPHIFY_SURFACE, *LATER_LANE_REF_FIELDS.keys()]
    refs = _source_delta_refs(source_delta)
    payload = {
        "schema_version": "graphify_snapshot_from_live_delta.v1",
        "snapshot_proof_id": str(snapshot_proof_id),
        "source_delta_id": str(source_delta["delta_id"]),
        "source_artifact_bundle_id": str(source_delta["source_artifact_bundle_id"]),
        "provider_name": str(source_delta["provider_name"]),
        "provider_profile": str(source_delta["provider_profile"]),
        "session_ref": str(source_delta["session_ref"]),
        "source_delta_ref": f"source_delta:{source_delta['delta_id']}",
        "snapshot_ref": None,
        "snapshot_manifest": manifest,
        "source_delta_refs": refs,
        "safe_evidence_pointer_count": len(refs),
        "raw_transcript_included": False,
        "graphify_is_sot": False,
        "provider_may_answer_from_graphify_alone": False,
        "canonical_output_allowed": False,
        "mailbox_receipt_refs": [],
        "reasoning_lease_isolation_refs": [],
        "typed_unavailable_surfaces": surfaces,
        "rerun_condition": "provide_graphify_snapshot_from_live_delta",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in surfaces],
        "claim_scope": "typed_unavailable_not_live_proven",
        "decision": "typed_unavailable_not_live_proven",
        "readiness_state": "not_ready",
        "checked_at": generated_at,
    }
    validate_graphify_snapshot_from_live_delta(payload, source_delta=source_delta)
    return payload
