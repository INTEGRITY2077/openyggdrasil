from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.admission_stub import admit_evaluator_handoff
from admission.amundsen_nursery_handoff import build_amundsen_nursery_handoff
from admission.session_admission_gate import evaluate_session_structure_signal
from capture.decision_distiller import finalize_provider_structured_decision_candidate
from capture.session_structure_signal import build_session_structure_signal
from cultivation.gardener_routing import build_gardener_routing_decision
from cultivation.gardener_stub import cultivate_decision_seed, plan_seed_planting
from cultivation.nursery_composition_input import build_nursery_composition_input
from cultivation.nursery_stub import engrave_composed_decision_seed
from cultivation.seedkeeper import preserve_decision_segment
from delivery.mailbox_contamination_guard import ensure_mailbox_message_accepted
from delivery.mailbox_schema import validate_message
from delivery.mailbox_store import deliver_push_packet
from delivery.postman_finalization import build_postman_delivery_handoff
from delivery.postman_gateway import submit_packet
from evaluation.evaluator import evaluate_decision_candidate
from evaluation.evaluator_amundsen_handoff import build_evaluator_amundsen_handoff
from harness_common import DEFAULT_VAULT, utc_now_iso
from pipeline.producer_consumer_smoke import build_producer_consumer_smoke
from placement.map_maker_stub import update_map_topography


RUNTIME_OWNER = "runtime/pipeline/runtime_facade_chain.py"
SCHEMA_VERSION = "runtime_facade_chain_result.v1"
INTERNAL_PROVIDER_PROFILE = "runtime-facade-transition-prep"
REQUIRED_SAFE_REF_FIELDS = (
    "bundle_ref",
    "source_ref",
    "producer_request_ref",
    "production_receipt_ref",
    "support_bundle_ref",
    "consumer_menu_ref",
)
OPTIONAL_SAFE_REF_FIELDS = (
    "structured_output_ref",
    "tree_ring_snapshot_ref",
    "skill_metadata_ref",
    "provider_receipt_consumer_ref",
)
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|mnt|tmp|var|etc)/)",
    re.IGNORECASE,
)
RAW_SKILL_BODY_RE = re.compile(r"(?s)^---\s*\n.*\bname\s*:")
UNSAFE_KEY_REASONS = {
    "api_key": "credential_material_not_allowed",
    "credential": "credential_material_not_allowed",
    "credentials": "credential_material_not_allowed",
    "local_path": "portable_local_path_not_allowed",
    "password": "credential_material_not_allowed",
    "profile": "provider_profile_material_not_allowed",
    "provider_context": "raw_provider_material_not_allowed",
    "provider_material": "raw_provider_material_not_allowed",
    "provider_profile": "provider_profile_material_not_allowed",
    "raw_provider_context": "raw_provider_material_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "raw_session": "raw_transcript_not_allowed",
    "raw_skill_body": "raw_skill_body_not_allowed",
    "raw_text": "raw_transcript_not_allowed",
    "raw_transcript": "raw_transcript_not_allowed",
    "secret": "credential_material_not_allowed",
    "skill_body": "raw_skill_body_not_allowed",
    "token": "credential_material_not_allowed",
    "transcript": "raw_transcript_not_allowed",
}
UNSAFE_TEXT_FRAGMENTS = (
    ("raw transcript", "raw_transcript_not_allowed"),
    ("session transcript", "raw_transcript_not_allowed"),
    ("provider credential", "credential_material_not_allowed"),
    ("provider profile", "provider_profile_material_not_allowed"),
    ("api_key", "credential_material_not_allowed"),
    ("credential:", "credential_material_not_allowed"),
    ("password:", "credential_material_not_allowed"),
    ("secret:", "credential_material_not_allowed"),
    (".env", "credential_material_not_allowed"),
    (".skill.md", "raw_skill_body_not_allowed"),
)
HARD_NON_CLAIMS = {
    "sixth_full_close_claimed": False,
    "official_seventh_entry_claimed": False,
    "r9_real_session_pass_claimed": False,
    "r10_live_pass_claimed": False,
    "q7_live_structured_extraction_solved_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "background_live_integration_claimed": False,
    "p4_h6_closed_claimed": False,
    "hermes_answer_quality_claimed": False,
    "readiness_91_percent_claimed": False,
    "full_product_readiness_claimed": False,
    "consumer_ux_completion_claimed": False,
}


