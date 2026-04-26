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
SCHEMA_PATH = CONTRACTS_ROOT / "production_report_evidence_lineage.v1.schema.json"

REQUIRED_LINEAGE_LANES = (
    "e2e1_physical_session",
    "e2e2_knowledge_forest_delta",
    "e2e3_graphify_snapshot",
    "e2e4_mailbox_consumption",
    "e2e5b_reasoning_lease_isolation",
)
REQUIRED_LINEAGE_LANE_SET = set(REQUIRED_LINEAGE_LANES)
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
NON_SAME_RUN_SOURCE_KINDS = {"contract_artifact", "typed_unavailable"}


@lru_cache(maxsize=1)
def load_production_report_evidence_lineage_schema() -> dict[str, Any]:
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


def _optional_same_run_id(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    same_run_id = str(value).strip()
    if not same_run_id:
        return None
    if not re.fullmatch(r"^[A-Za-z0-9._:-]{1,128}$", same_run_id):
        raise ValueError(f"{field_name} must be a stable same-run id")
    return same_run_id


def _ordered_lanes(lanes: set[str]) -> list[str]:
    return [lane for lane in REQUIRED_LINEAGE_LANES if lane in lanes]


def _normalize_artifact(entry: Mapping[str, Any]) -> dict[str, Any]:
    lane_id = str(entry.get("lane_id") or "").strip()
    if lane_id not in REQUIRED_LINEAGE_LANE_SET:
        raise ValueError(f"unexpected lineage lane: {lane_id or '<missing>'}")

    artifact_status = str(entry.get("artifact_status") or "").strip()
    if artifact_status not in {"present", "typed_unavailable"}:
        raise ValueError(f"{lane_id} artifact_status must be present or typed_unavailable")

    producer = str(entry.get("producer") or "").strip()
    if not producer:
        raise ValueError(f"{lane_id} producer is required")
    produced_at = _assert_timestamp(entry.get("produced_at"), field_name=f"{lane_id}.produced_at")

    safe_evidence_refs = [
        _assert_safe_ref(ref, field_name=f"{lane_id}.safe_evidence_refs")
        for ref in entry.get("safe_evidence_refs") or []
    ]
    if not safe_evidence_refs:
        raise ValueError(f"{lane_id} requires at least one safe evidence ref")
    if len(set(safe_evidence_refs)) != len(safe_evidence_refs):
        raise ValueError(f"{lane_id} safe evidence refs must be unique")
    if entry.get("contains_raw_transcript") is not False:
        raise ValueError(f"{lane_id} contains_raw_transcript must be false")

    source_kind = str(entry.get("source_kind") or "").strip()
    same_run_id = _optional_same_run_id(entry.get("same_run_id"), field_name=f"{lane_id}.same_run_id")
    same_run_witness_ref = entry.get("same_run_witness_ref")
    if same_run_witness_ref is not None:
        same_run_witness_ref = _assert_safe_ref(
            same_run_witness_ref,
            field_name=f"{lane_id}.same_run_witness_ref",
        )
    if same_run_id and not same_run_witness_ref:
        raise ValueError(f"{lane_id} same-run artifact requires same_run_witness_ref")
    if same_run_witness_ref and not same_run_id:
        raise ValueError(f"{lane_id} same_run_witness_ref requires same_run_id")
    if source_kind in NON_SAME_RUN_SOURCE_KINDS and same_run_id:
        raise ValueError(f"{lane_id} {source_kind} cannot carry same-run evidence")

    if artifact_status == "present":
        artifact_ref = _assert_safe_ref(entry.get("artifact_ref"), field_name=f"{lane_id}.artifact_ref")
        sha256 = str(entry.get("sha256") or "").strip()
        if not SHA256_RE.fullmatch(sha256):
            raise ValueError(f"{lane_id} present artifact requires sha256:<64 lowercase hex>")
        if entry.get("typed_unavailable_reason") is not None:
            raise ValueError(f"{lane_id} present artifact cannot carry typed_unavailable_reason")
        if source_kind == "typed_unavailable":
            raise ValueError(f"{lane_id} present artifact cannot use typed_unavailable source_kind")
        typed_unavailable_reason = None
    else:
        artifact_ref = entry.get("artifact_ref")
        if artifact_ref is not None:
            artifact_ref = _assert_safe_ref(artifact_ref, field_name=f"{lane_id}.artifact_ref")
        sha256 = entry.get("sha256")
        if sha256 is not None:
            raise ValueError(f"{lane_id} typed unavailable artifact cannot carry sha256")
        typed_unavailable_reason = str(entry.get("typed_unavailable_reason") or "").strip()
        if not typed_unavailable_reason:
            raise ValueError(f"{lane_id} typed unavailable artifact requires a reason")
        if source_kind != "typed_unavailable":
            raise ValueError(f"{lane_id} typed unavailable artifact requires source_kind=typed_unavailable")
        if same_run_id or same_run_witness_ref:
            raise ValueError(f"{lane_id} typed unavailable artifact cannot carry same-run evidence")

    normalized = {
        "lane_id": lane_id,
        "artifact_status": artifact_status,
        "artifact_ref": artifact_ref,
        "producer": producer,
        "produced_at": produced_at,
        "sha256": sha256,
        "typed_unavailable_reason": typed_unavailable_reason,
        "source_kind": source_kind,
        "safe_evidence_refs": safe_evidence_refs,
        "contains_raw_transcript": False,
    }
    if same_run_id is not None:
        normalized["same_run_id"] = same_run_id
        normalized["same_run_witness_ref"] = same_run_witness_ref
    return normalized


def _normalized_artifact_chain(artifact_chain: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_artifact(entry) for entry in artifact_chain]
    seen: set[str] = set()
    for entry in normalized:
        lane_id = entry["lane_id"]
        if lane_id in seen:
            raise ValueError(f"duplicate lineage lane: {lane_id}")
        seen.add(lane_id)
    return sorted(normalized, key=lambda entry: REQUIRED_LINEAGE_LANES.index(entry["lane_id"]))


def _same_run_fields(artifact_chain: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    present = [
        entry
        for entry in artifact_chain
        if str(entry.get("artifact_status")) == "present"
    ]
    if len(present) != len(REQUIRED_LINEAGE_LANES):
        return None, None
    if any(str(entry.get("source_kind")) in NON_SAME_RUN_SOURCE_KINDS for entry in present):
        return None, None
    same_run_ids = {
        str(entry.get("same_run_id") or "").strip()
        for entry in present
        if str(entry.get("same_run_id") or "").strip()
    }
    witness_refs = {
        str(entry.get("same_run_witness_ref") or "").strip()
        for entry in present
        if str(entry.get("same_run_witness_ref") or "").strip()
    }
    if len(same_run_ids) == 1 and len(witness_refs) == 1:
        return next(iter(same_run_ids)), next(iter(witness_refs))
    return None, None


def _derive_lineage_fields(
    artifact_chain: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str], list[str], str, str, list[str]]:
    present = {
        str(entry["lane_id"])
        for entry in artifact_chain
        if str(entry.get("artifact_status")) == "present"
    }
    typed_unavailable = {
        str(entry["lane_id"])
        for entry in artifact_chain
        if str(entry.get("artifact_status")) == "typed_unavailable"
    }
    missing = REQUIRED_LINEAGE_LANE_SET - present

    present_lane_ids = _ordered_lanes(present)
    typed_unavailable_lane_ids = _ordered_lanes(typed_unavailable)
    missing_lane_ids = _ordered_lanes(missing)

    same_run_id, same_run_witness_ref = _same_run_fields(artifact_chain)

    if not missing_lane_ids:
        lineage_status = "complete_minimum_lineage"
        readiness_state = (
            "ready_for_report_rebuild"
            if same_run_id and same_run_witness_ref
            else "not_ready"
        )
    elif typed_unavailable_lane_ids:
        lineage_status = "typed_unavailable"
        readiness_state = "not_ready"
    else:
        lineage_status = "incomplete_minimum_lineage"
        readiness_state = "not_ready"

    reason_codes = ["full_provenance_archive_deferred"]
    if not missing_lane_ids and not (same_run_id and same_run_witness_ref):
        reason_codes.append("same_run_lineage_required")
    for lane_id in missing_lane_ids:
        if lane_id in typed_unavailable:
            reason_codes.append(f"typed_unavailable_{lane_id}")
        else:
            reason_codes.append(f"missing_{lane_id}")

    return (
        present_lane_ids,
        typed_unavailable_lane_ids,
        missing_lane_ids,
        lineage_status,
        readiness_state,
        reason_codes,
    )


def build_production_report_evidence_lineage(
    *,
    artifact_chain: Sequence[Mapping[str, Any]],
    phase_id: str = "2026-04-26-8",
    lineage_id: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build the minimum lineage gate for a P9 production report rebuild.

    This is intentionally not a full provenance archive. It only proves that
    the report input chain has safe artifact refs, producers, timestamps, and
    either hashes or typed unavailable reasons for the E2E1-E2E5b lanes.
    """

    normalized_chain = _normalized_artifact_chain(artifact_chain)
    same_run_id, same_run_witness_ref = _same_run_fields(normalized_chain)
    (
        present_lane_ids,
        typed_unavailable_lane_ids,
        missing_lane_ids,
        lineage_status,
        readiness_state,
        reason_codes,
    ) = _derive_lineage_fields(normalized_chain)
    payload = {
        "schema_version": "production_report_evidence_lineage.v1",
        "lineage_id": lineage_id or f"p9-e2e6a-{uuid.uuid4().hex}",
        "phase_id": str(phase_id),
        "lineage_scope": "p9_live_e2e_minimum_production_report_lineage",
        "artifact_chain": normalized_chain,
        "required_lane_ids": list(REQUIRED_LINEAGE_LANES),
        "present_lane_ids": present_lane_ids,
        "typed_unavailable_lane_ids": typed_unavailable_lane_ids,
        "missing_lane_ids": missing_lane_ids,
        "lineage_status": lineage_status,
        "readiness_state": readiness_state,
        "full_provenance_archive_status": "deferred_not_required_for_e2e6a",
        "raw_transcript_included": False,
        "live_provider_readiness_claimed": False,
        "may_claim_91_percent_readiness": False,
        "reason_codes": reason_codes,
        "checked_at": checked_at or utc_now_iso(),
    }
    if same_run_id and same_run_witness_ref:
        payload["same_run_id"] = same_run_id
        payload["same_run_witness_ref"] = same_run_witness_ref
    validate_production_report_evidence_lineage(payload)
    return payload


def validate_production_report_evidence_lineage(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_production_report_evidence_lineage_schema(),
    )
    if tuple(payload.get("required_lane_ids") or []) != REQUIRED_LINEAGE_LANES:
        raise ValueError("required_lane_ids must be the E2E1-E2E5b lineage lane set")
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    if payload.get("live_provider_readiness_claimed") is not False:
        raise ValueError("minimal lineage cannot claim live provider readiness")
    if payload.get("may_claim_91_percent_readiness") is not False:
        raise ValueError("minimal lineage cannot claim 91 percent readiness")
    if str(payload.get("full_provenance_archive_status")) != "deferred_not_required_for_e2e6a":
        raise ValueError("E2E6a must keep the full provenance archive deferred")
    _assert_timestamp(payload.get("checked_at"), field_name="checked_at")

    normalized_chain = _normalized_artifact_chain(payload.get("artifact_chain") or [])
    same_run_id, same_run_witness_ref = _same_run_fields(normalized_chain)
    (
        present_lane_ids,
        typed_unavailable_lane_ids,
        missing_lane_ids,
        lineage_status,
        readiness_state,
        reason_codes,
    ) = _derive_lineage_fields(normalized_chain)

    expected = {
        "present_lane_ids": present_lane_ids,
        "typed_unavailable_lane_ids": typed_unavailable_lane_ids,
        "missing_lane_ids": missing_lane_ids,
        "lineage_status": lineage_status,
        "readiness_state": readiness_state,
        "reason_codes": reason_codes,
    }
    for field_name, expected_value in expected.items():
        if payload.get(field_name) != expected_value:
            raise ValueError(f"{field_name} does not match artifact_chain")
    if same_run_id and same_run_witness_ref:
        if payload.get("same_run_id") != same_run_id:
            raise ValueError("same_run_id does not match artifact_chain")
        if payload.get("same_run_witness_ref") != same_run_witness_ref:
            raise ValueError("same_run_witness_ref does not match artifact_chain")
    else:
        if payload.get("same_run_id") is not None or payload.get("same_run_witness_ref") is not None:
            raise ValueError("same-run fields do not match artifact_chain")


def prepare_lineage_for_production_report_rebuild(payload: Mapping[str, Any]) -> dict[str, Any]:
    validate_production_report_evidence_lineage(payload)
    if str(payload.get("lineage_status")) != "complete_minimum_lineage":
        raise ValueError("production report rebuild requires complete minimum lineage")
    if str(payload.get("readiness_state")) != "ready_for_report_rebuild":
        raise ValueError("production report rebuild requires same-run lineage")
    if not payload.get("same_run_id") or not payload.get("same_run_witness_ref"):
        raise ValueError("production report rebuild requires same-run lineage")
    return dict(payload)
