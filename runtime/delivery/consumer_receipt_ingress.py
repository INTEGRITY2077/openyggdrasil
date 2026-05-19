from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

CONSUMPTION_REQUEST_SCHEMA = "consumption_request.v1.schema.json"
RECALL_SUPPORT_BUNDLE_REF_SCHEMA = "recall_support_bundle_ref.v1.schema.json"
HERMES_ANSWER_RECEIPT_SCHEMA = "hermes_answer_receipt.v1.schema.json"
TYPED_UNAVAILABLE_SCHEMA = "typed_unavailable.v1.schema.json"

SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s]+$")
FORBIDDEN_REF_TOKENS = (
    "file://",
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    ".skill.md",
    "transcript.txt",
)
FORBIDDEN_TEXT_TOKENS = (
    "---\nname:",
    "```",
    ".skill.md",
    "<instructions>",
    "<INSTRUCTIONS>",
    "raw provider transcript",
    "transcript.txt",
)
NO_OVERCLAIM_BOUNDARY = {
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "readiness_91_percent_claimed": False,
}
DEFAULT_CONSUMPTION_REQUEST_REF = "consumption-request-ref://openyggdrasil/consumer-ingress/001"
DEFAULT_RECALL_SUPPORT_BUNDLE_REF = (
    "recall-support-bundle-ref://openyggdrasil/consumer-ingress/support-001"
)
DEFAULT_ANSWER_RECEIPT_REF = "hermes-answer-receipt-ref://openyggdrasil/consumer-ingress/answer-001"
DEFAULT_UNAVAILABLE_REF = "typed-unavailable-ref://openyggdrasil/consumer-ingress/unavailable-001"


@lru_cache(maxsize=4)
def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


def _validate(filename: str, payload: Mapping[str, Any]) -> None:
    jsonschema.Draft202012Validator.check_schema(_load_schema(filename))
    jsonschema.Draft202012Validator(
        _load_schema(filename),
        format_checker=jsonschema.FormatChecker(),
    ).validate(dict(payload))


def validate_consumption_request(payload: Mapping[str, Any]) -> None:
    _validate(CONSUMPTION_REQUEST_SCHEMA, payload)


def validate_recall_support_bundle_ref(payload: Mapping[str, Any]) -> None:
    _validate(RECALL_SUPPORT_BUNDLE_REF_SCHEMA, payload)


def validate_hermes_answer_receipt(payload: Mapping[str, Any]) -> None:
    _validate(HERMES_ANSWER_RECEIPT_SCHEMA, payload)


def validate_typed_unavailable(payload: Mapping[str, Any]) -> None:
    _validate(TYPED_UNAVAILABLE_SCHEMA, payload)


def _token(value: Any, *, length: int = 16) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _safe_ref(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower().replace("\\", "/")
    if not text or not SAFE_REF_RE.match(text):
        raise ValueError(f"{field_name} must be a safe ref")
    if any(token.replace("\\", "/").lower() in lowered for token in FORBIDDEN_REF_TOKENS):
        raise ValueError(f"{field_name} contains unsafe material")
    return text


def _provider_safe_text(value: Any, *, field_name: str, fallback: str) -> str:
    text = " ".join(str(value or fallback).strip().split())
    lowered = text.lower().replace("\\", "/")
    if not text:
        raise ValueError(f"{field_name} is required")
    if any(token.lower().replace("\\", "/") in lowered for token in FORBIDDEN_TEXT_TOKENS):
        raise ValueError(f"{field_name} contains unsafe material")
    return text[:600]


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _first_ref(source: Mapping[str, Any], keys: Sequence[str], fallback: str | None = None) -> str:
    for key in keys:
        value = source.get(key)
        if value:
            return _safe_ref(value, field_name=key)
    if fallback is None:
        raise ValueError(f"missing required ref from {keys}")
    return _safe_ref(fallback, field_name=str(keys[0]))


def _evidence_ref(
    evidence_id: str,
    ref: str,
    evidence_kind: str,
    *,
    pointer_accounting_key: str | None = None,
) -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "ref": _safe_ref(ref, field_name=f"{evidence_id}.ref"),
        "evidence_kind": evidence_kind,
        "resolution_status": "resolved",
        "evidence_status": "current",
        "pointer_accounting_key": pointer_accounting_key or f"{evidence_kind}_ref",
    }


