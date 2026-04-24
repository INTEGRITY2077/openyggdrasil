from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_decision_candidate,
    validate_engraved_seed,
)
from harness_common import utc_now_iso


def _turn_range(candidate: Mapping[str, Any]) -> list[int]:
    start = int(candidate.get("turn_start") or 0)
    end = int(candidate.get("turn_end") or start)
    return [start, end]


def _integrity_fields(candidate: Mapping[str, Any]) -> tuple[str, str, bool]:
    source_ref = str(candidate.get("source_ref") or "").strip()
    origin_locator = dict(candidate.get("origin_locator") or {})
    turn_range = _turn_range(candidate)
    if source_ref and origin_locator and all(turn_range):
        return "clean", "foreground_trace_complete", True
    return "review_needed", "foreground_trace_incomplete", False


def engrave_decision_seed(
    *,
    admission_verdict: Mapping[str, Any],
    decision_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    validate_admission_verdict(admission_verdict)
    validate_decision_candidate(decision_candidate)
    integrity_status, integrity_reason, planting_ready = _integrity_fields(decision_candidate)
    provenance_ring = {
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "turn_range": _turn_range(decision_candidate),
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
    }
    seed = {
        "schema_version": "engraved_seed.v1",
        "seed_id": uuid.uuid4().hex,
        "verdict_id": str(admission_verdict["verdict_id"]),
        "candidate_id": str(decision_candidate["candidate_id"]),
        "continent_key": str(admission_verdict["continent_key"]),
        "continent_id": str(admission_verdict["continent_id"]),
        "continent_title": str(admission_verdict["continent_title"]),
        "topic_key": str(admission_verdict["topic_key"]),
        "topic_id": str(admission_verdict["topic_id"]),
        "topic_title": str(admission_verdict["topic_title"]),
        "page_id": str(admission_verdict["page_id"]),
        "canonical_relative_path": str(admission_verdict["canonical_relative_path"]),
        "episode_id": str(admission_verdict["episode_id"]),
        "seed_identity_key": (
            f"{str(admission_verdict['continent_key'])}:{str(admission_verdict['topic_key'])}:"
            f"turn-{_turn_range(decision_candidate)[0]}-{_turn_range(decision_candidate)[1]}"
        ),
        "planting_target_kind": "topic_page",
        "planting_target_hint": str(admission_verdict["canonical_relative_path"]),
        "planting_ready": planting_ready,
        "integrity_status": integrity_status,
        "integrity_reason": integrity_reason,
        "provenance_ring": provenance_ring,
        "surface_summary": str(decision_candidate.get("surface_summary") or "").strip(),
        "trigger_reason": str(decision_candidate.get("trigger_reason") or "").strip(),
        "decision_text": str(decision_candidate.get("decision_text") or "").strip(),
        "rationale": str(decision_candidate.get("rationale") or "").strip(),
        "alternatives_rejected": list(decision_candidate.get("alternatives_rejected") or []),
        "stability_state": str(decision_candidate.get("stability_state") or "provisional").strip(),
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
        "engraved_at": utc_now_iso(),
    }
    validate_engraved_seed(seed)
    return seed
