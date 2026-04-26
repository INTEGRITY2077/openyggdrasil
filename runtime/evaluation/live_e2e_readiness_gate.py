from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "live_e2e_readiness_gate.v1.schema.json"

REQUIRED_PRECONDITIONS = (
    "run_lock_held",
    "hermes_binary_available",
    "provider_profile_available",
    "live_artifact_root_available",
    "safe_capture_policy_available",
    "raw_transcript_filter_enabled",
    "stale_decoy_probe_plan_available",
    "wsl2_bubblewrap_available",
    "schema_contracts_available",
)
REQUIRED_PRECONDITION_SET = set(REQUIRED_PRECONDITIONS)

REQUIRED_EVIDENCE_LANES = (
    "e2e1_physical_session",
    "e2e2_knowledge_forest_delta",
    "e2e3_graphify_snapshot",
    "e2e4_mailbox_consumption",
    "same_run_hermes_live_witness",
    "ptc_runtime_trace",
    "e2e5b_reasoning_lease_isolation",
    "e2e6a_production_lineage",
    "e2e6_production_report_rebuild",
)
REQUIRED_EVIDENCE_LANE_SET = set(REQUIRED_EVIDENCE_LANES)

NON_LIVE_EVIDENCE_SOURCE_KINDS = {
    "contract_artifact",
    "fixture_only",
    "historical_witness",
}
NOT_PRESENT_SOURCE_KINDS = {"typed_unavailable", "not_supplied"}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_TRANSCRIPT_MARKERS = (
    "raw-transcript",
    "raw_transcript",
    "raw provider transcript",
    "raw_provider_transcript",
    "raw-provider-session",
    "raw_provider_session",
    "provider-session-copy",
    "provider_session_copy",
    "transcript.txt",
)


@lru_cache(maxsize=1)
def load_live_e2e_readiness_gate_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _assert_timestamp(value: Any, *, field_name: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{field_name} is required")
    timestamp = str(value).strip()
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO 8601") from exc
    return timestamp


def _assert_no_raw_transcript_marker(value: str, *, field_name: str) -> None:
    normalized = value.lower().replace("\\", "/")
    normalized = normalized.replace("raw_transcript_filter", "redaction-policy")
    normalized = normalized.replace("raw-transcript-filter", "redaction-policy")
    for marker in RAW_TRANSCRIPT_MARKERS:
        if marker in normalized:
            raise ValueError(f"{field_name} contains raw transcript marker: {marker}")


def _assert_safe_ref(value: Any, *, field_name: str) -> str:
    if not _nonempty(value):
        raise ValueError(f"{field_name} is required")
    ref = str(value).strip()
    normalized = ref.lower().replace("\\", "/")
    _assert_no_raw_transcript_marker(ref, field_name=field_name)
    if re.match(r"^[a-z]:/", normalized) or normalized.startswith(("/", "file://")):
        raise ValueError(f"{field_name} must be an evidence ref, not a local path")
    if "://" not in ref:
        raise ValueError(f"{field_name} must use an explicit evidence ref scheme")
    return ref


def _safe_refs(values: Any, *, field_name: str) -> list[str]:
    refs = [
        _assert_safe_ref(ref, field_name=field_name)
        for ref in values or []
    ]
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} must be unique")
    return refs


def _ordered_preconditions(precondition_ids: set[str]) -> list[str]:
    return [item for item in REQUIRED_PRECONDITIONS if item in precondition_ids]


def _ordered_lanes(lane_ids: set[str]) -> list[str]:
    return [lane for lane in REQUIRED_EVIDENCE_LANES if lane in lane_ids]


def _reason(value: Any) -> str | None:
    if value is None:
        return None
    reason = str(value).strip()
    return reason or None


def _missing_precondition(precondition_id: str) -> dict[str, Any]:
    return {
        "precondition_id": precondition_id,
        "status": "missing",
        "source_kind": "not_supplied",
        "artifact_ref": None,
        "reason_code": f"missing_{precondition_id}",
        "safe_evidence_refs": [],
        "contains_raw_transcript": False,
    }


