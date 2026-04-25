from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_evaluator_verdict,
    validate_map_topography,
    validate_postman_delivery_handoff,
)
from cultivation.vault_promotion_request import build_vault_promotion_request
from delivery.mailbox_schema import validate_message
from harness_common import utc_now_iso


def build_postman_delivery_handoff(
    *,
    admission_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
    session_admission_verdict_id: str | None = None,
) -> dict[str, Any]:
    """Finalize a provider-session delivery target without taking upstream authority."""

    validate_admission_verdict(admission_verdict)
    validate_map_topography(map_topography)
    handoff = {
        "schema_version": "postman_delivery_handoff.v1",
        "handoff_id": uuid.uuid4().hex,
        "handoff_status": "ready_for_mailbox_packet",
        "message_type": "map_topography",
        "target": {
            "provider_id": str(admission_verdict["provider_id"]),
            "provider_profile": str(admission_verdict["provider_profile"]),
            "provider_session_id": str(admission_verdict["provider_session_id"]),
            "topic": str(admission_verdict["topic_key"]),
            "canonical_relative_path": str(map_topography["canonical_relative_path"]),
            "topography_id": str(map_topography["topography_id"]),
            "session_admission_verdict_id": session_admission_verdict_id,
            "source_refs": source_refs,
        },
        "delivery_authority": "session_delivery_finalization_only",
        "semantic_worth_authority": "not_postman",
        "category_authority": "not_postman",
        "placement_authority": "not_postman",
        "sot_mutation_authority": "not_postman",
        "mailbox_mutation_authority": "deferred_to_guarded_emission",
        "source_ref_authority": "forward_only",
        "reason_codes": [
            "postman_handoff_ready",
            "delivery_finalization_only",
            "mailbox_mutation_deferred_to_r3",
        ],
        "created_at": utc_now_iso(),
    }
    validate_postman_delivery_handoff(handoff)
    return handoff


def _message_scope(message: Mapping[str, Any]) -> Mapping[str, Any]:
    scope = message.get("scope")
    return scope if isinstance(scope, Mapping) else {}


def _message_payload(message: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = message.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _assert_delivery_matches_evaluator(
    *,
    delivered_message: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
) -> None:
    scope = _message_scope(delivered_message)
    expected = {
        "provider_id": evaluator_verdict.get("provider_id"),
        "profile": evaluator_verdict.get("provider_profile"),
        "session_id": evaluator_verdict.get("provider_session_id"),
    }
    for scope_key, expected_value in expected.items():
        actual_value = scope.get(scope_key)
        if actual_value and expected_value and str(actual_value) != str(expected_value):
            raise ValueError(f"mailbox delivery scope does not match evaluator verdict: {scope_key}")


def _completed_delivery_ref(
    *,
    delivered_message: Mapping[str, Any],
    delivery_claim: Mapping[str, Any],
    namespace: str | None,
) -> dict[str, Any]:
    message_id = str(delivered_message.get("message_id") or "").strip()
    claim_message_id = str(delivery_claim.get("message_id") or "").strip()
    if not message_id:
        raise ValueError("delivered_message.message_id is required")
    if claim_message_id and claim_message_id != message_id:
        raise ValueError("delivery claim message_id does not match delivered message")

    delivery_status = str(delivery_claim.get("delivery_status") or "").strip()
    claim_type = str(delivery_claim.get("claim_type") or "").strip()
    if delivery_status != "completed" and claim_type != "push_delivered":
        raise ValueError("completed mailbox delivery is required before promotion request emission")

    return {
        "delivery_ref_kind": "mailbox_message",
        "message_id": message_id,
        "handoff_id": delivery_claim.get("handoff_id"),
        "namespace": namespace or delivery_claim.get("namespace"),
        "delivery_status": "completed",
        "delivered_at": delivery_claim.get("delivered_at") or delivery_claim.get("created_at"),
    }


def _source_refs_from_message(
    delivered_message: Mapping[str, Any],
    source_refs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if source_refs:
        return [dict(ref) for ref in source_refs if isinstance(ref, Mapping) and dict(ref)]

    payload = _message_payload(delivered_message)
    inferred_refs: list[dict[str, Any]] = []
    payload_source_refs = payload.get("source_refs")
    if isinstance(payload_source_refs, list):
        inferred_refs.extend(dict(ref) for ref in payload_source_refs if isinstance(ref, Mapping) and dict(ref))

    for path in payload.get("source_paths") or []:
        value = str(path or "").strip()
        if value:
            inferred_refs.append({"kind": "vault_path", "path": value})

    source_ref = payload.get("source_ref")
    if source_ref:
        inferred_refs.append({"kind": "source_ref", "ref": str(source_ref)})

    if not inferred_refs:
        raise ValueError("delivered mailbox message source refs are required")
    return inferred_refs


def build_postman_promotion_request_after_delivery(
    *,
    delivered_message: Mapping[str, Any],
    delivery_claim: Mapping[str, Any],
    evaluator_verdict: Mapping[str, Any],
    effort_metadata: Mapping[str, Any],
    source_refs: list[dict[str, Any]] | None = None,
    provenance: Mapping[str, Any] | None = None,
    namespace: str | None = None,
    requested_owner: str = "gardener",
) -> dict[str, Any]:
    """Emit a vault promotion request after delivery without deciding worth.

    Postman contributes only completed-delivery evidence and source-ref
    forwarding. Evaluator remains the semantic-worth authority, and the
    resulting request still cannot write canonical vault state.
    """

    message = dict(delivered_message)
    claim = dict(delivery_claim)
    validate_message(message)
    validate_evaluator_verdict(evaluator_verdict)
    _assert_delivery_matches_evaluator(delivered_message=message, evaluator_verdict=evaluator_verdict)
    delivery_ref = _completed_delivery_ref(
        delivered_message=message,
        delivery_claim=claim,
        namespace=namespace,
    )
    active_source_refs = _source_refs_from_message(message, source_refs)
    active_provenance = dict(provenance or {})
    if not active_provenance:
        active_provenance = {
            "source_system": "postman_completed_delivery",
            "mailbox_message_id": str(message["message_id"]),
            "delivery_claim_id": claim.get("claim_id"),
            "producer": message.get("producer"),
        }

    return build_vault_promotion_request(
        evaluator_verdict=evaluator_verdict,
        mailbox_delivery_ref=delivery_ref,
        source_refs=active_source_refs,
        provenance=active_provenance,
        effort_metadata=effort_metadata,
        requested_owner=requested_owner,
    )