def _safe_ref(value: Any) -> str | None:
    text = str(value or "").strip()
    if not SAFE_REF_RE.fullmatch(text):
        return None
    lowered = text.lower()
    if LOCAL_PATH_RE.search(text):
        return None
    if any(fragment in lowered for fragment in ("credential", "transcript", ".skill.md", ".env")):
        return None
    return text


def _normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _unsafe_text_reason(value: str) -> str | None:
    if LOCAL_PATH_RE.search(value):
        return "portable_local_path_not_allowed"
    if RAW_SKILL_BODY_RE.search(value):
        return "raw_skill_body_not_allowed"
    lowered = value.lower()
    for fragment, reason in UNSAFE_TEXT_FRAGMENTS:
        if fragment in lowered:
            return reason
    return None


def _unsafe_bundle_reason(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalize_key(key)
            if normalized in UNSAFE_KEY_REASONS:
                return UNSAFE_KEY_REASONS[normalized]
            nested_reason = _unsafe_bundle_reason(child)
            if nested_reason is not None:
                return nested_reason
        return None
    if isinstance(value, list | tuple):
        for child in value:
            child_reason = _unsafe_bundle_reason(child)
            if child_reason is not None:
                return child_reason
        return None
    if isinstance(value, str):
        return _unsafe_text_reason(value)
    return None


def _stage_ref(stage: str, identifier: Any) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(identifier or "unknown")).strip("-")
    return f"runtime-stage-ref://openyggdrasil/r12/{stage}/{safe_id or 'unknown'}"


def _artifact_ref(kind: str, identifier: Any) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(identifier or "unknown")).strip("-")
    return f"{kind}-ref://openyggdrasil/r12/{safe_id or 'unknown'}"


def _append_stage(
    stage_refs: list[dict[str, str]],
    *,
    stage: str,
    identifier: Any,
    schema_version: str,
) -> None:
    stage_refs.append(
        {
            "stage": stage,
            "ref": _stage_ref(stage, identifier),
            "schema_version": schema_version,
        }
    )


def _base_result(
    *,
    status: str,
    stage_refs: list[dict[str, str]],
    blocked_stage: str | None,
    blocked_reason: str | None,
    reached_mailbox: bool,
    reason_codes: list[str],
    mailbox_message_ref: str | None = None,
    mailbox_delivery_ref: str | None = None,
    receipt_ref: str | None = None,
) -> dict[str, Any]:
    typed_unavailable = status == "typed_unavailable"
    return {
        "schema_version": SCHEMA_VERSION,
        "result_id": uuid.uuid4().hex,
        "runtime_owner": RUNTIME_OWNER,
        "top_level_entrypoint": "run_runtime_facade_chain",
        "facade_status": status,
        "transition_prep_only": True,
        "typed_refs_only": True,
        "safe_refs_only": True,
        "stage_refs": stage_refs,
        "ordered_stage_names": [stage["stage"] for stage in stage_refs],
        "reached_mailbox": reached_mailbox,
        "blocked_stage": blocked_stage,
        "blocked_reason": blocked_reason,
        "mailbox_message_ref": mailbox_message_ref,
        "mailbox_delivery_ref": mailbox_delivery_ref,
        "receipt_ref": receipt_ref,
        "remaining_typed_unavailable_stages": [blocked_stage] if typed_unavailable and blocked_stage else [],
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "credential_material_included": False,
        "private_profile_material_included": False,
        "raw_skill_body_included": False,
        "portable_local_path_included": False,
        "mock_live_relabeling_used": False,
        "reason_codes": reason_codes,
        **HARD_NON_CLAIMS,
        "created_at": utc_now_iso(),
    }


