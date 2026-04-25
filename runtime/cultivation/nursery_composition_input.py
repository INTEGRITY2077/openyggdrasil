from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_amundsen_nursery_handoff,
    validate_decision_candidate,
    validate_evaluator_verdict,
    validate_nursery_composition_input,
    validate_seedkeeper_segment,
)
from harness_common import utc_now_iso


def _same_candidate_id(*artifacts: Mapping[str, Any]) -> bool:
    ids = {str(artifact.get("candidate_id")) for artifact in artifacts if artifact.get("candidate_id")}
    return len(ids) == 1


def _blocked_reason(
    *,
    evaluator_verdict: Mapping[str, Any],
    amundsen_nursery_handoff: Mapping[str, Any],
    seedkeeper_segment: Mapping[str, Any],
) -> str | None:
    if str(evaluator_verdict.get("evaluator_status")) != "accept_for_amundsen":
        return "evaluator_not_accepted"
    if not bool(evaluator_verdict.get("amundsen_handoff_allowed")):
        return "evaluator_amundsen_handoff_not_allowed"
    if str(amundsen_nursery_handoff.get("handoff_status")) != "ready_for_nursery":
        return "amundsen_handoff_not_ready"
    if str(seedkeeper_segment.get("preservation_status")) != "preserved":
        return "seedkeeper_segment_not_preserved"
    return None


def build_nursery_composition_input(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
    amundsen_nursery_handoff: Mapping[str, Any],
    seedkeeper_segment: Mapping[str, Any],
) -> dict[str, Any]:
    validate_decision_candidate(decision_candidate)
    validate_evaluator_verdict(evaluator_verdict)
    validate_amundsen_nursery_handoff(amundsen_nursery_handoff)
    validate_seedkeeper_segment(seedkeeper_segment)
    if not _same_candidate_id(
        decision_candidate,
        evaluator_verdict,
        amundsen_nursery_handoff,
        seedkeeper_segment,
    ):
        raise ValueError("nursery_composition_input candidate_id mismatch")

    blocked_reason = _blocked_reason(
        evaluator_verdict=evaluator_verdict,
        amundsen_nursery_handoff=amundsen_nursery_handoff,
        seedkeeper_segment=seedkeeper_segment,
    )
    status = "ready_for_seed_composition" if blocked_reason is None else "blocked"
    reason_codes = [
        "nursery_composed_input",
        "semantic_worth_from_evaluator",
        "route_from_amundsen",
        "source_ref_from_seedkeeper",
    ]
    if blocked_reason is not None:
        reason_codes.append(blocked_reason)

    payload = {
        "schema_version": "nursery_composition_input.v1",
        "input_id": uuid.uuid4().hex,
        "candidate_id": str(decision_candidate["candidate_id"]),
        "evaluator_verdict_id": str(evaluator_verdict["evaluator_verdict_id"]),
        "amundsen_handoff_id": str(amundsen_nursery_handoff["handoff_id"]),
        "seedkeeper_segment_id": str(seedkeeper_segment["segment_id"]),
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "composition_status": status,
        "nursery_authority": "seed_composition_only_after_typed_handoffs",
        "semantic_worth_source": "evaluator_verdict",
        "route_source": "amundsen_nursery_handoff",
        "source_ref_source": "seedkeeper_segment",
        "decision_candidate": dict(decision_candidate),
        "evaluator_verdict": dict(evaluator_verdict),
        "amundsen_nursery_handoff": dict(amundsen_nursery_handoff),
        "seedkeeper_segment": dict(seedkeeper_segment),
        "blocked_reason": blocked_reason,
        "reason_codes": reason_codes,
        "created_at": utc_now_iso(),
    }
    validate_nursery_composition_input(payload)
    return payload