def _missing_evidence_lane(lane_id: str) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "status": "missing",
        "artifact_ref": None,
        "sha256": None,
        "typed_unavailable_reason": f"missing_{lane_id}",
        "source_kind": "not_supplied",
        "same_run_id": None,
        "safe_evidence_refs": [],
        "contains_raw_transcript": False,
        "fixture_only": False,
        "historical_only": False,
    }


def _normalize_precondition(entry: Mapping[str, Any]) -> dict[str, Any]:
    precondition_id = str(entry.get("precondition_id") or "").strip()
    if precondition_id not in REQUIRED_PRECONDITION_SET:
        raise ValueError(f"unexpected live E2E precondition: {precondition_id or '<missing>'}")

    status = str(entry.get("status") or "").strip()
    if status not in {"present", "typed_unavailable", "missing", "invalid"}:
        raise ValueError(f"{precondition_id} status must be present, typed_unavailable, missing, or invalid")

    source_kind = str(entry.get("source_kind") or "").strip()
    if not source_kind:
        source_kind = "runtime_check" if status == "present" else "not_supplied"

    artifact_ref = entry.get("artifact_ref")
    if artifact_ref is not None:
        artifact_ref = _assert_safe_ref(artifact_ref, field_name=f"{precondition_id}.artifact_ref")

    safe_evidence_refs = _safe_refs(
        entry.get("safe_evidence_refs") or [],
        field_name=f"{precondition_id}.safe_evidence_refs",
    )
    reason_code = _reason(entry.get("reason_code"))

    if entry.get("contains_raw_transcript") is not False:
        raise ValueError(f"{precondition_id} contains_raw_transcript must be false")

    if status == "present":
        if source_kind in {"typed_unavailable", "not_supplied"}:
            raise ValueError(f"{precondition_id} present precondition cannot use {source_kind} source_kind")
        if not safe_evidence_refs:
            raise ValueError(f"{precondition_id} present precondition requires safe_evidence_refs")
        if reason_code is not None:
            raise ValueError(f"{precondition_id} present precondition cannot carry reason_code")
    else:
        if source_kind not in NOT_PRESENT_SOURCE_KINDS:
            raise ValueError(f"{precondition_id} non-present precondition requires typed_unavailable or not_supplied source_kind")
        if artifact_ref is not None:
            raise ValueError(f"{precondition_id} non-present precondition cannot carry artifact_ref")
        if not reason_code:
            raise ValueError(f"{precondition_id} non-present precondition requires reason_code")

    return {
        "precondition_id": precondition_id,
        "status": status,
        "source_kind": source_kind,
        "artifact_ref": artifact_ref,
        "reason_code": reason_code,
        "safe_evidence_refs": safe_evidence_refs,
        "contains_raw_transcript": False,
    }


