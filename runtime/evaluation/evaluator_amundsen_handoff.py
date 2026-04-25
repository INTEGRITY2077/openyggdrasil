from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_decision_candidate,
    validate_evaluator_amundsen_handoff,
    validate_evaluator_verdict,
)
from harness_common import utc_now_iso


IDENTITY_FIELDS = (
    "candidate_id",
    "dedup_key",
    "provider_id",
    "provider_profile",
    "provider_session_id",
    "session_uid",
    "turn_start",
    "turn_end",
)


def _assert_identity_match(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
) -> None:
    for field in IDENTITY_FIELDS:
        if decision_candidate.get(field) != evaluator_verdict.get(field):
            raise ValueError(f"evaluator handoff identity mismatch: {field}")


def build_evaluator_amundsen_handoff(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the only Phase 3 path from Evaluator into Amundsen.

    Evaluator owns semantic worth. Amundsen may only classify category/continent
    after this handoff says the candidate is ready.
    """

    validate_decision_candidate(decision_candidate)
    validate_evaluator_verdict(evaluator_verdict)
    _assert_identity_match(
        decision_candidate=decision_candidate,
        evaluator_verdict=evaluator_verdict,
    )

    allowed = bool(evaluator_verdict.get("amundsen_handoff_allowed"))
    evaluator_status = str(evaluator_verdict["evaluator_status"])
    ready = allowed and evaluator_status == "accept_for_amundsen"
    reason_codes = ["evaluator_to_amundsen_handoff_ready" if ready else "evaluator_blocked_amundsen_handoff"]
    reason_codes.extend(str(code) for code in evaluator_verdict.get("reason_codes") or [])
    handoff = {
        "schema_version": "evaluator_amundsen_handoff.v1",
        "handoff_id": uuid.uuid4().hex,
        "candidate_id": str(decision_candidate["candidate_id"]),
        "evaluator_verdict_id": str(evaluator_verdict["evaluator_verdict_id"]),
        "dedup_key": str(decision_candidate["dedup_key"]),
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "turn_start": int(decision_candidate["turn_start"]),
        "turn_end": int(decision_candidate["turn_end"]),
        "handoff_status": "ready_for_amundsen" if ready else "blocked_by_evaluator",
        "evaluator_status": evaluator_status,
        "amundsen_handoff_allowed": allowed,
        "decision_authority": "evaluator_prefilter_to_amundsen_category_only",
        "semantic_worth_authority": "evaluator_only",
        "category_authority": "amundsen_only_after_handoff",
        "promotion_authority": "phase_5_postman_after_delivery",
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "decision_candidate": dict(decision_candidate),
        "evaluator_verdict": dict(evaluator_verdict),
        "blocked_reason": None if ready else f"evaluator_status:{evaluator_status}",
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
        "created_at": utc_now_iso(),
    }
    validate_evaluator_amundsen_handoff(handoff)
    return handoff