def _typed_unavailable(
    *,
    stage_refs: list[dict[str, str]],
    blocked_stage: str,
    reason_code: str,
) -> dict[str, Any]:
    return _base_result(
        status="typed_unavailable",
        stage_refs=stage_refs,
        blocked_stage=blocked_stage,
        blocked_reason=reason_code,
        reached_mailbox=False,
        reason_codes=["runtime_facade_chain_typed_unavailable", f"{blocked_stage}:{reason_code}"],
    )


def _bundle_digest(bundle: Mapping[str, Any]) -> str:
    encoded = repr(sorted((str(key), str(value)) for key, value in bundle.items()))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _validated_safe_refs(bundle: Mapping[str, Any]) -> dict[str, str] | str:
    unsafe_reason = _unsafe_bundle_reason(bundle)
    if unsafe_reason is not None:
        return unsafe_reason
    safe_refs: dict[str, str] = {}
    for field in (*REQUIRED_SAFE_REF_FIELDS, *OPTIONAL_SAFE_REF_FIELDS):
        value = bundle.get(field)
        if value is None:
            continue
        safe_value = _safe_ref(value)
        if safe_value is None:
            return f"unsafe_ref:{field}"
        safe_refs[field] = safe_value
    for field in REQUIRED_SAFE_REF_FIELDS:
        if field not in safe_refs:
            return f"missing_safe_ref:{field}"
    return safe_refs


def _safe_source_path_hint(source_ref: str) -> str:
    digest = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:16]
    return f"safe-ref-{digest}"


def _decision_surface_from_bundle(
    *,
    bundle: Mapping[str, Any],
    safe_refs: Mapping[str, str],
    provider_id: str,
    provider_session_id: str,
) -> dict[str, Any]:
    from attachments.provider_attachment import build_session_uid

    turn_start = int(bundle.get("turn_start") or 1)
    turn_end = int(bundle.get("turn_end") or turn_start)
    return {
        "schema_version": "decision_surface.v1",
        "provider_id": provider_id,
        "provider_profile": INTERNAL_PROVIDER_PROFILE,
        "provider_session_id": provider_session_id,
        "session_uid": build_session_uid(
            provider_id=provider_id,
            provider_profile=INTERNAL_PROVIDER_PROFILE,
            provider_session_id=provider_session_id,
        ),
        "turn_start": turn_start,
        "turn_end": turn_end,
        "surface_summary": str(
            bundle.get("surface_summary")
            or "Runtime facade chain-through accepted a safe-ref bundle."
        ).strip(),
        "trigger_reason": str(
            bundle.get("trigger_reason")
            or "R12 requires a top-level facade proof before live claims."
        ).strip(),
        "topic_hint": str(bundle.get("topic_hint") or "runtime-facade-chain-through").strip(),
        "source_ref": safe_refs["source_ref"],
        "conversation_excerpt": [
            {
                "role": "system",
                "text": "Safe-ref bundle admitted for transition-prep facade chain-through.",
            }
        ],
        "origin_locator": {"safe_ref_bundle": safe_refs["bundle_ref"]},
        "created_at": utc_now_iso(),
    }


def _structured_candidate_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_text": str(
            bundle.get("decision_text")
            or "openyggdrasil should prove top-level runtime facade chain-through."
        ).strip(),
        "rationale": str(
            bundle.get("rationale")
            or "Module-level PASS is insufficient without a product-entry facade trace."
        ).strip(),
        "alternatives_rejected": [
            "Treating isolated module PASS as product-entry chain-through proof"
        ],
        "stability_state": str(bundle.get("stability_state") or "stable").strip(),
        "topic_hint": str(bundle.get("topic_hint") or "runtime-facade-chain-through").strip(),
        "reason_labels": ["durable_decision", "architectural_boundary"],
        "confidence_score": float(bundle.get("confidence_score") or 0.9),
    }


