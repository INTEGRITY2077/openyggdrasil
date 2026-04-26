from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from admission.admission_stub import admit_evaluator_handoff
from admission.amundsen_nursery_handoff import build_amundsen_nursery_handoff
from admission.decision_contracts import (
    validate_cultivated_decision,
    validate_session_signal_runner_result,
    validate_session_structure_signal,
    validate_thin_worker_chain_result,
)
from capture.decision_distiller import finalize_exhaustive_decision_candidates
from common.map_identity import build_claim_id
from cultivation.gardener_routing import build_gardener_routing_decision
from cultivation.gardener_stub import plan_seed_planting
from cultivation.nursery_composition_input import build_nursery_composition_input
from cultivation.nursery_stub import engrave_composed_decision_seed
from cultivation.seedkeeper import preserve_decision_segment
from delivery.postman_finalization import build_postman_delivery_handoff
from evaluation.evaluator import evaluate_decision_candidate
from evaluation.evaluator_amundsen_handoff import build_evaluator_amundsen_handoff
from harness_common import DEFAULT_VAULT, utc_now_iso
from placement.map_maker_stub import update_map_topography


ROLE_ORDER = (
    "distiller",
    "evaluator",
    "amundsen",
    "seedkeeper",
    "gardener",
    "map_maker",
    "postman",
)

