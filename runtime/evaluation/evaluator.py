from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from admission.decision_contracts import validate_decision_candidate
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
EVALUATOR_VERDICT_SCHEMA_PATH = CONTRACTS_ROOT / "evaluator_verdict.v1.schema.json"

NEGATIVE_LABELS = {
    "trivial_lookup",
    "ephemeral_chat",
    "restatement_only",
    "minor_detail",
    "test_prompt",
}
POSITIVE_LABELS = {
    "accepted_decision",
    "accepted_decision_ux",
    "architectural_boundary",
    "boundary_transition",
    "correction",
    "deep_dive",
    "durable_decision",
    "explicit_decision",
    "hard_to_rederive",
    "novel_synthesis",
    "real_ux_regression",
    "substantial_comparison",
    "supersession",
}
HIGH_REASONING_LABELS = {
    "ambiguous",
    "cross_provider_conflict",
    "needs_high_reasoning",
}


@lru_cache(maxsize=1)
def load_evaluator_verdict_schema() -> dict[str, Any]:
    return json.loads(EVALUATOR_VERDICT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_evaluator_verdict(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_evaluator_verdict_schema())


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def _labels(candidate: Mapping[str, Any]) -> set[str]:
    return {str(label).strip() for label in candidate.get("reason_labels") or [] if str(label).strip()}


def _worthiness_score(*, confidence: float, labels: set[str], stability_state: str) -> float:
    score = confidence
    if labels & POSITIVE_LABELS:
        score += 0.12
    if labels & NEGATIVE_LABELS:
        score -= 0.35
    if stability_state == "stable":
        score += 0.08
    elif stability_state == "superseding":
        score += 0.05
    elif stability_state == "provisional":
        score -= 0.04
    return max(0.0, min(1.0, round(score, 4)))


def _prefilter_boundary(*, evaluator_status: str, requires_high_reasoning: bool) -> str:
    if requires_high_reasoning:
        return "provider_reasoning_required"
    if evaluator_status == "accept_for_amundsen":
        return "deterministic_accept"
    if evaluator_status == "reject":
        return "deterministic_reject"
    return "deterministic_defer"


def evaluate_decision_candidate(
    *,
    decision_candidate: Mapping[str, Any],
    high_reasoning_available: bool = False,
) -> dict[str, Any]:
    """Evaluate candidate worthiness without choosing category or placement.

    Evaluator may decide whether Amundsen may receive the candidate. It must
    not emit category keys, placement targets, canonical paths, or mailbox
    mutations.
    """

    validate_decision_candidate(decision_candidate)
    labels = _labels(decision_candidate)
    confidence = _clamp_score(decision_candidate.get("confidence_score"))
    stability_state = str(decision_candidate.get("stability_state") or "provisional")
    trigger_reason = str(decision_candidate.get("trigger_reason") or "").lower()
    decision_text = str(decision_candidate.get("decision_text") or "").strip()
    worthiness = _worthiness_score(
        confidence=confidence,
        labels=labels,
        stability_state=stability_state,
    )
    reason_codes: list[str] = []
    requires_high_reasoning = bool(labels & HIGH_REASONING_LABELS)

    if labels & NEGATIVE_LABELS:
        evaluator_status = "reject"
        reason_codes.append("negative_reason_label")
    elif confidence < 0.35:
        evaluator_status = "reject"
        reason_codes.append("confidence_below_reject_threshold")
    elif requires_high_reasoning:
        evaluator_status = "defer"
        reason_codes.append("high_reasoning_required")
        if high_reasoning_available:
            reason_codes.append("high_reasoning_available_but_phase_4_not_owned")
    elif "context_pressure" in labels or "context_pressure" in trigger_reason:
        evaluator_status = "defer"
        reason_codes.append("context_pressure_defer")
    elif confidence < 0.55:
        evaluator_status = "defer"
        reason_codes.append("confidence_below_handoff_threshold")
    else:
        evaluator_status = "accept_for_amundsen"
        reason_codes.append("candidate_worthy_for_category_decision")

    amundsen_handoff_allowed = evaluator_status == "accept_for_amundsen"
    promotion_recommendation = (
        evaluator_status == "accept_for_amundsen"
        and worthiness >= 0.68
        and stability_state in {"stable", "superseding"}
    )
    if evaluator_status == "reject":
        promotion_gate = "rejected"
    elif promotion_recommendation:
        promotion_gate = "ready"
    elif evaluator_status == "defer":
        promotion_gate = "not_ready"
    else:
        promotion_gate = "deferred_to_phase_5"

    if promotion_recommendation:
        reason_codes.append("promotion_candidate_ready")
    elif evaluator_status == "accept_for_amundsen":
        reason_codes.append("category_handoff_only")

    phase4_handoff_recommended = requires_high_reasoning
    prefilter_boundary = _prefilter_boundary(
        evaluator_status=evaluator_status,
        requires_high_reasoning=requires_high_reasoning,
    )
    verdict = {
        "schema_version": "evaluator_verdict.v1",
        "evaluator_verdict_id": uuid.uuid4().hex,
        "candidate_id": str(decision_candidate["candidate_id"]),
        "dedup_key": str(decision_candidate["dedup_key"]),
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "turn_start": int(decision_candidate["turn_start"]),
        "turn_end": int(decision_candidate["turn_end"]),
        "evaluator_status": evaluator_status,
        "promotion_recommendation": promotion_recommendation,
        "promotion_gate": promotion_gate,
        "worthiness_score": worthiness,
        "confidence_score": confidence,
        "amundsen_handoff_allowed": amundsen_handoff_allowed,
        "requires_high_reasoning": requires_high_reasoning,
        "decision_authority": "deterministic_prefilter_only",
        "prefilter_boundary": prefilter_boundary,
        "high_reasoning_status": (
            "needed_deferred_to_phase_4" if requires_high_reasoning else "not_needed"
        ),
        "phase4_handoff_recommended": phase4_handoff_recommended,
        "provider_credential_required": False,
        "reason_codes": reason_codes,
        "verdict_summary": decision_text[:180] or "Decision candidate evaluated.",
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
        "evaluated_at": utc_now_iso(),
    }
    validate_evaluator_verdict(verdict)
    return verdict