def _normalize_evidence_lane(entry: Mapping[str, Any]) -> dict[str, Any]:
    lane_id = str(entry.get("lane_id") or "").strip()
    if lane_id not in REQUIRED_EVIDENCE_LANE_SET:
        raise ValueError(f"unexpected live E2E evidence lane: {lane_id or '<missing>'}")

    status = str(entry.get("status") or "").strip()
    if status not in {"present", "typed_unavailable", "missing", "invalid"}:
        raise ValueError(f"{lane_id} status must be present, typed_unavailable, missing, or invalid")

    source_kind = str(entry.get("source_kind") or "").strip()
    if not source_kind:
        source_kind = "physical_live_artifact" if status == "present" else "not_supplied"

    artifact_ref = entry.get("artifact_ref")
    if artifact_ref is not None:
        artifact_ref = _assert_safe_ref(artifact_ref, field_name=f"{lane_id}.artifact_ref")

    safe_evidence_refs = _safe_refs(
        entry.get("safe_evidence_refs") or [],
        field_name=f"{lane_id}.safe_evidence_refs",
    )
    sha256 = entry.get("sha256")
    if sha256 is not None:
        sha256 = str(sha256).strip()
    typed_unavailable_reason = _reason(entry.get("typed_unavailable_reason"))
    same_run_id = _reason(entry.get("same_run_id"))
    fixture_only = entry.get("fixture_only") is True
    historical_only = entry.get("historical_only") is True

    if entry.get("contains_raw_transcript") is not False:
        raise ValueError(f"{lane_id} contains_raw_transcript must be false")

    if status == "present":
        if source_kind in NOT_PRESENT_SOURCE_KINDS:
            raise ValueError(f"{lane_id} present evidence cannot use {source_kind} source_kind")
        if artifact_ref is None:
            raise ValueError(f"{lane_id} present evidence requires artifact_ref")
        if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
            raise ValueError(f"{lane_id} present evidence requires sha256:<64 lowercase hex>")
        if typed_unavailable_reason is not None:
            raise ValueError(f"{lane_id} present evidence cannot carry typed_unavailable_reason")
        if not safe_evidence_refs:
            raise ValueError(f"{lane_id} present evidence requires safe_evidence_refs")
    else:
        if source_kind not in NOT_PRESENT_SOURCE_KINDS:
            raise ValueError(f"{lane_id} non-present evidence requires typed_unavailable or not_supplied source_kind")
        if artifact_ref is not None:
            raise ValueError(f"{lane_id} non-present evidence cannot carry artifact_ref")
        if sha256 is not None:
            raise ValueError(f"{lane_id} non-present evidence cannot carry sha256")
        if not typed_unavailable_reason:
            raise ValueError(f"{lane_id} non-present evidence requires typed_unavailable_reason")
        if same_run_id is not None:
            raise ValueError(f"{lane_id} non-present evidence cannot carry same_run_id")
        if fixture_only or historical_only:
            raise ValueError(f"{lane_id} non-present evidence cannot be fixture_only or historical_only")

    return {
        "lane_id": lane_id,
        "status": status,
        "artifact_ref": artifact_ref,
        "sha256": sha256,
        "typed_unavailable_reason": typed_unavailable_reason,
        "source_kind": source_kind,
        "same_run_id": same_run_id,
        "safe_evidence_refs": safe_evidence_refs,
        "contains_raw_transcript": False,
        "fixture_only": fixture_only,
        "historical_only": historical_only,
    }


def _normalized_preconditions(preconditions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_precondition(entry) for entry in preconditions]
    by_id: dict[str, dict[str, Any]] = {}
    for entry in normalized:
        precondition_id = entry["precondition_id"]
        if precondition_id in by_id:
            raise ValueError(f"duplicate live E2E precondition: {precondition_id}")
        by_id[precondition_id] = entry
    for precondition_id in REQUIRED_PRECONDITIONS:
        by_id.setdefault(precondition_id, _missing_precondition(precondition_id))
    return [by_id[precondition_id] for precondition_id in REQUIRED_PRECONDITIONS]


def _normalized_evidence_lanes(evidence_lanes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_evidence_lane(entry) for entry in evidence_lanes]
    by_id: dict[str, dict[str, Any]] = {}
    for entry in normalized:
        lane_id = entry["lane_id"]
        if lane_id in by_id:
            raise ValueError(f"duplicate live E2E evidence lane: {lane_id}")
        by_id[lane_id] = entry
    for lane_id in REQUIRED_EVIDENCE_LANES:
        by_id.setdefault(lane_id, _missing_evidence_lane(lane_id))
    return [by_id[lane_id] for lane_id in REQUIRED_EVIDENCE_LANES]


