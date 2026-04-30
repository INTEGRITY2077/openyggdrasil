from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from delivery.consumer_receipt_ingress import (
    build_consumption_request,
    build_hermes_answer_receipt,
    build_recall_support_bundle_ref,
)
from harness_common import utc_now_iso
from pipeline.producer_consumer_smoke import build_producer_consumer_smoke
from reasoning.hermes_real_session_usage_probe import build_hermes_real_session_usage_probe
from reasoning.provider_skill_receipt_consumer import build_provider_skill_receipt_menu


SCHEMA_VERSION = "p0_e10_usage_ref_materialization.v1"
RUNTIME_OWNER = "runtime/pipeline/p0_e10_usage_ref_materializer.py"
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(r"(^[A-Za-z]:|\\\\|/Users/|/home/|/tmp/|file://)", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UNSAFE_REF_FRAGMENTS = (
    ".skill.md",
    "credential",
    "profile",
    "prompt",
    "transcript",
)
REQUIRED_P0_E8_REFS = (
    "provider_skill_invocation_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "typed_result_ref",
)
OUTPUT_REF_FIELDS = (
    "provider_gateway_evidence_ref",
    "provider_skill_invocation_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_usage_evidence_ref",
    "producer_request_ref",
    "producer_receipt_ref",
    "support_bundle_ref",
    "consumer_menu_ref",
    "consumer_usage_ref",
    "typed_result_ref",
)
NO_OVERCLAIM_FLAGS = {
    "r9_r10_live_pass_claimed": False,
    "r9_real_session_pass_claimed": False,
    "r10_live_pass_claimed": False,
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "full_product_readiness_claimed": False,
}


def _is_safe_ref(value: Any) -> bool:
    text = str(value or "").strip()
    if not SAFE_REF_RE.match(text):
        return False
    if LOCAL_PATH_RE.search(text):
        return False
    lowered = text.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _safe_ref(source: Mapping[str, Any], field: str) -> str | None:
    value = source.get(field)
    if value is None:
        return None
    text = str(value).strip()
    return text if _is_safe_ref(text) else None


def _safe_identifier(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if IDENTIFIER_RE.match(text) else fallback


def _stable_token(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(values), ensure_ascii=True, sort_keys=True, default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()[:20]


def _unique_refs(values: Sequence[str | None]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            refs.append(text)
            seen.add(text)
    return refs


def _typed_unavailable(
    *,
    condition: str,
    reason_codes: Sequence[str],
    safe_refs: Mapping[str, str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    refs = dict(safe_refs or {})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "materialization_status": "typed_unavailable",
        "unavailable_condition": condition,
        "reject_condition": None,
        "reason_codes": list(reason_codes),
        "runtime_owner": RUNTIME_OWNER,
        "typed_refs_only": True,
        "ptc_callable": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        **NO_OVERCLAIM_FLAGS,
        "created_at": created_at or utc_now_iso(),
    }
    for field in OUTPUT_REF_FIELDS:
        payload[field] = refs.get(field)
    payload.update(
        {
            "typed_task_id": refs.get("typed_task_id"),
            "producer_consumer_smoke": None,
            "provider_skill_receipt_menu": None,
            "consumption_request": None,
            "recall_support_bundle": None,
            "hermes_answer_receipt": None,
            "r9_usage_probe": None,
            "safe_portable_refs": _unique_refs([refs.get(field) for field in OUTPUT_REF_FIELDS]),
        }
    )
    validate_p0_e10_usage_ref_materialization(payload)
    return payload


def validate_p0_e10_usage_ref_materialization(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid P0-E10 usage ref materialization schema_version")
    if payload.get("runtime_owner") != RUNTIME_OWNER:
        raise ValueError("invalid P0-E10 usage ref materialization runtime owner")
    if payload.get("materialization_status") not in {"pass_candidate", "typed_unavailable"}:
        raise ValueError("invalid P0-E10 usage ref materialization status")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("P0-E10 materialization must use typed refs only")
    if payload.get("ptc_callable") is not True:
        raise ValueError("P0-E10 materialization must remain PTC-callable")
    if payload.get("provider_gateway_called") is not False:
        raise ValueError("P0-E10 materialization must not call a provider gateway")
    if payload.get("provider_state_read") is not False:
        raise ValueError("P0-E10 materialization must not read provider state")

    for flag in [
        "raw_transcript_included",
        "raw_provider_material_included",
        "skill_body_included",
        "provider_credential_profile_included",
        "portable_local_path_included",
        *NO_OVERCLAIM_FLAGS.keys(),
    ]:
        if payload.get(flag) is not False:
            raise ValueError(f"unsafe or overclaiming P0-E10 flag: {flag}")

    for field in OUTPUT_REF_FIELDS:
        value = payload.get(field)
        if value is not None and not _is_safe_ref(value):
            raise ValueError(f"{field} must be a safe portable ref")
    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(ref):
            raise ValueError("safe_portable_refs must be safe portable refs")
    for reason_code in payload.get("reason_codes") or []:
        if not IDENTIFIER_RE.match(str(reason_code)):
            raise ValueError("reason_codes must be safe identifiers")

    if payload.get("materialization_status") == "typed_unavailable":
        if not payload.get("unavailable_condition"):
            raise ValueError("typed_unavailable requires unavailable_condition")
        return

    for field in (*OUTPUT_REF_FIELDS, "typed_task_id"):
        if not payload.get(field):
            raise ValueError(f"pass_candidate requires {field}")
    if payload.get("unavailable_condition") is not None:
        raise ValueError("pass_candidate must not include unavailable_condition")

    smoke = payload.get("producer_consumer_smoke")
    menu = payload.get("provider_skill_receipt_menu")
    answer = payload.get("hermes_answer_receipt")
    probe = payload.get("r9_usage_probe")
    if not isinstance(smoke, Mapping) or smoke.get("smoke_status") != "smoke_built":
        raise ValueError("pass_candidate requires built producer_consumer_smoke")
    if not isinstance(menu, Mapping) or menu.get("consumption_status") != "menu_built":
        raise ValueError("pass_candidate requires built provider_skill_receipt_menu")
    if not isinstance(answer, Mapping) or answer.get("unavailable") is not False:
        raise ValueError("pass_candidate requires consumer usage answer receipt")
    if not isinstance(probe, Mapping) or probe.get("proof_package_status") != "pass_candidate":
        raise ValueError("pass_candidate requires R9 probe pass_candidate classification")
    if payload.get("producer_usage_evidence_ref") != smoke.get("smoke_ref"):
        raise ValueError("producer_usage_evidence_ref must be the smoke runtime output ref")
    if payload.get("consumer_menu_ref") != menu.get("menu_ref"):
        raise ValueError("consumer_menu_ref must be the menu runtime output ref")
    if payload.get("consumer_usage_ref") != answer.get("answer_receipt_ref"):
        raise ValueError("consumer_usage_ref must be the answer receipt runtime output ref")


def build_p0_e10_usage_ref_materialization(
    *,
    p0_e8_healthy_chain: Mapping[str, Any],
    worker4_verification_ref: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Materialize bounded R9/R10 producer/consumer refs from verified P0-E8 refs.

    This adapter only composes existing typed runtime owners. It does not call
    Hermes, read provider state, dereference local artifacts, or claim readiness.
    """

    if not isinstance(p0_e8_healthy_chain, Mapping):
        return _typed_unavailable(
            condition="unsupported_p0_e8_input_shape",
            reason_codes=["unsupported_p0_e8_input_shape"],
            created_at=created_at,
        )

    chain = dict(p0_e8_healthy_chain)
    safe_refs = {
        field: ref
        for field in REQUIRED_P0_E8_REFS
        if (ref := _safe_ref(chain, field)) is not None
    }
    unsafe_fields = [
        field for field in REQUIRED_P0_E8_REFS if chain.get(field) and field not in safe_refs
    ]
    if unsafe_fields:
        return _typed_unavailable(
            condition="unsafe_p0_e8_ref",
            reason_codes=[f"unsafe_ref:{field}" for field in unsafe_fields],
            safe_refs=safe_refs,
            created_at=created_at,
        )

    missing_fields = [field for field in REQUIRED_P0_E8_REFS if field not in safe_refs]
    if missing_fields:
        return _typed_unavailable(
            condition="missing_p0_e8_required_ref",
            reason_codes=[f"missing_ref:{field}" for field in missing_fields],
            safe_refs=safe_refs,
            created_at=created_at,
        )

    if chain.get("typed_unavailable_ref") not in (None, ""):
        return _typed_unavailable(
            condition="p0_e8_typed_result_required",
            reason_codes=["typed_unavailable_ref_must_be_absent"],
            safe_refs=safe_refs,
            created_at=created_at,
        )
    if chain.get("unsafe_flags") is not False:
        return _typed_unavailable(
            condition="p0_e8_unsafe_flags_not_false",
            reason_codes=["unsafe_flags_false_required"],
            safe_refs=safe_refs,
            created_at=created_at,
        )
    if not _is_safe_ref(worker4_verification_ref):
        return _typed_unavailable(
            condition="unsafe_worker4_verification_ref",
            reason_codes=["unsafe_worker4_verification_ref"],
            safe_refs=safe_refs,
            created_at=created_at,
        )

    typed_task_id = _safe_identifier(
        chain.get("typed_task_id"),
        "p0-e10-usage-ref-materialization",
    )
    if typed_task_id != str(chain.get("typed_task_id") or ""):
        return _typed_unavailable(
            condition="unsafe_typed_task_id",
            reason_codes=["typed_task_id_safe_identifier_required"],
            safe_refs=safe_refs,
            created_at=created_at,
        )

    provider_gateway_evidence_ref = str(
        chain.get("provider_gateway_evidence_ref") or safe_refs["provider_skill_invocation_ref"]
    )
    if not _is_safe_ref(provider_gateway_evidence_ref):
        return _typed_unavailable(
            condition="unsafe_provider_gateway_evidence_ref",
            reason_codes=["unsafe_provider_gateway_evidence_ref"],
            safe_refs=safe_refs,
            created_at=created_at,
        )

    token = _stable_token(
        {
            "typed_task_id": typed_task_id,
            "typed_result_ref": safe_refs["typed_result_ref"],
            "provider_skill_invocation_ref": safe_refs["provider_skill_invocation_ref"],
            "worker4_verification_ref": worker4_verification_ref,
        }
    )
    base = f"openyggdrasil/p0-e10/{token}"
    producer_request_ref = f"production-request-ref://{base}"
    producer_receipt_ref = f"production-receipt-ref://{base}"
    support_bundle_ref = f"support-bundle-ref://{base}"
    consumer_request_ref = f"consumption-request-ref://{base}"
    consumer_usage_ref = f"consumer-usage-ref://{base}"
    approved_routing_fact_ref = f"approved-routing-fact-ref://{base}"
    ptc_session_ref = f"ptc-session-ref://{base}"
    ptc_egress_payload_ref = f"ptc-egress-payload-ref://{base}"

    try:
        menu = build_provider_skill_receipt_menu(
            receipt_consumer_request={
                "consumer_request_id": f"p0-e10-consumer:{token}",
                "input_schema_versions": [
                    "p0_e6_typed_handoff_tollgate.v1",
                    "provider_skill_receipt_consumer.v1",
                ],
                "production_request_ref": producer_request_ref,
                "production_receipt_ref": producer_receipt_ref,
                "support_bundle_ref": support_bundle_ref,
                "receipt_menu_items": [
                    {
                        "item_ref": producer_request_ref,
                        "item_kind": "production_request",
                        "label": "P0-E10 producer request from verified P0-E8 typed result",
                        "source_ref": safe_refs["typed_result_ref"],
                        "reason_code": "p0_e8_typed_result_basis",
                    },
                    {
                        "item_ref": producer_receipt_ref,
                        "item_kind": "production_receipt",
                        "label": "P0-E10 producer receipt for bounded usage package",
                        "source_ref": producer_request_ref,
                        "reason_code": "producer_receipt_materialized",
                    },
                    {
                        "item_ref": support_bundle_ref,
                        "item_kind": "support_bundle",
                        "label": "P0-E10 support bundle for consumer usage",
                        "source_ref": producer_receipt_ref,
                        "reason_code": "support_bundle_materialized",
                    },
                ],
            }
        )
        smoke = build_producer_consumer_smoke(
            smoke_request={
                "smoke_request_id": f"p0-e10-smoke:{token}",
                "producer_request_ref": producer_request_ref,
                "production_receipt_ref": producer_receipt_ref,
                "support_bundle_ref": support_bundle_ref,
                "consumer_menu_ref": menu["menu_ref"],
                "provider_receipt_consumer_ref": f"provider-receipt-consumer-ref://{base}",
            }
        )
        consumption_request = build_consumption_request(
            {
                "worker4_verdict": "PASS",
                "worker4_verdict_ref": worker4_verification_ref,
                "production_receipt_ref": producer_receipt_ref,
                "approved_routing_fact_ref": approved_routing_fact_ref,
                "ptc_session_ref": ptc_session_ref,
                "ptc_egress_payload_ref": ptc_egress_payload_ref,
                "evidence_refs": [
                    {
                        "evidence_id": "p0-e8-typed-result",
                        "ref": safe_refs["typed_result_ref"],
                        "evidence_kind": "route_decision",
                        "resolution_status": "resolved",
                        "evidence_status": "current",
                        "pointer_accounting_key": "p0_e8_typed_result_ref",
                    },
                    {
                        "evidence_id": "p0-e8-provider-skill-invocation",
                        "ref": safe_refs["provider_skill_invocation_ref"],
                        "evidence_kind": "route_decision",
                        "resolution_status": "resolved",
                        "evidence_status": "current",
                        "pointer_accounting_key": "provider_skill_invocation_ref",
                    },
                ],
            },
            created_at=created_at,
            consumption_request_ref=consumer_request_ref,
            recall_support_bundle_ref=support_bundle_ref,
            requested_answer_category="support_bundle_summary",
        )
        recall_support_bundle = build_recall_support_bundle_ref(
            consumption_request,
            selected_memory_refs=[
                {
                    "ref": support_bundle_ref,
                    "role": "support_bundle_source",
                    "reason_code": "p0_e10_materialized_support_bundle",
                }
            ],
            created_at=created_at,
        )
        answer = build_hermes_answer_receipt(
            consumption_request,
            recall_support_bundle,
            answer_receipt_ref=consumer_usage_ref,
            answer_summary=(
                "Hermes used the P0-E10 materialized producer receipt and support bundle refs."
            ),
            created_at=created_at,
        )
        r9_probe = build_hermes_real_session_usage_probe(
            proof_package={
                "session_probe_id": f"p0-e10-session:{token}",
                "typed_task_id": typed_task_id,
                "input_schema_versions": [
                    SCHEMA_VERSION,
                    "producer_consumer_smoke.v1",
                    "provider_skill_receipt_consumer.v1",
                    "consumption_request.v1",
                    "recall_support_bundle_ref.v1",
                    "hermes_answer_receipt.v1",
                    "hermes_real_session_usage_probe.v1",
                ],
                "provider_gateway_evidence_ref": provider_gateway_evidence_ref,
                "before_main_context_window_ref": safe_refs["before_main_context_window_ref"],
                "after_main_context_window_ref": safe_refs["after_main_context_window_ref"],
                "producer_usage_evidence_ref": smoke["smoke_ref"],
                "producer_request_ref": producer_request_ref,
                "producer_receipt_ref": producer_receipt_ref,
                "support_bundle_ref": support_bundle_ref,
                "consumer_menu_ref": menu["menu_ref"],
                "consumer_usage_ref": answer["answer_receipt_ref"],
                "typed_result_ref": safe_refs["typed_result_ref"],
            }
        )
    except ValueError as exc:
        return _typed_unavailable(
            condition="runtime_owner_materialization_blocked",
            reason_codes=["runtime_owner_materialization_blocked", _safe_identifier(str(exc), "runtime_error")],
            safe_refs={
                **safe_refs,
                "provider_gateway_evidence_ref": provider_gateway_evidence_ref,
                "typed_task_id": typed_task_id,
            },
            created_at=created_at,
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "materialization_status": "pass_candidate",
        "unavailable_condition": None,
        "reject_condition": None,
        "reason_codes": [
            "p0_e10_usage_refs_materialized",
            "existing_typed_runtime_owners_replayed",
            "worker4_verified_p0_e8_basis",
            "no_overclaim_flags",
        ],
        "runtime_owner": RUNTIME_OWNER,
        "typed_refs_only": True,
        "ptc_callable": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "typed_task_id": typed_task_id,
        "provider_gateway_evidence_ref": provider_gateway_evidence_ref,
        "provider_skill_invocation_ref": safe_refs["provider_skill_invocation_ref"],
        "before_main_context_window_ref": safe_refs["before_main_context_window_ref"],
        "after_main_context_window_ref": safe_refs["after_main_context_window_ref"],
        "producer_usage_evidence_ref": smoke["smoke_ref"],
        "producer_request_ref": producer_request_ref,
        "producer_receipt_ref": producer_receipt_ref,
        "support_bundle_ref": support_bundle_ref,
        "consumer_menu_ref": menu["menu_ref"],
        "consumer_usage_ref": answer["answer_receipt_ref"],
        "typed_result_ref": safe_refs["typed_result_ref"],
        "producer_consumer_smoke": smoke,
        "provider_skill_receipt_menu": menu,
        "consumption_request": consumption_request,
        "recall_support_bundle": recall_support_bundle,
        "hermes_answer_receipt": answer,
        "r9_usage_probe": r9_probe,
        "safe_portable_refs": _unique_refs(
            [
                provider_gateway_evidence_ref,
                safe_refs["provider_skill_invocation_ref"],
                safe_refs["before_main_context_window_ref"],
                safe_refs["after_main_context_window_ref"],
                smoke["smoke_ref"],
                producer_request_ref,
                producer_receipt_ref,
                support_bundle_ref,
                menu["menu_ref"],
                answer["answer_receipt_ref"],
                safe_refs["typed_result_ref"],
                *smoke.get("safe_portable_refs", []),
                *menu.get("safe_portable_refs", []),
                *r9_probe.get("safe_portable_refs", []),
            ]
        ),
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        **NO_OVERCLAIM_FLAGS,
        "created_at": created_at or utc_now_iso(),
    }
    validate_p0_e10_usage_ref_materialization(payload)
    return payload


__all__ = [
    "build_p0_e10_usage_ref_materialization",
    "validate_p0_e10_usage_ref_materialization",
]