def _build_mailbox_packet(
    *,
    provider_id: str,
    provider_session_id: str,
    admission_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any],
    postman_handoff: Mapping[str, Any],
    safe_refs: Mapping[str, str],
) -> dict[str, Any]:
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "map_topography",
        "kind": "packet",
        "producer": "runtime-facade-chain",
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "medium",
        "scope": {
            "provider_id": provider_id,
            "profile": INTERNAL_PROVIDER_PROFILE,
            "session_id": provider_session_id,
            "topic": str(admission_verdict["topic_key"]),
        },
        "payload": {
            "postman_handoff_ref": _artifact_ref("postman-handoff", postman_handoff["handoff_id"]),
            "map_topography_ref": _artifact_ref("map-topography", map_topography["topography_id"]),
            "source_refs": [{"kind": field, "ref": ref} for field, ref in safe_refs.items()],
            "facts": [
                str(map_topography["topic_title"]),
                str(map_topography["canonical_relative_path"]),
            ],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
            "canonical_write_status": "not_written",
            "canonical_authority": "not_this_contract",
            "vault_mutation_allowed": False,
        },
        "delivery": {
            "mode": "push_ready",
            "channel": "hermes-inbox",
            "profile_target": INTERNAL_PROVIDER_PROFILE,
            "session_target": provider_session_id,
        },
        "human_summary": "Runtime facade map-topography packet reached guarded mailbox handoff.",
    }
    validate_message(message)
    ensure_mailbox_message_accepted(message)
    return message