ThinCandidateRenderer = Callable[..., Mapping[str, Any] | Sequence[Mapping[str, Any]]]
RoleFallbacks = Mapping[str, str]
TRIGGER_CONFIDENCE_BONUS = {
    "correction_supersession_trigger": 0.14,
    "hard_trigger": 0.08,
    "boundary_trigger": 0.07,
    "retrieval_need_trigger": 0.04,
}


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def _source_refs_from_signal(signal: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_ref = signal.get("source_ref")
    if isinstance(source_ref, Mapping):
        return [
            {
                "kind": "provider_session",
                "path_hint": str(source_ref.get("path_hint") or "missing-source-ref").strip(),
                "range_hint": source_ref.get("range_hint"),
                "symlink_hint": source_ref.get("symlink_hint"),
                "message_id": None,
            }
        ]
    return [
        {
            "kind": "provider_session",
            "path_hint": "missing-source-ref",
            "range_hint": None,
            "symlink_hint": None,
            "message_id": None,
        }
    ]


def _source_refs(
    *,
    signal: Mapping[str, Any],
    runner_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    refs = runner_result.get("source_refs")
    if isinstance(refs, list) and refs:
        return [dict(ref) for ref in refs if isinstance(ref, Mapping)]
    return _source_refs_from_signal(signal)


def _source_ref_token(signal: Mapping[str, Any]) -> str:
    source_ref = signal.get("source_ref")
    if not isinstance(source_ref, Mapping):
        return "provider_session:missing-source-ref"
    path_hint = str(source_ref.get("path_hint") or "missing-source-ref").strip()
    range_hint = str(source_ref.get("range_hint") or "").strip()
    return f"provider_session:{path_hint}#{range_hint}" if range_hint else f"provider_session:{path_hint}"


def _trigger_parts(trigger_reason: str) -> tuple[str, list[str]]:
    trigger_head, _, raw_labels = trigger_reason.partition(":")
    labels = [label.strip() for label in raw_labels.split(",") if label.strip()]
    return trigger_head.strip(), labels


def compute_rule_based_candidate_confidence(*, decision_surface: Mapping[str, Any]) -> float:
    trigger_head, labels = _trigger_parts(str(decision_surface.get("trigger_reason") or ""))
    score = 0.50
    score += TRIGGER_CONFIDENCE_BONUS.get(trigger_head, 0.0)
    score += min(len(labels) * 0.04, 0.12)
    source_ref = str(decision_surface.get("source_ref") or "")
    if source_ref and "missing-source-ref" not in source_ref:
        score += 0.08
    try:
        turn_count = int(decision_surface["turn_end"]) - int(decision_surface["turn_start"]) + 1
    except Exception:
        turn_count = 0
    if 1 <= turn_count <= 8:
        score += 0.02
    return round(max(0.0, min(1.0, score)), 2)


def _origin_locator(signal: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = dict(signal.get("source_ref") or {})
    return {
        "signal_id": _string_field(signal, "signal_id", "invalid-signal"),
        "source_ref_kind": str(source_ref.get("kind") or "provider_session"),
        "path_hint": str(source_ref.get("path_hint") or "missing-source-ref").strip(),
        "range_hint": source_ref.get("range_hint"),
        "symlink_hint": source_ref.get("symlink_hint"),
        "anchor_hash": signal.get("anchor_hash"),
    }


def build_decision_surface_from_signal(signal: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a bounded provider signal into the existing decision surface contract.

    The conversation excerpt is synthetic and signal-only; it is not copied provider raw text.
    """

    validate_session_structure_signal(signal)
    turn_range = dict(signal["turn_range"])
    surface_reason = str(signal["surface_reason"]).strip()
    trigger_type = str(signal["trigger_type"]).strip()
    reason_labels = [str(label).strip() for label in signal.get("reason_labels") or [] if str(label).strip()]
    return {
        "schema_version": "decision_surface.v1",
        "provider_id": str(signal["provider_id"]),
        "provider_profile": str(signal["provider_profile"]),
        "provider_session_id": str(signal["provider_session_id"]),
        "session_uid": str(signal["session_uid"]),
        "turn_start": int(turn_range["from"]),
        "turn_end": int(turn_range["to"]),
        "surface_summary": surface_reason,
        "trigger_reason": f"{trigger_type}:{','.join(reason_labels)}",
        "topic_hint": None,
        "source_ref": _source_ref_token(signal),
        "conversation_excerpt": [
            {
                "role": "provider_signal",
                "text": surface_reason,
            }
        ],
        "origin_locator": _origin_locator(signal),
        "created_at": utc_now_iso(),
    }


def _default_candidate_renderer(*, decision_surface: Mapping[str, Any]) -> Mapping[str, Any]:
    turn_start = int(decision_surface["turn_start"])
    turn_end = int(decision_surface["turn_end"])
    trigger_reason = str(decision_surface["trigger_reason"])
    surface_summary = str(decision_surface["surface_summary"])
    trigger_head, _labels = _trigger_parts(trigger_reason)
    trigger_head = trigger_head or "signal"
    return {
        "decision_text": f"Structure provider session turns {turn_start}-{turn_end}: {surface_summary}",
        "rationale": f"Accepted bounded provider signal through {trigger_head}.",
        "alternatives_rejected": [],
        "stability_state": "superseding" if trigger_head == "correction_supersession_trigger" else "provisional",
        "topic_hint": f"session-structure/{trigger_head}",
        "reason_labels": ["thin_worker_chain", trigger_head],
        "confidence_score": compute_rule_based_candidate_confidence(decision_surface=decision_surface),
    }


def _cultivation_intent(
    *,
    engraved_seed: Mapping[str, Any],
    planting_decision: Mapping[str, Any],
    gardener_routing_decision: Mapping[str, Any],
) -> dict[str, Any]:
    created = utc_now_iso()
    topic_id = str(engraved_seed["topic_id"])
    canonical_relative_path = str(gardener_routing_decision["canonical_relative_path"])
    provenance_rel = str(gardener_routing_decision["provenance_relative_path"])
    cultivated = {
        "schema_version": "cultivated_decision.v1",
        "cultivation_id": uuid.uuid4().hex,
        "planting_id": str(planting_decision["planting_id"]),
        "seed_id": str(engraved_seed["seed_id"]),
        "candidate_id": str(engraved_seed["candidate_id"]),
        "topic_id": topic_id,
        "topic_title": str(engraved_seed["topic_title"]),
        "page_id": str(engraved_seed["page_id"]),
        "canonical_relative_path": canonical_relative_path,
        "provenance_relative_path": provenance_rel,
        "canonical_note_path": str(gardener_routing_decision["canonical_note_path"]),
        "provenance_note_path": str(gardener_routing_decision["provenance_note_path"]),
        "claim_id": build_claim_id(
            topic_id=topic_id,
            claim_key=f"{str(engraved_seed['episode_id'])}:summary",
        ),
        "decision_text": str(engraved_seed["decision_text"]),
        "support_fact": str(engraved_seed["decision_text"]),
        "planting_target_kind": str(planting_decision["planting_target_kind"]),
        "planting_target_key": str(planting_decision["planting_target_key"]),
        "source_rel": canonical_relative_path,
        "cultivated_at": created,
    }
    validate_cultivated_decision(cultivated)
    return cultivated


def _empty_artifacts() -> dict[str, Any]:
    return {
        "decision_candidate": None,
        "decision_candidate_batch": None,
        "evaluator_verdict": None,
        "evaluator_amundsen_handoff": None,
        "admission_verdict": None,
        "amundsen_nursery_handoff": None,
        "seedkeeper_segment": None,
        "nursery_composition_input": None,
        "engraved_seed": None,
        "planting_decision": None,
        "gardener_routing_decision": None,
        "cultivated_decision": None,
        "map_topography": None,
    }


def _artifact_id(role: str, artifacts: Mapping[str, Any]) -> tuple[str | None, str | None]:
    if role == "distiller":
        artifact = artifacts.get("decision_candidate_batch")
        if isinstance(artifact, Mapping):
            return "decision_candidate_batch", str(artifact.get("batch_id"))
        artifact = artifacts.get("decision_candidate")
        return "decision_candidate", str(artifact.get("candidate_id")) if isinstance(artifact, Mapping) else None
    if role == "evaluator":
        artifact = artifacts.get("evaluator_verdict")
        return "evaluator_verdict", str(artifact.get("evaluator_verdict_id")) if isinstance(artifact, Mapping) else None
    if role == "amundsen":
        artifact = artifacts.get("amundsen_nursery_handoff")
        if isinstance(artifact, Mapping):
            return "amundsen_nursery_handoff", str(artifact.get("handoff_id"))
        artifact = artifacts.get("admission_verdict")
        return "topic_route", str(artifact.get("continent_id")) if isinstance(artifact, Mapping) else None
    if role == "seedkeeper":
        artifact = artifacts.get("seedkeeper_segment")
        return "seedkeeper_segment", str(artifact.get("segment_id")) if isinstance(artifact, Mapping) else None
    if role == "gardener":
        artifact = artifacts.get("gardener_routing_decision")
        if isinstance(artifact, Mapping):
            return "gardener_routing_decision", str(artifact.get("routing_id"))
        artifact = artifacts.get("planting_decision")
        return "planting_decision", str(artifact.get("planting_id")) if isinstance(artifact, Mapping) else None
    if role == "map_maker":
        artifact = artifacts.get("map_topography")
        return "map_topography", str(artifact.get("topography_id")) if isinstance(artifact, Mapping) else None
    return "postman_handoff", None


def _role_steps(
    *,
    completed_roles: set[str],
    blocked_role: str | None,
    fallback_role: str | None,
    artifacts: Mapping[str, Any],
    stop_reason: str | None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        artifact_kind, artifact_id = _artifact_id(role, artifacts)
        if role in completed_roles:
            status = "completed"
            reason_codes = [f"{role}_completed"]
            if role == "distiller":
                reason_codes.append("exhaustive_candidate_batch")
            if role == "evaluator":
                reason_codes.append("session_admission_preserved")
            elif role == "amundsen":
                reason_codes.append("nursery_route_explicit")
            elif role == "seedkeeper":
                reason_codes.append("source_ref_preserved")
                reason_codes.append("nursery_boundary_ready")
            elif role == "gardener":
                reason_codes.append("forest_routing_only")
        elif role == fallback_role:
            status = "fallback_used"
            reason_codes = [stop_reason or f"{role}_fallback_used"]
        elif role == blocked_role:
            status = "blocked"
            reason_codes = [stop_reason or f"{role}_blocked"]
        else:
            status = "skipped"
            reason_codes = ["not_reached"]
            artifact_kind = None
            artifact_id = None
        if role == "postman" and role in completed_roles:
            status = "ready"
            reason_codes = ["postman_handoff_ready", "mailbox_emission_deferred_to_r3"]
        steps.append(
            {
                "role": role,
                "status": status,
                "artifact_kind": artifact_kind,
                "artifact_id": artifact_id,
                "reason_codes": reason_codes,
            }
        )
    return steps


def _postman_handoff(
    *,
    admission_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any],
    runner_result: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    session_admission = dict(runner_result.get("admission_verdict") or {})
    return build_postman_delivery_handoff(
        admission_verdict=admission_verdict,
        map_topography=map_topography,
        source_refs=source_refs,
        session_admission_verdict_id=session_admission.get("verdict_id"),
    )


def _result(
    *,
    signal: Mapping[str, Any],
    runner_result: Mapping[str, Any],
    status: str,
    stop_reason: str | None,
    completed_roles: set[str],
    blocked_role: str | None,
    fallback_role: str | None = None,
    artifacts: Mapping[str, Any],
    postman_handoff: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_refs = _source_refs(signal=signal, runner_result=runner_result)
    fallback_reason = stop_reason or None
    result = {
        "schema_version": "thin_worker_chain_result.v1",
        "chain_result_id": uuid.uuid4().hex,
        "runner_result_id": _string_field(runner_result, "runner_result_id", "missing-runner-result"),
        "signal_id": _string_field(signal, "signal_id", _string_field(runner_result, "signal_id", "invalid-signal")),
        "provider_id": _string_field(signal, "provider_id", _string_field(runner_result, "provider_id")),
        "provider_profile": _string_field(signal, "provider_profile", _string_field(runner_result, "provider_profile")),
        "provider_session_id": _string_field(
            signal,
            "provider_session_id",
            _string_field(runner_result, "provider_session_id"),
        ),
        "session_uid": _string_field(signal, "session_uid", _string_field(runner_result, "session_uid")),
        "status": status,
        "stop_reason": stop_reason,
        "role_steps": _role_steps(
            completed_roles=completed_roles,
            blocked_role=blocked_role,
            fallback_role=fallback_role,
            artifacts=artifacts,
            stop_reason=stop_reason,
        ),
        "source_refs": source_refs,
        "mailbox_packet_refs": [],
        "fallback_state": {
            "fallback_used": fallback_reason is not None,
            "fallback_reason": fallback_reason,
            "quarantine": bool(dict(runner_result.get("fallback_state") or {}).get("quarantine")),
        },
        "artifacts": dict(artifacts),
        "postman_handoff": dict(postman_handoff) if isinstance(postman_handoff, Mapping) else None,
        "next_action": "emit_mailbox_support_result" if status == "completed" else "stop",
        "created_at": utc_now_iso(),
    }
    validate_thin_worker_chain_result(result)
    return result


def _stopped_result(
    *,
    signal: Mapping[str, Any],
    runner_result: Mapping[str, Any],
    stop_reason: str,
    blocked_role: str = "distiller",
    fallback_role: str | None = None,
    completed_roles: set[str] | None = None,
    artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        signal=signal,
        runner_result=runner_result,
        status="stopped",
        stop_reason=stop_reason,
        completed_roles=completed_roles or set(),
        blocked_role=blocked_role,
        fallback_role=fallback_role,
        artifacts=artifacts or _empty_artifacts(),
        postman_handoff=None,
    )


def _fallback_reason(role: str, role_fallbacks: RoleFallbacks | None) -> str | None:
    if role_fallbacks is None:
        return None
    reason = str(role_fallbacks.get(role) or "").strip()
    if not reason:
        return None
    return f"{role}_fallback_used:{reason}"


def _raw_candidate_payloads(rendered: Any) -> list[Any]:
    if isinstance(rendered, Mapping):
        return [rendered]
    if isinstance(rendered, Sequence) and not isinstance(rendered, (str, bytes, bytearray)):
        return list(rendered)
    return [rendered]


def _fallback_result_if_requested(
    *,
    role: str,
    role_fallbacks: RoleFallbacks | None,
    signal: Mapping[str, Any],
    runner_result: Mapping[str, Any],
    completed_roles: set[str],
    artifacts: Mapping[str, Any],
) -> dict[str, Any] | None:
    reason = _fallback_reason(role, role_fallbacks)
    if reason is None:
        return None
    return _stopped_result(
        signal=signal,
        runner_result=runner_result,
        stop_reason=reason,
        blocked_role=None,
        fallback_role=role,
        completed_roles=completed_roles,
        artifacts=artifacts,
    )


def run_thin_worker_chain(
    *,
    signal: Mapping[str, Any],
    runner_result: Mapping[str, Any],
    candidate_renderer: ThinCandidateRenderer | None = None,
    role_fallbacks: RoleFallbacks | None = None,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """Run R2: accepted signal to deterministic role-boundary chain result.

    This function never writes mailbox packets and never copies provider raw sessions.
    """

    try:
        validate_session_signal_runner_result(runner_result)
    except Exception as exc:
        return _stopped_result(
            signal=signal,
            runner_result=runner_result,
            stop_reason=f"runner_result_invalid:{exc.__class__.__name__}",
            blocked_role="distiller",
        )

    if runner_result.get("status") != "runner_plan_ready":
        return _stopped_result(
            signal=signal,
            runner_result=runner_result,
            stop_reason=str(runner_result.get("stop_reason") or "runner_not_ready"),
            blocked_role="distiller",
        )

    artifacts = _empty_artifacts()
    completed_roles: set[str] = set()
    active_vault_root = (vault_root or DEFAULT_VAULT).resolve()

    try:
        fallback = _fallback_result_if_requested(
            role="distiller",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        decision_surface = build_decision_surface_from_signal(signal)
        raw_candidates = _raw_candidate_payloads(
            (candidate_renderer or _default_candidate_renderer)(decision_surface=decision_surface)
        )
        decision_candidate_batch = finalize_exhaustive_decision_candidates(
            decision_surface=decision_surface,
            raw_candidates=raw_candidates,
        )
        artifacts["decision_candidate_batch"] = decision_candidate_batch
        if decision_candidate_batch["exhaustiveness_status"] != "exhaustive":
            return _stopped_result(
                signal=signal,
                runner_result=runner_result,
                stop_reason="distiller_deterministic_skip:no_valid_raw_candidates",
                blocked_role="distiller",
                completed_roles=completed_roles,
                artifacts=artifacts,
            )
        decision_candidate = dict(decision_candidate_batch["candidates"][0])
        artifacts["decision_candidate"] = decision_candidate
        completed_roles.add("distiller")

        fallback = _fallback_result_if_requested(
            role="evaluator",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        evaluator_verdict = evaluate_decision_candidate(
            decision_candidate=decision_candidate,
        )
        evaluator_handoff = build_evaluator_amundsen_handoff(
            decision_candidate=decision_candidate,
            evaluator_verdict=evaluator_verdict,
        )
        artifacts["evaluator_verdict"] = evaluator_verdict
        artifacts["evaluator_amundsen_handoff"] = evaluator_handoff
        completed_roles.add("evaluator")
        if evaluator_handoff["handoff_status"] != "ready_for_amundsen":
            return _stopped_result(
                signal=signal,
                runner_result=runner_result,
                stop_reason=str(evaluator_handoff["blocked_reason"]),
                blocked_role="amundsen",
                completed_roles=completed_roles,
                artifacts=artifacts,
            )

        fallback = _fallback_result_if_requested(
            role="amundsen",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        admission_verdict = admit_evaluator_handoff(
            evaluator_amundsen_handoff=evaluator_handoff,
            vault_root=active_vault_root,
        )
        amundsen_nursery_handoff = build_amundsen_nursery_handoff(admission_verdict=admission_verdict)
        artifacts["admission_verdict"] = admission_verdict
        artifacts["amundsen_nursery_handoff"] = amundsen_nursery_handoff
        if amundsen_nursery_handoff["handoff_status"] != "ready_for_nursery":
            return _stopped_result(
                signal=signal,
                runner_result=runner_result,
                stop_reason=str(amundsen_nursery_handoff["blocked_reason"]),
                blocked_role="amundsen",
                completed_roles=completed_roles,
                artifacts=artifacts,
            )
        completed_roles.add("amundsen")

        fallback = _fallback_result_if_requested(
            role="seedkeeper",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        seedkeeper_segment = preserve_decision_segment(decision_candidate=decision_candidate)
        artifacts["seedkeeper_segment"] = seedkeeper_segment
        if seedkeeper_segment["preservation_status"] != "preserved":
            return _stopped_result(
                signal=signal,
                runner_result=runner_result,
                stop_reason=str(seedkeeper_segment["integrity_reason"]),
                blocked_role="seedkeeper",
                completed_roles=completed_roles,
                artifacts=artifacts,
            )
        completed_roles.add("seedkeeper")
        nursery_composition_input = build_nursery_composition_input(
            decision_candidate=decision_candidate,
            evaluator_verdict=evaluator_verdict,
            amundsen_nursery_handoff=amundsen_nursery_handoff,
            seedkeeper_segment=seedkeeper_segment,
        )
        artifacts["nursery_composition_input"] = nursery_composition_input
        if nursery_composition_input["composition_status"] != "ready_for_seed_composition":
            return _stopped_result(
                signal=signal,
                runner_result=runner_result,
                stop_reason=str(nursery_composition_input["blocked_reason"]),
                blocked_role="gardener",
                completed_roles=completed_roles,
                artifacts=artifacts,
            )

        fallback = _fallback_result_if_requested(
            role="gardener",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        engraved_seed = engrave_composed_decision_seed(
            nursery_composition_input=nursery_composition_input,
        )
        artifacts["engraved_seed"] = engraved_seed
        planting_decision = plan_seed_planting(engraved_seed=engraved_seed)
        artifacts["planting_decision"] = planting_decision
        gardener_routing_decision = build_gardener_routing_decision(
            engraved_seed=engraved_seed,
            planting_decision=planting_decision,
            vault_root=active_vault_root,
        )
        artifacts["gardener_routing_decision"] = gardener_routing_decision
        cultivated_decision = _cultivation_intent(
            engraved_seed=engraved_seed,
            planting_decision=planting_decision,
            gardener_routing_decision=gardener_routing_decision,
        )
        artifacts["cultivated_decision"] = cultivated_decision
        completed_roles.add("gardener")

        fallback = _fallback_result_if_requested(
            role="map_maker",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        map_topography = update_map_topography(
            planting_decision=planting_decision,
            cultivated_decision=cultivated_decision,
            amundsen_nursery_handoff=amundsen_nursery_handoff,
            gardener_routing_decision=gardener_routing_decision,
        )
        artifacts["map_topography"] = map_topography
        completed_roles.add("map_maker")

        fallback = _fallback_result_if_requested(
            role="postman",
            role_fallbacks=role_fallbacks,
            signal=signal,
            runner_result=runner_result,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
        if fallback is not None:
            return fallback
        handoff = _postman_handoff(
            admission_verdict=admission_verdict,
            map_topography=map_topography,
            runner_result=runner_result,
            source_refs=_source_refs(signal=signal, runner_result=runner_result),
        )
        completed_roles.add("postman")
        return _result(
            signal=signal,
            runner_result=runner_result,
            status="completed",
            stop_reason=None,
            completed_roles=completed_roles,
            blocked_role=None,
            fallback_role=None,
            artifacts=artifacts,
            postman_handoff=handoff,
        )
    except Exception as exc:
        next_role = next((role for role in ROLE_ORDER if role not in completed_roles), "postman")
        return _stopped_result(
            signal=signal,
            runner_result=runner_result,
            stop_reason=f"{next_role}_failed:{exc.__class__.__name__}",
            blocked_role=next_role,
            completed_roles=completed_roles,
            artifacts=artifacts,
        )