def _normalize_evidence_refs(
    producer_receipt: Mapping[str, Any],
    *,
    worker4_verdict_ref: str,
    production_receipt_ref: str,
    approved_routing_fact_ref: str,
    ptc_egress_payload_ref: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, raw in enumerate(producer_receipt.get("evidence_refs") or []):
        if not isinstance(raw, Mapping):
            continue
        ref = _safe_ref(raw.get("ref"), field_name=f"evidence_refs[{index}].ref")
        resolution_status = str(raw.get("resolution_status") or "resolved")
        evidence_status = str(raw.get("evidence_status") or "current")
        evidence_kind = str(raw.get("evidence_kind") or "")
        if resolution_status != "resolved":
            raise ValueError("unresolved evidence refs cannot enter consumer ingress")
        if evidence_status != "current":
            raise ValueError("stale or decoy evidence refs cannot enter consumer ingress")
        if evidence_kind in {"graphify_hint", "decoy"}:
            raise ValueError("graphify or decoy evidence cannot enter consumer ingress")
        rows.append(
            _evidence_ref(
                str(raw.get("evidence_id") or f"evidence-{index + 1}"),
                ref,
                evidence_kind or "route_decision",
                pointer_accounting_key=str(
                    raw.get("pointer_accounting_key") or f"{evidence_kind or 'route_decision'}_ref"
                ),
            )
        )

    required = [
        _evidence_ref(
            "worker4-verification-pass-001",
            worker4_verdict_ref,
            "worker4_verification",
        ),
        _evidence_ref("production-receipt-001", production_receipt_ref, "production_receipt"),
        _evidence_ref(
            "approved-routing-fact-001",
            approved_routing_fact_ref,
            "approved_routing_fact",
        ),
        _evidence_ref("ptc-egress-payload-001", ptc_egress_payload_ref, "ptc_egress_payload"),
    ]
    by_key = {(row["evidence_kind"], row["ref"]): row for row in rows}
    for row in required:
        by_key.setdefault((row["evidence_kind"], row["ref"]), row)
    return list(by_key.values())


def _reject_raw_flags(source: Mapping[str, Any]) -> None:
    for key in (
        "raw_provider_material_included",
        "skill_body_included",
        "portable_local_path_included",
        "fabricated_answer",
    ):
        if source.get(key) is True:
            raise ValueError(f"{key} is forbidden")


def _typed_unavailable_ref(ref: str, reason_code: str, rejection_kind: str) -> dict[str, str]:
    return {
        "ref": _safe_ref(ref, field_name="missing_or_rejected_ref.ref"),
        "reason_code": reason_code,
        "rejection_kind": rejection_kind,
    }


def build_typed_unavailable(
    *,
    reason_code: str,
    blocked_stage: str,
    missing_or_rejected_refs: Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
    unavailable_ref: str = DEFAULT_UNAVAILABLE_REF,
) -> dict[str, Any]:
    rows = []
    for raw in missing_or_rejected_refs or ():
        rows.append(
            _typed_unavailable_ref(
                str(raw.get("ref") or DEFAULT_UNAVAILABLE_REF),
                str(raw.get("reason_code") or reason_code),
                str(raw.get("rejection_kind") or "missing"),
            )
        )
    payload = {
        "schema_version": "typed_unavailable.v1",
        "unavailable_ref": _safe_ref(unavailable_ref, field_name="unavailable_ref"),
        "created_at": created_at or utc_now_iso(),
        "reason_code": reason_code,
        "blocked_stage": blocked_stage,
        "missing_or_rejected_refs": rows,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "portable_local_path_included": False,
        "fabricated_answer": False,
        "no_overclaim_boundary": dict(NO_OVERCLAIM_BOUNDARY),
    }
    validate_typed_unavailable(payload)
    return payload


def build_consumption_request(
    producer_receipt: Mapping[str, Any],
    *,
    created_at: str | None = None,
    consumption_request_ref: str = DEFAULT_CONSUMPTION_REQUEST_REF,
    recall_support_bundle_ref: str = DEFAULT_RECALL_SUPPORT_BUNDLE_REF,
    requested_answer_category: str = "memory_recall",
) -> dict[str, Any]:
    receipt = dict(producer_receipt)
    _reject_raw_flags(receipt)
    worker4_verdict = str(receipt.get("worker4_verdict") or receipt.get("verdict") or "")
    if worker4_verdict != "PASS":
        raise ValueError("Worker 4 PASS is required before consumer ingress")
    worker4_verdict_ref = _first_ref(
        receipt,
        ("worker4_verdict_ref", "worker4_verification_ref", "verification_ref"),
        "worker4-verification-ref://openyggdrasil/producer-first-poc/worker4/pass-001",
    )
    production_receipt_ref = _first_ref(
        receipt,
        ("production_receipt_ref", "receipt_ref", "source_production_receipt_ref"),
        "production-receipt-ref://openyggdrasil/producer-first-poc/worker2/receipt-001",
    )
    approved_routing_fact_ref = _first_ref(
        receipt,
        ("approved_routing_fact_ref",),
        "approved-routing-fact-ref://openyggdrasil/producer-first-poc/worker2/route-001",
    )
    ptc_session_ref = _first_ref(
        receipt,
        ("ptc_code_execution_session_ref", "ptc_session_ref"),
        "ptc-session-ref://openyggdrasil/producer-first-poc/worker3/session-001",
    )
    ptc_egress_payload_ref = _first_ref(
        receipt,
        ("ptc_egress_payload_ref", "ptc_egress_ref"),
        "ptc-egress-payload-ref://openyggdrasil/producer-first-poc/worker3/egress-001",
    )
    evidence_refs = _normalize_evidence_refs(
        receipt,
        worker4_verdict_ref=worker4_verdict_ref,
        production_receipt_ref=production_receipt_ref,
        approved_routing_fact_ref=approved_routing_fact_ref,
        ptc_egress_payload_ref=ptc_egress_payload_ref,
    )
    payload = {
        "schema_version": "consumption_request.v1",
        "consumption_request_ref": _safe_ref(
            consumption_request_ref,
            field_name="consumption_request_ref",
        ),
        "created_at": created_at or utc_now_iso(),
        "worker4_verdict_ref": worker4_verdict_ref,
        "worker4_verdict": "PASS",
        "source_production_receipt_ref": production_receipt_ref,
        "approved_routing_fact_ref": approved_routing_fact_ref,
        "ptc_code_execution_session_ref": ptc_session_ref,
        "recall_support_bundle_ref": _safe_ref(
            recall_support_bundle_ref,
            field_name="recall_support_bundle_ref",
        ),
        "requested_answer_category": requested_answer_category,
        "evidence_refs": evidence_refs,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "portable_local_path_included": False,
        "fabricated_answer": False,
        "no_overclaim_boundary": dict(NO_OVERCLAIM_BOUNDARY),
        "reason_codes": [
            "worker4_pass_required",
            "producer_receipt_verified",
            "typed_refs_only",
        ],
    }
    validate_consumption_request(payload)
    return payload


def build_recall_support_bundle_ref(
    consumption_request: Mapping[str, Any],
    *,
    selected_memory_refs: Sequence[Mapping[str, Any]] | None = None,
    rejected_memory_refs: Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    request = dict(consumption_request)
    validate_consumption_request(request)
    selected = [
        {
            "ref": _safe_ref(
                raw.get("ref"),
                field_name="selected_memory_refs.ref",
            ),
            "role": str(raw.get("role") or "support_bundle_source"),
            "reason_code": str(raw.get("reason_code") or "worker4_verified_current_receipt"),
            "memory_status": "current",
        }
        for raw in (
            selected_memory_refs
            or [
                {
                    "ref": "support-bundle-ref://openyggdrasil/producer-first-poc/worker2/support-001",
                    "role": "support_bundle_source",
                    "reason_code": "worker4_verified_current_receipt",
                }
            ]
        )
    ]
    rejected = [
        {
            "ref": _safe_ref(raw.get("ref"), field_name="rejected_memory_refs.ref"),
            "role": str(raw.get("role") or "support_bundle_source"),
            "reason_code": str(raw.get("reason_code") or "stale_ref_rejected"),
            "memory_status": str(raw.get("memory_status") or "stale"),
            "rejected": True,
        }
        for raw in (
            rejected_memory_refs
            or [
                {
                    "ref": "graphify-ref://openyggdrasil/consumer-ingress/decoy-001",
                    "role": "graphify_hint",
                    "reason_code": "graphify_hint_not_sot",
                    "memory_status": "graphify_non_sot",
                },
                {
                    "ref": "support-bundle-ref://openyggdrasil/consumer-ingress/stale-001",
                    "role": "support_bundle_source",
                    "reason_code": "stale_ref_rejected",
                    "memory_status": "stale",
                },
            ]
        )
    ]
    payload = {
        "schema_version": "recall_support_bundle_ref.v1",
        "support_bundle_ref": request["recall_support_bundle_ref"],
        "created_at": created_at or str(request["created_at"]),
        "source_evidence_refs": list(request["evidence_refs"]),
        "selected_memory_refs": selected,
        "rejected_memory_refs": rejected,
        "stale_refs_rejected": True,
        "decoy_refs_rejected": True,
        "graphify_refs_non_sot": True,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "portable_local_path_included": False,
        "no_overclaim_boundary": dict(NO_OVERCLAIM_BOUNDARY),
        "reason_codes": [
            "stale_refs_rejected",
            "decoy_refs_rejected",
            "graphify_non_sot",
        ],
    }
    validate_recall_support_bundle_ref(payload)
    return payload


def build_hermes_answer_receipt(
    consumption_request: Mapping[str, Any],
    recall_support_bundle_ref: Mapping[str, Any],
    *,
    answer_receipt_ref: str = DEFAULT_ANSWER_RECEIPT_REF,
    answer_summary: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    request = dict(consumption_request)
    support = dict(recall_support_bundle_ref)
    validate_consumption_request(request)
    validate_recall_support_bundle_ref(support)
    summary = _provider_safe_text(
        answer_summary,
        field_name="answer_summary",
        fallback="Hermes used the verified producer receipt and current support bundle refs.",
    )
    payload = {
        "schema_version": "hermes_answer_receipt.v1",
        "answer_receipt_ref": _safe_ref(answer_receipt_ref, field_name="answer_receipt_ref"),
        "created_at": created_at or str(request["created_at"]),
        "answer_category": request["requested_answer_category"],
        "consumption_request_ref": request["consumption_request_ref"],
        "recall_support_bundle_ref": support["support_bundle_ref"],
        "evidence_refs": list(request["evidence_refs"]),
        "answer_summary": summary,
        "unavailable": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "portable_local_path_included": False,
        "no_overclaim_boundary": dict(NO_OVERCLAIM_BOUNDARY),
        "reason_codes": [
            "evidence_backed_answer",
            "typed_refs_only",
            "no_overclaim_boundary_preserved",
        ],
    }
    validate_hermes_answer_receipt(payload)
    return payload


def consume_verified_producer_receipt(
    producer_receipt: Mapping[str, Any],
    *,
    created_at: str | None = None,
    requested_answer_category: str = "memory_recall",
    answer_summary: str | None = None,
) -> dict[str, Any]:
    """Build consumer ingress payloads from a Worker-4-verified producer receipt.

    The adapter returns `typed_unavailable.v1` instead of fabricating memory when
    the producer package is not verified or contains stale/unsafe refs.
    """

    try:
        request = build_consumption_request(
            producer_receipt,
            created_at=created_at,
            requested_answer_category=requested_answer_category,
        )
        support = build_recall_support_bundle_ref(request, created_at=created_at)
        answer = build_hermes_answer_receipt(
            request,
            support,
            answer_summary=answer_summary,
            created_at=created_at,
        )
    except ValueError as exc:
        reason_code = "consumer_ingress_blocked"
        blocked_stage = "evidence_resolution"
        rejection_kind = "unresolved"
        text = str(exc)
        if "Worker 4 PASS" in text:
            reason_code = "missing_worker4_pass"
            blocked_stage = "worker4_gate"
            rejection_kind = "missing"
        elif "stale" in text or "decoy" in text:
            reason_code = "stale_or_decoy_evidence"
            rejection_kind = "stale"
        elif "raw_provider" in text:
            reason_code = "raw_provider_material_detected"
            blocked_stage = "raw_material_scan"
            rejection_kind = "unsafe_material"
        elif "fabricated" in text:
            reason_code = "consumer_ingress_blocked"
            blocked_stage = "answer_receipt"
            rejection_kind = "unsafe_material"
        elif "unsafe" in text:
            reason_code = "unsafe_local_path_detected"
            blocked_stage = "raw_material_scan"
            rejection_kind = "unsafe_material"
        elif "skill" in text:
            reason_code = "raw_skill_body_detected"
            blocked_stage = "raw_material_scan"
            rejection_kind = "unsafe_material"
        return {
            "schema_version": "consumer_receipt_ingress_result.v1",
            "ingress_status": "typed_unavailable",
            "typed_unavailable": build_typed_unavailable(
                reason_code=reason_code,
                blocked_stage=blocked_stage,
                missing_or_rejected_refs=[
                    {
                        "ref": DEFAULT_UNAVAILABLE_REF,
                        "reason_code": reason_code,
                        "rejection_kind": rejection_kind,
                    }
                ],
                created_at=created_at,
            ),
            "reason_codes": [reason_code],
        }
    return {
        "schema_version": "consumer_receipt_ingress_result.v1",
        "ingress_status": "completed",
        "consumption_request": request,
        "recall_support_bundle_ref": support,
        "hermes_answer_receipt": answer,
        "reason_codes": [
            "worker4_pass_consumed",
            "consumer_ingress_payloads_emitted",
            "typed_refs_only",
        ],
    }


__all__ = [
    "build_consumption_request",
    "build_hermes_answer_receipt",
    "build_recall_support_bundle_ref",
    "build_typed_unavailable",
    "consume_verified_producer_receipt",
    "validate_consumption_request",
    "validate_hermes_answer_receipt",
    "validate_recall_support_bundle_ref",
    "validate_typed_unavailable",
]