def run_runtime_facade_chain(
    *,
    safe_ref_bundle: Mapping[str, Any],
    vault_root: str | Path | None = None,
    mailbox_namespace: str | None = None,
) -> dict[str, Any]:
    """Run the R12 top-level transition-prep chain from safe refs to mailbox."""

    stage_refs: list[dict[str, str]] = []
    if not isinstance(safe_ref_bundle, Mapping):
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="safe_ref_bundle",
            reason_code="bundle_not_mapping",
        )

    bundle = dict(safe_ref_bundle)
    safe_ref_result = _validated_safe_refs(bundle)
    if isinstance(safe_ref_result, str):
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="safe_ref_bundle",
            reason_code=safe_ref_result,
        )
    safe_refs = safe_ref_result
    _append_stage(
        stage_refs,
        stage="safe_ref_bundle",
        identifier=_bundle_digest(bundle),
        schema_version="safe_ref_bundle.v1",
    )

    smoke = build_producer_consumer_smoke(smoke_request={**bundle, **safe_refs})
    if smoke["smoke_status"] != "smoke_built":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="producer_consumer_smoke",
            reason_code=str(smoke.get("unavailable_condition") or "smoke_unavailable"),
        )
    _append_stage(
        stage_refs,
        stage="producer_consumer_smoke",
        identifier=smoke["smoke_id"],
        schema_version="producer_consumer_smoke.v1",
    )

    provider_id = str(bundle.get("provider_id") or "openyggdrasil").strip()
    provider_session_id = str(
        bundle.get("provider_session_id") or f"runtime-facade-session-{_bundle_digest(bundle)}"
    ).strip()
    source_path_hint = _safe_source_path_hint(safe_refs["source_ref"])
    signal = build_session_structure_signal(
        provider_id=provider_id,
        provider_profile=INTERNAL_PROVIDER_PROFILE,
        provider_session_id=provider_session_id,
        turn_start=int(bundle.get("turn_start") or 1),
        turn_end=int(bundle.get("turn_end") or int(bundle.get("turn_start") or 1)),
        trigger_type=str(bundle.get("trigger_type") or "hard_trigger"),
        reason_labels=["durable_decision", "architectural_boundary"],
        surface_reason=str(
            bundle.get("surface_reason")
            or "Top-level facade chain-through proof is required."
        ).strip(),
        source_path_hint=source_path_hint,
        priority="immediate",
    )
    _append_stage(
        stage_refs,
        stage="session_structure_signal",
        identifier=signal["signal_id"],
        schema_version="session_structure_signal.v1",
    )

    session_verdict = evaluate_session_structure_signal(signal)
    if session_verdict["verdict"] != "accept":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="session_admission_gate",
            reason_code=str(session_verdict["verdict"]),
        )
    _append_stage(
        stage_refs,
        stage="session_admission_gate",
        identifier=session_verdict["verdict_id"],
        schema_version="session_admission_verdict.v1",
    )

    decision_surface = _decision_surface_from_bundle(
        bundle=bundle,
        safe_refs=safe_refs,
        provider_id=provider_id,
        provider_session_id=provider_session_id,
    )
    decision_candidate = finalize_provider_structured_decision_candidate(
        decision_surface=decision_surface,
        structured_output=_structured_candidate_from_bundle(bundle),
        structured_output_proof="structured_output_ref" in safe_refs,
    )
    if decision_candidate.get("status") == "typed_unavailable":
        reason_codes = decision_candidate.get("reason_codes") or ["structured_output_unavailable"]
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="decision_distiller",
            reason_code=str(reason_codes[-1]),
        )
    _append_stage(
        stage_refs,
        stage="decision_distiller",
        identifier=decision_candidate["candidate_id"],
        schema_version="decision_candidate.v1",
    )

    seedkeeper_segment = preserve_decision_segment(decision_candidate=decision_candidate)
    if seedkeeper_segment["preservation_status"] != "preserved":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="seedkeeper",
            reason_code=str(seedkeeper_segment["integrity_reason"]),
        )
    _append_stage(
        stage_refs,
        stage="seedkeeper",
        identifier=seedkeeper_segment["segment_id"],
        schema_version="seedkeeper_segment.v1",
    )

    evaluator_verdict = evaluate_decision_candidate(decision_candidate=decision_candidate)
    if evaluator_verdict["evaluator_status"] != "accept_for_amundsen":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="evaluator",
            reason_code=str(evaluator_verdict["evaluator_status"]),
        )
    _append_stage(
        stage_refs,
        stage="evaluator",
        identifier=evaluator_verdict["evaluator_verdict_id"],
        schema_version="evaluator_verdict.v1",
    )

    evaluator_handoff = build_evaluator_amundsen_handoff(
        decision_candidate=decision_candidate,
        evaluator_verdict=evaluator_verdict,
    )
    if evaluator_handoff["handoff_status"] != "ready_for_amundsen":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="evaluator_amundsen_handoff",
            reason_code=str(evaluator_handoff["blocked_reason"]),
        )
    _append_stage(
        stage_refs,
        stage="evaluator_amundsen_handoff",
        identifier=evaluator_handoff["handoff_id"],
        schema_version="evaluator_amundsen_handoff.v1",
    )

    active_vault_root = Path(vault_root) if vault_root is not None else DEFAULT_VAULT
    admission_verdict = admit_evaluator_handoff(
        evaluator_amundsen_handoff=evaluator_handoff,
        vault_root=active_vault_root,
    )
    _append_stage(
        stage_refs,
        stage="admission_amundsen",
        identifier=admission_verdict["verdict_id"],
        schema_version="admission_verdict.v1",
    )

    amundsen_handoff = build_amundsen_nursery_handoff(admission_verdict=admission_verdict)
    if amundsen_handoff["handoff_status"] != "ready_for_nursery":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="amundsen_nursery_handoff",
            reason_code=str(amundsen_handoff["blocked_reason"]),
        )
    _append_stage(
        stage_refs,
        stage="amundsen_nursery_handoff",
        identifier=amundsen_handoff["handoff_id"],
        schema_version="amundsen_nursery_handoff.v1",
    )

    nursery_input = build_nursery_composition_input(
        decision_candidate=decision_candidate,
        evaluator_verdict=evaluator_verdict,
        amundsen_nursery_handoff=amundsen_handoff,
        seedkeeper_segment=seedkeeper_segment,
    )
    if nursery_input["composition_status"] != "ready_for_seed_composition":
        return _typed_unavailable(
            stage_refs=stage_refs,
            blocked_stage="nursery_composition",
            reason_code=str(nursery_input["blocked_reason"]),
        )
    _append_stage(
        stage_refs,
        stage="nursery_composition",
        identifier=nursery_input["input_id"],
        schema_version="nursery_composition_input.v1",
    )

    engraved_seed = engrave_composed_decision_seed(nursery_composition_input=nursery_input)
    _append_stage(
        stage_refs,
        stage="nursery_seed",
        identifier=engraved_seed["seed_id"],
        schema_version="engraved_seed.v1",
    )

    planting_decision = plan_seed_planting(engraved_seed=engraved_seed)
    _append_stage(
        stage_refs,
        stage="gardener_planting",
        identifier=planting_decision["planting_id"],
        schema_version="planting_decision.v1",
    )

    gardener_route = build_gardener_routing_decision(
        engraved_seed=engraved_seed,
        planting_decision=planting_decision,
        vault_root=active_vault_root,
    )
    _append_stage(
        stage_refs,
        stage="gardener_routing",
        identifier=gardener_route["routing_id"],
        schema_version="gardener_routing_decision.v1",
    )

    cultivated = cultivate_decision_seed(
        engraved_seed=engraved_seed,
        vault_root=active_vault_root,
    )
    _append_stage(
        stage_refs,
        stage="cultivation",
        identifier=cultivated["cultivation_id"],
        schema_version="cultivated_decision.v1",
    )

    map_topography = update_map_topography(
        planting_decision=planting_decision,
        cultivated_decision=cultivated,
        amundsen_nursery_handoff=amundsen_handoff,
        gardener_routing_decision=gardener_route,
    )
    _append_stage(
        stage_refs,
        stage="map_maker",
        identifier=map_topography["topography_id"],
        schema_version="map_topography.v1",
    )

    source_refs = [{"kind": field, "ref": ref} for field, ref in safe_refs.items()]
    postman_handoff = build_postman_delivery_handoff(
        admission_verdict=admission_verdict,
        map_topography=map_topography,
        source_refs=source_refs,
        session_admission_verdict_id=str(session_verdict["verdict_id"]),
    )
    _append_stage(
        stage_refs,
        stage="postman_gateway",
        identifier=postman_handoff["handoff_id"],
        schema_version="postman_delivery_handoff.v1",
    )

    mailbox_message = _build_mailbox_packet(
        provider_id=provider_id,
        provider_session_id=provider_session_id,
        admission_verdict=admission_verdict,
        map_topography=map_topography,
        postman_handoff=postman_handoff,
        safe_refs=safe_refs,
    )
    namespace = mailbox_namespace or f"runtime-facade-r12-{_bundle_digest(bundle)}"
    submitted = submit_packet(mailbox_message, namespace=namespace)
    deliver_push_packet(submitted, namespace=namespace, consumer="runtime-facade-chain")
    _append_stage(
        stage_refs,
        stage="mailbox_store",
        identifier=submitted["message_id"],
        schema_version="mailbox.v1",
    )
    receipt_ref = _artifact_ref("runtime-facade-receipt", submitted["message_id"])
    _append_stage(
        stage_refs,
        stage="receipt",
        identifier=submitted["message_id"],
        schema_version="runtime_facade_receipt.v1",
    )

    return _base_result(
        status="completed",
        stage_refs=stage_refs,
        blocked_stage=None,
        blocked_reason=None,
        reached_mailbox=True,
        mailbox_message_ref=_artifact_ref("mailbox-message", submitted["message_id"]),
        mailbox_delivery_ref=_artifact_ref("mailbox-delivery", submitted["message_id"]),
        receipt_ref=receipt_ref,
        reason_codes=[
            "runtime_facade_chain_completed",
            "top_level_facade_entrypoint_called",
            "safe_refs_chain_through",
            "not_live_session_proof",
        ],
    )
