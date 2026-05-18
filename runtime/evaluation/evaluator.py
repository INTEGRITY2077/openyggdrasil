from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from admission.decision_contracts import validate_decision_candidate
from delivery.support_bundle import validate_support_bundle
from harness_common import utc_now_iso
from evaluation.why_remembered_answer import validate_why_remembered_answer
from reasoning.lease_executor import (
    build_reasoning_lease_mailbox_job,
    validate_reasoning_lease_mailbox_job,
)
from reasoning.module_effort_requirements import build_high_effort_reasoning_lease_request


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
    "substantial_comparison",
    "supersession",
}
HIGH_REASONING_LABELS = {
    "ambiguous",
    "cross_provider_conflict",
    "needs_high_reasoning",
}
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
DOWNSTREAM_EVIDENCE_KINDS = [
    "decision_candidate",
    "evaluator_verdict",
    "support_bundle",
    "answer_verdict",
]
UNSAFE_DOWNSTREAM_TOKENS = (
    "d:/",
    "c:/",
    "file://",
    "raw_transcript",
    "raw transcript",
    "transcript.txt",
    "api_key",
)


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


def _retrieval_terms(value: Any) -> set[str]:
    text = json.dumps(value, sort_keys=True, default=str).lower() if not isinstance(value, str) else value.lower()
    tokens: list[str] = []
    token = ""
    for char in text:
        if char.isalnum():
            token += char
        elif token:
            tokens.append(token)
            token = ""
    if token:
        tokens.append(token)
    stopwords = {"and", "for", "the", "with", "from", "this", "that", "should", "must"}
    return {item for item in tokens if len(item) >= 3 and item not in stopwords}


def build_retrieval_utility_score(
    *,
    decision_candidate: Mapping[str, Any],
    topic_index_entries: Sequence[Mapping[str, Any]] | None = None,
    baseline_score: float = 0.0,
) -> dict[str, Any]:
    """Estimate whether the candidate would improve Pathfinder retrieval."""

    candidate_terms = _retrieval_terms(
        {
            "topic_hint": decision_candidate.get("topic_hint"),
            "surface_summary": decision_candidate.get("surface_summary"),
            "decision_text": decision_candidate.get("decision_text"),
            "rationale": decision_candidate.get("rationale"),
            "reason_labels": decision_candidate.get("reason_labels"),
        }
    )
    entries = [dict(entry) for entry in topic_index_entries or ()]
    overlaps: list[float] = []
    matched_topic_refs: list[str] = []
    for entry in entries:
        entry_terms = _retrieval_terms(
            {
                "topic_key": entry.get("topic_key"),
                "title": entry.get("title"),
                "one_line_summary": entry.get("one_line_summary"),
                "aliases": entry.get("aliases"),
            }
        )
        overlap = len(candidate_terms & entry_terms) / max(1, min(len(candidate_terms), len(entry_terms)))
        if overlap >= 0.15:
            overlaps.append(overlap)
            matched_topic_refs.append(str(entry.get("topic_ref") or entry.get("topic_key") or "topic-index-entry"))
    intrinsic_signal = min(0.45, len(candidate_terms) / 40.0)
    confidence_signal = _clamp_score(decision_candidate.get("confidence_score")) * 0.35
    best_overlap = max(overlaps or [0.0])
    candidate_score = _clamp_score(round(max(best_overlap, intrinsic_signal) + confidence_signal, 4))
    baseline = _clamp_score(baseline_score)
    delta = round(candidate_score - baseline, 4)
    utility_decision = "keep" if candidate_score >= 0.35 and delta >= 0.02 else "discard"
    return {
        "schema_version": "retrieval_utility_score.v1",
        "baseline_score": baseline,
        "candidate_score": candidate_score,
        "utility_delta": delta,
        "utility_decision": utility_decision,
        "matched_topic_count": len(matched_topic_refs),
        "matched_topic_refs": matched_topic_refs[:8],
        "candidate_term_count": len(candidate_terms),
        "reason_codes": [
            "retrieval_utility_simulated_from_candidate_terms",
            f"retrieval_utility_{utility_decision}",
        ],
    }