def _derive_precondition_fields(
    preconditions: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str], list[str], list[str], bool]:
    satisfied = {str(entry["precondition_id"]) for entry in preconditions if entry["status"] == "present"}
    missing = {str(entry["precondition_id"]) for entry in preconditions if entry["status"] == "missing"}
    typed_unavailable = {
        str(entry["precondition_id"])
        for entry in preconditions
        if entry["status"] == "typed_unavailable"
    }
    invalid = {str(entry["precondition_id"]) for entry in preconditions if entry["status"] == "invalid"}
    preconditions_ready = (
        len(satisfied) == len(REQUIRED_PRECONDITIONS)
        and not missing
        and not typed_unavailable
        and not invalid
    )
    return (
        _ordered_preconditions(satisfied),
        _ordered_preconditions(missing),
        _ordered_preconditions(typed_unavailable),
        _ordered_preconditions(invalid),
        preconditions_ready,
    )


def _derive_evidence_fields(
    evidence_lanes: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str], list[str], list[str], list[str], str | None, bool, bool, bool]:
    present = {str(entry["lane_id"]) for entry in evidence_lanes if entry["status"] == "present"}
    missing = {str(entry["lane_id"]) for entry in evidence_lanes if entry["status"] == "missing"}
    typed_unavailable = {
        str(entry["lane_id"])
        for entry in evidence_lanes
        if entry["status"] == "typed_unavailable"
    }
    invalid = {str(entry["lane_id"]) for entry in evidence_lanes if entry["status"] == "invalid"}
    non_live = {
        str(entry["lane_id"])
        for entry in evidence_lanes
        if entry["status"] == "present"
        and (
            entry.get("fixture_only") is True
            or entry.get("historical_only") is True
            or str(entry.get("source_kind") or "") in NON_LIVE_EVIDENCE_SOURCE_KINDS
        )
    }
    present_entries = [entry for entry in evidence_lanes if entry["status"] == "present"]
    same_run_ids = {
        str(entry.get("same_run_id") or "").strip()
        for entry in present_entries
        if str(entry.get("same_run_id") or "").strip()
    }
    all_present_have_same_run = bool(present_entries) and len(same_run_ids) == 1 and all(
        str(entry.get("same_run_id") or "").strip() in same_run_ids
        for entry in present_entries
    )
    same_run_id = next(iter(same_run_ids)) if len(same_run_ids) == 1 else None
    same_run_missing = bool(present_entries) and not all(
        str(entry.get("same_run_id") or "").strip()
        for entry in present_entries
    )
    same_run_mismatch = len(same_run_ids) > 1
    evidence_ready = (
        len(present) == len(REQUIRED_EVIDENCE_LANES)
        and not missing
        and not typed_unavailable
        and not invalid
        and not non_live
        and all_present_have_same_run
    )
    return (
        _ordered_lanes(present),
        _ordered_lanes(missing),
        _ordered_lanes(typed_unavailable),
        _ordered_lanes(invalid),
        _ordered_lanes(non_live),
        same_run_id,
        evidence_ready,
        same_run_missing,
        same_run_mismatch,
    )


def _derive_reason_codes(
    *,
    missing_preconditions: Sequence[str],
    typed_unavailable_preconditions: Sequence[str],
    invalid_preconditions: Sequence[str],
    missing_evidence: Sequence[str],
    typed_unavailable_evidence: Sequence[str],
    invalid_evidence: Sequence[str],
    non_live_evidence: Sequence[str],
    same_run_missing: bool,
    same_run_mismatch: bool,
) -> list[str]:
    reasons: list[str] = ["live_ready_claim_deferred_to_report_gate"]
    reasons.extend(f"precondition_missing_{item}" for item in missing_preconditions)
    reasons.extend(f"precondition_typed_unavailable_{item}" for item in typed_unavailable_preconditions)
    reasons.extend(f"precondition_invalid_{item}" for item in invalid_preconditions)
    reasons.extend(f"evidence_missing_{lane}" for lane in missing_evidence)
    reasons.extend(f"evidence_typed_unavailable_{lane}" for lane in typed_unavailable_evidence)
    reasons.extend(f"evidence_invalid_{lane}" for lane in invalid_evidence)
    reasons.extend(f"non_live_evidence_{lane}" for lane in non_live_evidence)
    if same_run_missing:
        reasons.append("same_run_id_missing")
    if same_run_mismatch:
        reasons.append("same_run_id_mismatch")
    return list(dict.fromkeys(reasons))


