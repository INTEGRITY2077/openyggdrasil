from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import validate_decision_candidate, validate_seedkeeper_segment
from harness_common import utc_now_iso


def _turn_range(candidate: Mapping[str, Any]) -> list[int]:
    start = int(candidate.get("turn_start") or 0)
    end = int(candidate.get("turn_end") or start)
    return [start, end]


def _source_ref(candidate: Mapping[str, Any]) -> str | None:
    value = str(candidate.get("source_ref") or "").strip()
    return value or None


def preserve_decision_segment(*, decision_candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve deterministic source metadata without category or semantic judgment."""

    validate_decision_candidate(decision_candidate)
    source_ref = _source_ref(decision_candidate)
    origin_locator = dict(decision_candidate.get("origin_locator") or {})
    source_ref_present = source_ref is not None
    origin_present = bool(origin_locator)
    preservation_status = "preserved" if source_ref_present and origin_present else "review_needed"
    integrity_status = "clean" if preservation_status == "preserved" else "review_needed"
    integrity_reason = (
        "seedkeeper_source_ref_preserved"
        if preservation_status == "preserved"
        else "seedkeeper_source_ref_or_origin_missing"
    )
    reason_codes = ["deterministic_segment_preserved"]
    if source_ref_present:
        reason_codes.append("source_ref_present")
    else:
        reason_codes.append("source_ref_missing")
    if origin_present:
        reason_codes.append("origin_locator_present")
    else:
        reason_codes.append("origin_locator_missing")

    segment = {
        "schema_version": "seedkeeper_segment.v1",
        "segment_id": uuid.uuid4().hex,
        "candidate_id": str(decision_candidate["candidate_id"]),
        "dedup_key": str(decision_candidate["dedup_key"]),
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "turn_start": int(decision_candidate["turn_start"]),
        "turn_end": int(decision_candidate["turn_end"]),
        "source_ref": source_ref,
        "source_ref_status": "present" if source_ref_present else "missing",
        "origin_locator": origin_locator,
        "provenance_ring": {
            "provider_id": str(decision_candidate["provider_id"]),
            "provider_profile": str(decision_candidate["provider_profile"]),
            "provider_session_id": str(decision_candidate["provider_session_id"]),
            "session_uid": str(decision_candidate["session_uid"]),
            "turn_range": _turn_range(decision_candidate),
            "source_ref": source_ref,
            "origin_locator": origin_locator,
        },
        "preservation_status": preservation_status,
        "integrity_status": integrity_status,
        "integrity_reason": integrity_reason,
        "segment_authority": "deterministic_source_ref_preservation_only",
        "semantic_worth_authority": "not_seedkeeper",
        "category_authority": "not_seedkeeper",
        "planting_ready": preservation_status == "preserved",
        "reason_codes": reason_codes,
        "preserved_at": utc_now_iso(),
    }
    validate_seedkeeper_segment(segment)
    return segment