def _prefilter_boundary(*, evaluator_status: str, requires_high_reasoning: bool) -> str:
    if requires_high_reasoning:
        return "provider_reasoning_required"
    if evaluator_status == "accept_for_amundsen":
        return "deterministic_accept"
    if evaluator_status == "reject":
        return "deterministic_reject"
    return "deterministic_defer"


def _vault_promotion_readiness(
    *, evaluator_status: str, promotion_recommendation: bool
) -> str:
    if evaluator_status == "reject":
        return "rejected"
    if promotion_recommendation:
        return "ready_after_delivery"
    return "not_ready"


def evaluate_decision_candidate(
    *,
    decision_candidate: Mapping[str, Any],
    high_reasoning_available: bool = False,
    retrieval_index_entries: Sequence[Mapping[str, Any]] | None = None,
    retrieval_baseline_score: float = 0.0,
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
    retrieval_utility = build_retrieval_utility_score(
        decision_candidate=decision_candidate,
        topic_index_entries=retrieval_index_entries,
        baseline_score=retrieval_baseline_score,
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

    if retrieval_utility["utility_decision"] == "discard":
        reason_codes.append("retrieval_utility_discard")
        if evaluator_status == "accept_for_amundsen":
            evaluator_status = "defer"
            reason_codes.append("retrieval_utility_deferred_category_handoff")
    else:
        reason_codes.append("retrieval_utility_keep")

    amundsen_handoff_allowed = evaluator_status == "accept_for_amundsen"
    promotion_recommendation = (
        evaluator_status == "accept_for_amundsen"
        and worthiness >= 0.68
        and stability_state in {"stable", "superseding"}
        and retrieval_utility["utility_decision"] == "keep"
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
    vault_promotion_readiness = _vault_promotion_readiness(
        evaluator_status=evaluator_status,
        promotion_recommendation=promotion_recommendation,
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
        "retrieval_utility_score": retrieval_utility["candidate_score"],
        "retrieval_utility_baseline_score": retrieval_utility["baseline_score"],
        "retrieval_utility_delta": retrieval_utility["utility_delta"],
        "retrieval_utility_decision": retrieval_utility["utility_decision"],
        "retrieval_utility_metrics": retrieval_utility,
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
        "vault_promotion_readiness": vault_promotion_readiness,
        "vault_promotion_owner": "phase_5_postman_after_delivery",
        "vault_promotion_request_emitted": False,
        "vault_mutation_allowed": False,
        "reason_codes": reason_codes,
        "verdict_summary": decision_text[:180] or "Decision candidate evaluated.",
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
        "evaluated_at": utc_now_iso(),
    }
    validate_evaluator_verdict(verdict)
    return verdict


def _assert_candidate_verdict_identity(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
) -> None:
    for field in IDENTITY_FIELDS:
        if decision_candidate.get(field) != evaluator_verdict.get(field):
            raise ValueError(f"evaluator downstream identity mismatch: {field}")


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_ref(prefix: str, payload: Mapping[str, Any]) -> str:
    return f"{prefix}://openyggdrasil/{_fingerprint(payload)[:32]}"


def _unsafe_downstream_tokens(payload: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str).replace("\\", "/").lower()
    return [token for token in UNSAFE_DOWNSTREAM_TOKENS if token in serialized]


def _candidate_verdict_summary(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": str(decision_candidate["candidate_id"]),
        "dedup_key": str(decision_candidate["dedup_key"]),
        "evaluator_verdict_id": str(evaluator_verdict["evaluator_verdict_id"]),
        "evaluator_status": str(evaluator_verdict["evaluator_status"]),
        "promotion_gate": str(evaluator_verdict["promotion_gate"]),
        "amundsen_handoff_allowed": bool(evaluator_verdict["amundsen_handoff_allowed"]),
        "requires_high_reasoning": bool(evaluator_verdict["requires_high_reasoning"]),
        "downstream_decision_evidence_ref": _safe_ref(
            "decision-candidate-ref",
            {
                "candidate_id": decision_candidate["candidate_id"],
                "evaluator_verdict_id": evaluator_verdict["evaluator_verdict_id"],
            },
        ),
    }


def _support_bundle_verdict(
    *,
    support_bundle: Mapping[str, Any],
    decision_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    bundle = dict(support_bundle)
    validate_support_bundle(bundle)
    facts = [str(fact).strip() for fact in bundle.get("facts") or [] if str(fact).strip()]
    source_paths = [
        str(path).strip()
        for path in bundle.get("source_paths") or []
        if str(path).strip()
    ]
    if not facts:
        raise ValueError("support bundle verdict requires facts")
    if not source_paths:
        raise ValueError("support bundle verdict requires source paths")
    decision_key = bundle.get("decision_key")
    if decision_key and decision_key != decision_candidate.get("dedup_key"):
        raise ValueError("support bundle decision_key must match candidate dedup_key")
    return {
        "verdict_status": "usable_for_downstream_decision",
        "support_bundle_ref": _safe_ref("support-bundle-ref", bundle),
        "source_packet_id": str(bundle["source_packet_id"]),
        "fact_count": len(facts),
        "source_path_count": len(source_paths),
        "decision_key": decision_key,
        "raw_provider_material_included": False,
        "local_filesystem_path_included": False,
    }


def _answer_verdict_summary(answer_verdict: Mapping[str, Any]) -> dict[str, Any]:
    answer = dict(answer_verdict)
    validate_why_remembered_answer(answer)
    if answer.get("decision") != "green_passed":
        raise ValueError("answer verdict must be green_passed")
    if int(answer.get("raw_transcript_leak_count") or 0) != 0:
        raise ValueError("answer verdict must not include raw transcript leaks")
    if float(answer.get("provenance_coverage") or 0.0) < 1.0:
        raise ValueError("answer verdict must have full provenance coverage")
    return {
        "answer_verdict_ref": _safe_ref("answer-verdict-ref", answer),
        "answer_id": str(answer["answer_id"]),
        "decision": str(answer["decision"]),
        "provenance_coverage": float(answer["provenance_coverage"]),
        "safe_evidence_pointer_coverage": float(answer["safe_evidence_pointer_coverage"]),
        "selection_reason_coverage": float(answer["selection_reason_coverage"]),
        "transcript_leak_count": int(answer["raw_transcript_leak_count"]),
    }


def _evidence_refs(
    *,
    candidate_verdict: Mapping[str, Any],
    bundle_verdict: Mapping[str, Any],
    answer_verdict: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "evidence_kind": "decision_candidate",
            "evidence_ref": str(candidate_verdict["downstream_decision_evidence_ref"]),
        },
        {
            "evidence_kind": "evaluator_verdict",
            "evidence_ref": _safe_ref(
                "evaluator-verdict-ref",
                {"evaluator_verdict_id": candidate_verdict["evaluator_verdict_id"]},
            ),
        },
        {
            "evidence_kind": "support_bundle",
            "evidence_ref": str(bundle_verdict["support_bundle_ref"]),
        },
        {
            "evidence_kind": "answer_verdict",
            "evidence_ref": str(answer_verdict["answer_verdict_ref"]),
        },
    ]


def _lease_route(
    *,
    module_id: str,
    mailbox_job: Mapping[str, Any],
) -> dict[str, Any]:
    validate_reasoning_lease_mailbox_job(mailbox_job)
    payload = dict(mailbox_job["payload"])
    if payload.get("lease_result_claimed") is not False:
        raise ValueError("lease result must not be claimed by queued route")
    return {
        "module_id": module_id,
        "delegated_through_reasoning_lease_executor": True,
        "lease_request_id": str(payload["lease_request_id"]),
        "lease_request_ref": str(payload["lease_request_ref"]),
        "mailbox_message_id": str(mailbox_job["message_id"]),
        "required_effort": str(payload["required_effort"]),
        "preferred_effort": str(payload["preferred_effort"]),
        "lease_group": str(payload["lease_group"]),
        "sandbox_required": bool(payload["sandbox_required"]),
        "synchronous_worker_called": bool(payload["synchronous_worker_called"]),
        "lease_result_claimed": bool(payload["lease_result_claimed"]),
        "mailbox_job": dict(mailbox_job),
    }


def validate_evaluator_downstream_decision_evidence(payload: Mapping[str, Any]) -> None:
    result = dict(payload)
    required = {
        "schema_version",
        "evidence_id",
        "connection_status",
        "connected_downstream_decision_evidence",
        "candidate_verdict",
        "bundle_verdict",
        "answer_verdict",
        "downstream_evidence_kinds",
        "downstream_decision_evidence",
        "lease_route_count",
        "lease_routes",
        "execution_policy",
        "reason_codes",
        "created_at",
    }
    missing = sorted(required - set(result))
    if missing:
        raise ValueError(f"evaluator downstream evidence is missing: {', '.join(missing)}")
    if result["schema_version"] != "evaluator_downstream_decision_evidence.v1":
        raise ValueError("invalid evaluator downstream evidence schema_version")
    if result["connection_status"] != "downstream_decision_evidence_connected":
        raise ValueError("downstream decision evidence must be connected")
    if result["connected_downstream_decision_evidence"] is not True:
        raise ValueError("downstream decision evidence must be connected")
    if result["downstream_evidence_kinds"] != DOWNSTREAM_EVIDENCE_KINDS:
        raise ValueError("downstream evidence kinds are incomplete")

    bundle_verdict = dict(result["bundle_verdict"])
    if bundle_verdict.get("verdict_status") != "usable_for_downstream_decision":
        raise ValueError("bundle verdict must be usable for downstream decision")
    if int(bundle_verdict.get("fact_count") or 0) <= 0:
        raise ValueError("bundle verdict requires facts")
    if int(bundle_verdict.get("source_path_count") or 0) <= 0:
        raise ValueError("bundle verdict requires source paths")
    if bundle_verdict.get("raw_provider_material_included") is not False:
        raise ValueError("raw provider material is not allowed")
    if bundle_verdict.get("local_filesystem_path_included") is not False:
        raise ValueError("local filesystem paths are not allowed")

    answer_verdict = dict(result["answer_verdict"])
    if answer_verdict.get("decision") != "green_passed":
        raise ValueError("answer verdict must be green_passed")
    if int(answer_verdict.get("transcript_leak_count") or 0) != 0:
        raise ValueError("answer verdict must not include raw transcript leaks")
    if float(answer_verdict.get("provenance_coverage") or 0.0) < 1.0:
        raise ValueError("answer verdict must have full provenance coverage")

    policy = dict(result["execution_policy"])
    if policy.get("high_effort_lease_delegation_required") is not True:
        raise ValueError("high-effort lease delegation is required")
    if policy.get("distiller_and_evaluator_delegated") is not True:
        raise ValueError("distiller and evaluator must be delegated")
    if policy.get("synchronous_worker_called") is not False:
        raise ValueError("synchronous worker must not be called")
    if policy.get("lease_result_claimed") is not False:
        raise ValueError("lease result must not be claimed")
    if policy.get("raw_provider_material_included") is not False:
        raise ValueError("raw provider material is not allowed")
    if policy.get("local_filesystem_path_included") is not False:
        raise ValueError("local filesystem paths are not allowed")

    lease_routes = [dict(route) for route in result["lease_routes"]]
    if int(result["lease_route_count"]) != len(lease_routes):
        raise ValueError("lease_route_count mismatch")
    route_modules = {route.get("module_id") for route in lease_routes}
    if route_modules != {"distiller", "evaluator"}:
        raise ValueError("distiller and evaluator lease routes are required")
    for route in lease_routes:
        if route.get("delegated_through_reasoning_lease_executor") is not True:
            raise ValueError("route must delegate through reasoning lease executor")
        if route.get("required_effort") != "high":
            raise ValueError("route must require high effort")
        if route.get("lease_group") != "deep_reasoning":
            raise ValueError("route must use deep_reasoning lease group")
        if route.get("synchronous_worker_called") is not False:
            raise ValueError("synchronous worker must not be called")
        if route.get("lease_result_claimed") is not False:
            raise ValueError("lease result must not be claimed")
        mailbox_job = route.get("mailbox_job")
        if not isinstance(mailbox_job, Mapping):
            raise ValueError("lease route requires mailbox_job")
        validate_reasoning_lease_mailbox_job(mailbox_job)

    unsafe = _unsafe_downstream_tokens(result)
    if unsafe:
        raise ValueError(f"unsafe downstream evidence material included: {', '.join(unsafe)}")


def build_evaluator_downstream_decision_evidence(
    *,
    decision_candidate: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
    support_bundle: Mapping[str, Any],
    answer_verdict: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Connect Evaluator verdicts to downstream evidence and lease routing."""

    candidate = dict(decision_candidate)
    verdict = dict(evaluator_verdict)
    validate_decision_candidate(candidate)
    validate_evaluator_verdict(verdict)
    _assert_candidate_verdict_identity(
        decision_candidate=candidate,
        evaluator_verdict=verdict,
    )
    created = created_at or utc_now_iso()
    candidate_verdict = _candidate_verdict_summary(
        decision_candidate=candidate,
        evaluator_verdict=verdict,
    )
    bundle_verdict = _support_bundle_verdict(
        support_bundle=support_bundle,
        decision_candidate=candidate,
    )
    answer_summary = _answer_verdict_summary(answer_verdict)
    evidence_refs = _evidence_refs(
        candidate_verdict=candidate_verdict,
        bundle_verdict=bundle_verdict,
        answer_verdict=answer_summary,
    )
    input_refs = {
        item["evidence_kind"]: item["evidence_ref"]
        for item in evidence_refs
    }

    lease_routes: list[dict[str, Any]] = []
    for module_id in ("distiller", "evaluator"):
        lease_request = build_high_effort_reasoning_lease_request(
            module_id=module_id,
            input_refs=input_refs,
            provider_id=str(candidate["provider_id"]),
            provider_profile=str(candidate["provider_profile"]),
            provider_session_id=str(candidate["provider_session_id"]),
            session_uid=str(candidate["session_uid"]),
            requested_at=created,
            objective=(
                f"Review downstream decision evidence for {module_id} using safe evidence refs."
            ),
        )
        mailbox_job = build_reasoning_lease_mailbox_job(
            lease_request,
            created_at=created,
            producer_role="evaluator_downstream_decision_evidence",
        )
        lease_routes.append(_lease_route(module_id=module_id, mailbox_job=mailbox_job))

    result = {
        "schema_version": "evaluator_downstream_decision_evidence.v1",
        "evidence_id": uuid.uuid4().hex,
        "connection_status": "downstream_decision_evidence_connected",
        "connected_downstream_decision_evidence": True,
        "candidate_verdict": candidate_verdict,
        "bundle_verdict": bundle_verdict,
        "answer_verdict": answer_summary,
        "downstream_evidence_kinds": DOWNSTREAM_EVIDENCE_KINDS,
        "downstream_decision_evidence": evidence_refs,
        "lease_route_count": len(lease_routes),
        "lease_routes": lease_routes,
        "execution_policy": {
            "high_effort_lease_delegation_required": True,
            "distiller_and_evaluator_delegated": True,
            "synchronous_worker_called": False,
            "lease_result_claimed": False,
            "raw_provider_material_included": False,
            "local_filesystem_path_included": False,
        },
        "reason_codes": [
            "candidate_bundle_answer_verdicts_connected",
            "distiller_high_effort_delegated_to_reasoning_lease",
            "evaluator_high_effort_delegated_to_reasoning_lease",
            "downstream_decision_evidence_refs_only",
            "raw_provider_material_not_copied",
        ],
        "created_at": created,
    }
    validate_evaluator_downstream_decision_evidence(result)
    return result