def _derive_evidence_required(
    *,
    missing_preconditions: Sequence[str],
    typed_unavailable_preconditions: Sequence[str],
    invalid_preconditions: Sequence[str],
    missing_evidence: Sequence[str],
    typed_unavailable_evidence: Sequence[str],
    invalid_evidence: Sequence[str],
    non_live_evidence: Sequence[str],
    evidence_ready: bool,
) -> list[str]:
    required: list[str] = []
    required.extend(f"provide_precondition_{item}" for item in missing_preconditions)
    required.extend(f"resolve_precondition_{item}" for item in typed_unavailable_preconditions)
    required.extend(f"repair_precondition_{item}" for item in invalid_preconditions)
    required.extend(f"provide_same_run_evidence_{lane}" for lane in missing_evidence)
    required.extend(f"resolve_same_run_evidence_{lane}" for lane in typed_unavailable_evidence)
    required.extend(f"repair_same_run_evidence_{lane}" for lane in invalid_evidence)
    required.extend(f"replace_non_live_evidence_{lane}" for lane in non_live_evidence)
    if not evidence_ready:
        required.append("execute_physical_same_run_hermes_live_e2e")
    return list(dict.fromkeys(required))


def _derive_gate_fields(
    *,
    preconditions: Sequence[Mapping[str, Any]],
    evidence_lanes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    (
        satisfied_precondition_ids,
        missing_precondition_ids,
        typed_unavailable_precondition_ids,
        invalid_precondition_ids,
        preconditions_ready,
    ) = _derive_precondition_fields(preconditions)
    (
        present_evidence_lane_ids,
        missing_evidence_lane_ids,
        typed_unavailable_evidence_lane_ids,
        invalid_evidence_lane_ids,
        non_live_evidence_lane_ids,
        same_run_id,
        evidence_ready,
        same_run_missing,
        same_run_mismatch,
    ) = _derive_evidence_fields(evidence_lanes)

    if preconditions_ready and evidence_ready:
        readiness_state = "ready_for_live_e2e_report_review"
        rerun_condition = "review_production_report_without_overclaim"
    elif preconditions_ready:
        readiness_state = "ready_for_physical_live_probe_execution"
        rerun_condition = "execute_physical_same_run_hermes_live_e2e"
    else:
        readiness_state = "not_ready"
        rerun_condition = "satisfy_live_e2e_preconditions"

    evidence_required = _derive_evidence_required(
        missing_preconditions=missing_precondition_ids,
        typed_unavailable_preconditions=typed_unavailable_precondition_ids,
        invalid_preconditions=invalid_precondition_ids,
        missing_evidence=missing_evidence_lane_ids,
        typed_unavailable_evidence=typed_unavailable_evidence_lane_ids,
        invalid_evidence=invalid_evidence_lane_ids,
        non_live_evidence=non_live_evidence_lane_ids,
        evidence_ready=evidence_ready,
    )
    reason_codes = _derive_reason_codes(
        missing_preconditions=missing_precondition_ids,
        typed_unavailable_preconditions=typed_unavailable_precondition_ids,
        invalid_preconditions=invalid_precondition_ids,
        missing_evidence=missing_evidence_lane_ids,
        typed_unavailable_evidence=typed_unavailable_evidence_lane_ids,
        invalid_evidence=invalid_evidence_lane_ids,
        non_live_evidence=non_live_evidence_lane_ids,
        same_run_missing=same_run_missing,
        same_run_mismatch=same_run_mismatch,
    )

    return {
        "required_precondition_ids": list(REQUIRED_PRECONDITIONS),
        "satisfied_precondition_ids": satisfied_precondition_ids,
        "missing_precondition_ids": missing_precondition_ids,
        "typed_unavailable_precondition_ids": typed_unavailable_precondition_ids,
        "invalid_precondition_ids": invalid_precondition_ids,
        "required_evidence_lane_ids": list(REQUIRED_EVIDENCE_LANES),
        "present_evidence_lane_ids": present_evidence_lane_ids,
        "missing_evidence_lane_ids": missing_evidence_lane_ids,
        "typed_unavailable_evidence_lane_ids": typed_unavailable_evidence_lane_ids,
        "invalid_evidence_lane_ids": invalid_evidence_lane_ids,
        "non_live_evidence_lane_ids": non_live_evidence_lane_ids,
        "same_run_id": same_run_id if evidence_ready else None,
        "live_execution_readiness": "ready_for_physical_live_probe" if preconditions_ready else "not_ready",
        "evidence_chain_readiness": "same_run_evidence_complete" if evidence_ready else "not_ready",
        "readiness_state": readiness_state,
        "may_start_physical_live_probe": preconditions_ready,
        "may_claim_live_e2e_chain_complete": evidence_ready,
        "may_claim_live_ready": False,
        "may_claim_91_percent_readiness": False,
        "raw_transcript_included": False,
        "rerun_condition": rerun_condition,
        "evidence_required": evidence_required,
        "reason_codes": reason_codes,
    }


def build_live_e2e_readiness_gate(
    *,
    preconditions: Sequence[Mapping[str, Any]],
    evidence_lanes: Sequence[Mapping[str, Any]] = (),
    phase_id: str = "p9-live-e2e",
    readiness_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build the gate used before and after a physical same-run Hermes live E2E.

    This gate can authorize starting the physical probe when preconditions are
    present. It cannot authorize a live-readiness claim; final readiness still
    belongs to the production report gate.
    """

    normalized_preconditions = _normalized_preconditions(preconditions)
    normalized_evidence_lanes = _normalized_evidence_lanes(evidence_lanes)
    payload = {
        "schema_version": "live_e2e_readiness_gate.v1",
        "readiness_id": readiness_id or f"p9-live-e2e-readiness-{uuid.uuid4().hex}",
        "phase_id": str(phase_id),
        "gate_scope": "p9_physical_same_run_hermes_live_e2e_readiness",
        "preconditions": normalized_preconditions,
        "evidence_lanes": normalized_evidence_lanes,
        **_derive_gate_fields(
            preconditions=normalized_preconditions,
            evidence_lanes=normalized_evidence_lanes,
        ),
        "checked_at": checked_at or utc_now_iso(),
    }
    validate_live_e2e_readiness_gate(payload)
    return payload


def validate_live_e2e_readiness_gate(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_live_e2e_readiness_gate_schema(),
    )
    if tuple(payload.get("required_precondition_ids") or []) != REQUIRED_PRECONDITIONS:
        raise ValueError("required_precondition_ids must match the live E2E precondition set")
    if tuple(payload.get("required_evidence_lane_ids") or []) != REQUIRED_EVIDENCE_LANES:
        raise ValueError("required_evidence_lane_ids must match the live E2E lane set")
    if payload.get("may_claim_live_ready") is not False:
        raise ValueError("live E2E readiness gate cannot claim live readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("live E2E readiness gate cannot claim 91 percent readiness")
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    normalized_preconditions = _normalized_preconditions(payload.get("preconditions") or [])
    normalized_evidence_lanes = _normalized_evidence_lanes(payload.get("evidence_lanes") or [])
    expected_fields = _derive_gate_fields(
        preconditions=normalized_preconditions,
        evidence_lanes=normalized_evidence_lanes,
    )
    for field_name, expected_value in expected_fields.items():
        if payload.get(field_name) != expected_value:
            raise ValueError(f"{field_name} does not match readiness inputs")

    if payload.get("preconditions") != normalized_preconditions:
        raise ValueError("preconditions must be normalized and complete")
    if payload.get("evidence_lanes") != normalized_evidence_lanes:
        raise ValueError("evidence_lanes must be normalized and complete")
