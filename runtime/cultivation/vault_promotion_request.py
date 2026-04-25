from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from admission.decision_contracts import validate_evaluator_verdict
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
VAULT_PROMOTION_REQUEST_SCHEMA_PATH = CONTRACTS_ROOT / "vault_promotion_request.v1.schema.json"


@lru_cache(maxsize=1)
def load_vault_promotion_request_schema() -> dict[str, Any]:
    return json.loads(VAULT_PROMOTION_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_vault_promotion_request(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_vault_promotion_request_schema())


def _require_mapping(name: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not dict(value):
        raise ValueError(f"{name} is required")
    return dict(value)


def _require_source_refs(source_refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs = [dict(ref) for ref in source_refs if isinstance(ref, Mapping) and dict(ref)]
    if not refs:
        raise ValueError("source_refs are required")
    return refs


def _completed_mailbox_delivery_ref(mailbox_delivery_ref: Mapping[str, Any]) -> dict[str, Any]:
    ref = _require_mapping("mailbox_delivery_ref", mailbox_delivery_ref)
    if str(ref.get("delivery_status") or "") != "completed":
        raise ValueError("mailbox delivery must be completed before promotion can be requested")
    message_id = str(ref.get("message_id") or "").strip()
    if not message_id:
        raise ValueError("mailbox_delivery_ref.message_id is required")
    return {
        "delivery_ref_kind": "mailbox_message",
        "message_id": message_id,
        "handoff_id": ref.get("handoff_id"),
        "namespace": ref.get("namespace"),
        "delivery_status": "completed",
        "delivered_at": ref.get("delivered_at"),
    }


def _evaluator_verdict_ref(evaluator_verdict: Mapping[str, Any]) -> dict[str, Any]:
    validate_evaluator_verdict(evaluator_verdict)
    if evaluator_verdict.get("promotion_recommendation") is not True:
        raise ValueError("evaluator promotion_recommendation must be true")
    if evaluator_verdict.get("promotion_gate") != "ready":
        raise ValueError("evaluator promotion_gate must be ready")
    if evaluator_verdict.get("vault_promotion_readiness") != "ready_after_delivery":
        raise ValueError("evaluator vault_promotion_readiness must be ready_after_delivery")
    return {
        "evaluator_verdict_id": str(evaluator_verdict["evaluator_verdict_id"]),
        "candidate_id": str(evaluator_verdict["candidate_id"]),
        "promotion_recommendation": True,
        "promotion_gate": "ready",
        "vault_promotion_readiness": "ready_after_delivery",
        "worthiness_score": float(evaluator_verdict["worthiness_score"]),
        "confidence_score": float(evaluator_verdict["confidence_score"]),
        "reason_codes": [str(code) for code in evaluator_verdict.get("reason_codes") or []],
    }


def build_vault_promotion_request(
    *,
    evaluator_verdict: Mapping[str, Any],
    mailbox_delivery_ref: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    effort_metadata: Mapping[str, Any],
    requested_owner: str = "gardener",
) -> dict[str, Any]:
    """Build an explicit request for later vault promotion review.

    The request is not a canonical write. It requires Evaluator promote=true and
    a completed mailbox delivery reference, then records enough provenance for a
    later owner to review and promote through the Phase 5 lifecycle.
    """

    verdict_ref = _evaluator_verdict_ref(evaluator_verdict)
    delivery_ref = _completed_mailbox_delivery_ref(mailbox_delivery_ref)
    active_source_refs = _require_source_refs(source_refs)
    active_provenance = _require_mapping("provenance", provenance)
    active_effort = _require_mapping("effort_metadata", effort_metadata)

    request = {
        "schema_version": "vault_promotion_request.v1",
        "promotion_request_id": uuid.uuid4().hex,
        "request_kind": "explicit_vault_promotion_request",
        "request_status": "requested",
        "candidate_id": str(evaluator_verdict["candidate_id"]),
        "provider_id": str(evaluator_verdict["provider_id"]),
        "provider_profile": str(evaluator_verdict["provider_profile"]),
        "provider_session_id": str(evaluator_verdict["provider_session_id"]),
        "session_uid": str(evaluator_verdict["session_uid"]),
        "requested_owner": requested_owner,
        "source_refs": active_source_refs,
        "mailbox_delivery_ref": delivery_ref,
        "evaluator_verdict_ref": verdict_ref,
        "provenance": active_provenance,
        "confidence": {
            "worthiness_score": verdict_ref["worthiness_score"],
            "confidence_score": verdict_ref["confidence_score"],
        },
        "effort_metadata": active_effort,
        "gate_metadata": {
            "evaluator_promote_gate": "promote_true_and_ready",
            "mailbox_delivery_gate": "completed_delivery_required",
            "canonical_write_gate": "not_authorized_by_request",
        },
        "semantic_worth_authority": "evaluator_only",
        "delivery_authority": "postman_completed_delivery_ref_only",
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "vault_mutation_allowed": False,
        "runner_success_is_promotion_gate": False,
        "reason_codes": [
            "vault_promotion_request_explicit",
            "evaluator_promote_true",
            "mailbox_delivery_completed",
            "canonical_write_not_authorized",
        ],
        "requested_at": utc_now_iso(),
    }
    validate_vault_promotion_request(request)
    return request
