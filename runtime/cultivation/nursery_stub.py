from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_decision_candidate,
    validate_engraved_seed,
    validate_seedkeeper_segment,
)
from cultivation.seedkeeper import preserve_decision_segment
from harness_common import utc_now_iso


def _turn_range(candidate: Mapping[str, Any]) -> list[int]:
    start = int(candidate.get("turn_start") or 0)
    end = int(candidate.get("turn_end") or start)
    return [start, end]


def _resolve_seedkeeper_segment(
    *,
    decision_candidate: Mapping[str, Any],
    seedkeeper_segment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if seedkeeper_segment is None:
        seedkeeper_segment = preserve_decision_segment(decision_candidate=decision_candidate)
    validate_seedkeeper_segment(seedkeeper_segment)
    if str(seedkeeper_segment["candidate_id"]) != str(decision_candidate["candidate_id"]):
        raise ValueError("seedkeeper_segment candidate_id does not match decision_candidate")
    if str(seedkeeper_segment["dedup_key"]) != str(decision_candidate["dedup_key"]):
        raise ValueError("seedkeeper_segment dedup_key does not match decision_candidate")
    return dict(seedkeeper_segment)


def engrave_decision_seed(
    *,
    admission_verdict: Mapping[str, Any],
    decision_candidate: Mapping[str, Any],
    seedkeeper_segment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_admission_verdict(admission_verdict)
    validate_decision_candidate(decision_candidate)
    preserved_segment = _resolve_seedkeeper_segment(
        decision_candidate=decision_candidate,
        seedkeeper_segment=seedkeeper_segment,
    )
    provenance_ring = dict(preserved_segment["provenance_ring"])
    turn_range = list(provenance_ring["turn_range"])
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
            f"turn-{turn_range[0]}-{turn_range[1]}"
        ),
        "planting_target_kind": "topic_page",
        "planting_target_hint": str(admission_verdict["canonical_relative_path"]),
        "planting_ready": bool(preserved_segment["planting_ready"]),
        "integrity_status": str(preserved_segment["integrity_status"]),
        "integrity_reason": str(preserved_segment["integrity_reason"]),
        "provenance_ring": provenance_ring,
        "surface_summary": str(decision_candidate.get("surface_summary") or "").strip(),
        "trigger_reason": str(decision_candidate.get("trigger_reason") or "").strip(),
        "decision_text": str(decision_candidate.get("decision_text") or "").strip(),
        "rationale": str(decision_candidate.get("rationale") or "").strip(),
        "alternatives_rejected": list(decision_candidate.get("alternatives_rejected") or []),
        "stability_state": str(decision_candidate.get("stability_state") or "provisional").strip(),
        "source_ref": preserved_segment.get("source_ref"),
        "origin_locator": dict(preserved_segment.get("origin_locator") or {}),
        "engraved_at": utc_now_iso(),
    }
    validate_engraved_seed(seed)
    return seed
