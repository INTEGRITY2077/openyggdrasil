from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from delivery.mailbox_contamination_guard import validate_mailbox_guard_result
from delivery.support_bundle import validate_support_bundle
from evaluation.graphify_snapshot_from_live_delta import (
    validate_graphify_snapshot_from_live_delta,
)
from evaluation.hermes_response_quality_scorecard import (
    validate_hermes_response_quality_scorecard,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "mailbox_delivery_hermes_consumption.v1.schema.json"

MAILBOX_DELIVERY_SURFACE = "mailbox_delivery"
HERMES_CONSUMPTION_SURFACE = "hermes_consumption"
STALE_DECOY_REJECTION_SURFACE = "stale_decoy_rejection"
REASONING_LEASE_SURFACE = "reasoning_lease_isolation"
EVIDENCE_REQUIREMENTS = {
    MAILBOX_DELIVERY_SURFACE: "mailbox_delivery_receipt_ref_non_empty",
    HERMES_CONSUMPTION_SURFACE: "hermes_consumption_receipt_ref_non_empty",
    STALE_DECOY_REJECTION_SURFACE: "stale_decoy_rejection_ref_non_empty",
    REASONING_LEASE_SURFACE: "reasoning_lease_isolation_ref_non_empty",
}


@lru_cache(maxsize=1)
def load_mailbox_delivery_hermes_consumption_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def support_bundle_fingerprint(payload: Mapping[str, Any]) -> str:
    validate_support_bundle(payload)
    encoded = _stable_json(payload).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _typed_surfaces(payload: Mapping[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in payload.get("typed_unavailable_surfaces") or []
        if str(item).strip()
    }


def _evidence_set(payload: Mapping[str, Any]) -> set[str]:
    return {str(item).strip() for item in payload.get("evidence_required") or [] if str(item).strip()}


def _string_refs(payload: Mapping[str, Any], key: str) -> list[str]:
    return [str(item).strip() for item in payload.get(key) or [] if str(item).strip()]


def _require_source_snapshot(payload: Mapping[str, Any], source_snapshot: Mapping[str, Any] | None) -> None:
    if source_snapshot is None:
        return
    if payload.get("source_graphify_snapshot_id") != source_snapshot.get("snapshot_proof_id"):
        raise ValueError("source_graphify_snapshot_id must match source_snapshot.snapshot_proof_id")
    if source_snapshot.get("readiness_state") != "ready_for_e2e4":
        raise ValueError("source_snapshot must be ready_for_e2e4")
    if source_snapshot.get("decision") != "e2e3_graphify_snapshot_valid":
        raise ValueError("source_snapshot decision must be e2e3_graphify_snapshot_valid")
    validate_graphify_snapshot_from_live_delta(source_snapshot)
    if payload.get("source_delta_id") != source_snapshot.get("source_delta_id"):
        raise ValueError("source_delta_id must match source_snapshot")
    if payload.get("source_artifact_bundle_id") != source_snapshot.get("source_artifact_bundle_id"):
        raise ValueError("source_artifact_bundle_id must match source_snapshot")
    if payload.get("provider_name") != source_snapshot.get("provider_name"):
        raise ValueError("provider_name must match source_snapshot")
    if payload.get("provider_profile") != source_snapshot.get("provider_profile"):
        raise ValueError("provider_profile must match source_snapshot")
    if payload.get("session_ref") != source_snapshot.get("session_ref"):
        raise ValueError("session_ref must match source_snapshot")


def _require_guard_acceptance(guard_result: Mapping[str, Any], *, message_id: str) -> None:
    validate_mailbox_guard_result(guard_result)
    if guard_result.get("message_id") != message_id:
        raise ValueError("delivery guard_result.message_id must match mailbox message_id")
    if guard_result.get("verdict") != "accept" or guard_result.get("action") != "admit":
        raise ValueError("delivery guard_result must accept the mailbox message")


def _validate_delivery_receipt(receipt: Mapping[str, Any], *, expected_profile: str) -> tuple[str, Mapping[str, Any]]:
    if receipt.get("provider_id") != "hermes":
        raise ValueError("delivery_receipt provider_id must be hermes")
    if receipt.get("provider_profile") != expected_profile:
        raise ValueError("delivery_receipt provider_profile must match proof")
    message_id = str(receipt.get("message_id") or "").strip()
    if not message_id:
        raise ValueError("delivery_receipt.message_id is required")
    _require_guard_acceptance(dict(receipt.get("guard_result") or {}), message_id=message_id)
    support_bundle = receipt.get("support_bundle")
    if not isinstance(support_bundle, Mapping):
        raise ValueError("delivery_receipt.support_bundle must be an object")
    fingerprint = support_bundle_fingerprint(support_bundle)
    if receipt.get("support_bundle_fingerprint") != fingerprint:
        raise ValueError("delivery_receipt.support_bundle_fingerprint must match support_bundle content")
    return fingerprint, support_bundle


def _validate_consumption_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_profile: str,
    delivery_message_id: str,
    delivery_fingerprint: str,
    delivered_bundle: Mapping[str, Any],
) -> None:
    if receipt.get("provider_id") != "hermes":
        raise ValueError("hermes_consumption_receipt provider_id must be hermes")
    if receipt.get("provider_profile") != expected_profile:
        raise ValueError("hermes_consumption_receipt provider_profile must match proof")
    if receipt.get("consumed_message_id") != delivery_message_id:
        raise ValueError("hermes_consumption_receipt.consumed_message_id must match delivery message_id")

    consumed_bundle = receipt.get("consumed_support_bundle")
    if not isinstance(consumed_bundle, Mapping):
        raise ValueError("hermes_consumption_receipt.consumed_support_bundle must be an object")
    validate_support_bundle(consumed_bundle)
    if _stable_json(consumed_bundle) != _stable_json(delivered_bundle):
        raise ValueError("hermes_consumption_receipt.consumed_support_bundle must exactly match delivered support_bundle")
    fingerprint = support_bundle_fingerprint(consumed_bundle)
    if fingerprint != delivery_fingerprint:
        raise ValueError("hermes_consumption_receipt support bundle hash must match delivery")
    if receipt.get("support_bundle_fingerprint") != fingerprint:
        raise ValueError("hermes_consumption_receipt.support_bundle_fingerprint must match consumed_support_bundle")
    if receipt.get("raw_transcript_included") is not False:
        raise ValueError("hermes_consumption_receipt.raw_transcript_included must be false")
    if not _string_refs(receipt, "used_memory_refs"):
        raise ValueError("hermes_consumption_receipt.used_memory_refs are required")
    if not _string_refs(receipt, "safe_evidence_pointers"):
        raise ValueError("hermes_consumption_receipt.safe_evidence_pointers are required")
    for row in receipt.get("rejected_memory") or []:
        if not isinstance(row, Mapping) or not row.get("reason_codes"):
            raise ValueError("hermes_consumption_receipt rejected_memory rows require reason_codes")

    scorecard = receipt.get("response_quality_scorecard")
    if not isinstance(scorecard, Mapping):
        raise ValueError("response_quality_scorecard must be an object")
    validate_hermes_response_quality_scorecard(scorecard)
    if scorecard.get("decision") != "green_passed" or scorecard.get("failing_metrics"):
        raise ValueError("response_quality_scorecard must be green_passed with no failing_metrics")


def _validate_stale_decoy_rejections(receipts: list[Any]) -> None:
    if not receipts:
        raise ValueError("stale_decoy_rejection_receipts are required")
    roles: set[str] = set()
    for row in receipts:
        if not isinstance(row, Mapping):
            raise ValueError("stale_decoy_rejection_receipts must contain objects")
        role = str(row.get("candidate_role") or "")
        roles.add(role)
        guard = row.get("guard_result")
        if not isinstance(guard, Mapping):
            raise ValueError("stale_decoy_rejection_receipts guard_result must be an object")
        validate_mailbox_guard_result(guard)
        if guard.get("message_id") != row.get("message_id"):
            raise ValueError("stale_decoy_rejection_receipts message_id must match guard_result")
        if guard.get("verdict") == "accept" or guard.get("action") == "admit":
            raise ValueError("stale_decoy_rejection_receipts must reject or quarantine stale/decoy candidates")
        if not guard.get("reason_codes"):
            raise ValueError("stale_decoy_rejection_receipts require reason_codes")
    required_roles = {"stale_memory", "decoy_memory"}
    missing = sorted(required_roles - roles)
    if missing:
        raise ValueError(f"stale_decoy_rejection_receipts must include: {', '.join(missing)}")


def _require_later_lane_boundary(payload: Mapping[str, Any]) -> None:
    if _string_refs(payload, "reasoning_lease_isolation_refs"):
        raise ValueError("E2E4 must not claim reasoning lease isolation")
    typed = _typed_surfaces(payload)
    if REASONING_LEASE_SURFACE not in typed:
        raise ValueError("typed_unavailable_surfaces must include reasoning_lease_isolation")
    evidence = _evidence_set(payload)
    if EVIDENCE_REQUIREMENTS[REASONING_LEASE_SURFACE] not in evidence:
        raise ValueError("missing evidence_required entry: reasoning_lease_isolation_ref_non_empty")
    if payload.get("rerun_condition") != "provide_reasoning_lease_isolation_artifacts":
        raise ValueError("missing reasoning lease lane requires provide_reasoning_lease_isolation_artifacts")
    if payload.get("claim_scope") != "e2e4_mailbox_delivery_consumption_only":
        raise ValueError("claim_scope must be e2e4_mailbox_delivery_consumption_only")


def _require_proven_rules(payload: Mapping[str, Any]) -> None:
    if payload.get("mailbox_delivery_proven") is not True:
        raise ValueError("mailbox_delivery_proven must be true")
    if payload.get("hermes_consumption_proven") is not True:
        raise ValueError("hermes_consumption_proven must be true")
    if payload.get("stale_decoy_rejection_proven") is not True:
        raise ValueError("stale_decoy_rejection_proven must be true")
    if payload.get("decision") != "e2e4_mailbox_delivery_consumption_valid":
        raise ValueError("proven E2E4 decision must be e2e4_mailbox_delivery_consumption_valid")
    if payload.get("readiness_state") != "ready_for_e2e5":
        raise ValueError("proven E2E4 readiness_state must be ready_for_e2e5")
    if int(payload.get("safe_evidence_pointer_count") or 0) < 5:
        raise ValueError("safe_evidence_pointer_count must be >= 5 for proven mailbox consumption")

    delivery = payload.get("delivery_receipt")
    consumption = payload.get("hermes_consumption_receipt")
    if not isinstance(delivery, Mapping):
        raise ValueError("delivery_receipt is required for proven E2E4")
    if not isinstance(consumption, Mapping):
        raise ValueError("hermes_consumption_receipt is required for proven E2E4")

    delivery_fingerprint, delivered_bundle = _validate_delivery_receipt(
        delivery,
        expected_profile=str(payload["provider_profile"]),
    )
    if payload.get("support_bundle_fingerprint") != delivery_fingerprint:
        raise ValueError("support_bundle_fingerprint must match delivered support_bundle")
    _validate_consumption_receipt(
        consumption,
        expected_profile=str(payload["provider_profile"]),
        delivery_message_id=str(delivery["message_id"]),
        delivery_fingerprint=delivery_fingerprint,
        delivered_bundle=delivered_bundle,
    )
    _validate_stale_decoy_rejections(list(payload.get("stale_decoy_rejection_receipts") or []))
    _require_later_lane_boundary(payload)


def _require_typed_unavailable_rules(payload: Mapping[str, Any]) -> None:
    if payload.get("delivery_receipt") is not None:
        raise ValueError("typed unavailable E2E4 must not carry delivery_receipt")
    if payload.get("hermes_consumption_receipt") is not None:
        raise ValueError("typed unavailable E2E4 must not carry hermes_consumption_receipt")
    if payload.get("stale_decoy_rejection_receipts"):
        raise ValueError("typed unavailable E2E4 must not carry stale_decoy_rejection_receipts")
    if payload.get("mailbox_delivery_proven") is not False:
        raise ValueError("typed unavailable E2E4 mailbox_delivery_proven must be false")
    if payload.get("hermes_consumption_proven") is not False:
        raise ValueError("typed unavailable E2E4 hermes_consumption_proven must be false")
    if payload.get("stale_decoy_rejection_proven") is not False:
        raise ValueError("typed unavailable E2E4 stale_decoy_rejection_proven must be false")
    if payload.get("decision") != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable E2E4 decision must be typed_unavailable_not_live_proven")
    if payload.get("readiness_state") != "not_ready":
        raise ValueError("typed unavailable E2E4 readiness_state must be not_ready")
    if payload.get("claim_scope") != "typed_unavailable_not_live_proven":
        raise ValueError("typed unavailable E2E4 claim_scope must be typed_unavailable_not_live_proven")
    if payload.get("rerun_condition") != "provide_mailbox_delivery_hermes_consumption":
        raise ValueError("typed unavailable E2E4 must require provide_mailbox_delivery_hermes_consumption")

    required = {
        MAILBOX_DELIVERY_SURFACE,
        HERMES_CONSUMPTION_SURFACE,
        STALE_DECOY_REJECTION_SURFACE,
        REASONING_LEASE_SURFACE,
    }
    typed = _typed_surfaces(payload)
    missing = sorted(required - typed)
    if missing:
        raise ValueError(f"typed_unavailable_surfaces must include: {', '.join(missing)}")

    evidence = _evidence_set(payload)
    missing_evidence = [
        EVIDENCE_REQUIREMENTS[surface]
        for surface in required
        if EVIDENCE_REQUIREMENTS[surface] not in evidence
    ]
    if missing_evidence:
        raise ValueError(f"missing evidence_required entries: {', '.join(missing_evidence)}")


def validate_mailbox_delivery_hermes_consumption(
    payload: Mapping[str, Any],
    *,
    source_snapshot: Mapping[str, Any] | None = None,
) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_mailbox_delivery_hermes_consumption_schema(),
    )
    if payload.get("raw_transcript_included") is not False:
        raise ValueError("raw_transcript_included must be false")
    _require_source_snapshot(payload, source_snapshot)

    decision = str(payload.get("decision") or "")
    if decision == "e2e4_mailbox_delivery_consumption_valid":
        _require_proven_rules(payload)
    elif decision == "typed_unavailable_not_live_proven":
        _require_typed_unavailable_rules(payload)
    else:
        raise ValueError(f"unknown E2E4 decision: {decision}")


def build_typed_unavailable_mailbox_delivery_hermes_consumption(
    *,
    source_snapshot: Mapping[str, Any],
    consumption_proof_id: str,
    reason_code: str,
    checked_at: str | None = None,
) -> dict[str, Any]:
    if source_snapshot.get("readiness_state") != "ready_for_e2e4":
        raise ValueError("source_snapshot must be ready_for_e2e4")
    validate_graphify_snapshot_from_live_delta(source_snapshot)
    generated_at = checked_at or utc_now_iso()
    surfaces = [
        MAILBOX_DELIVERY_SURFACE,
        HERMES_CONSUMPTION_SURFACE,
        STALE_DECOY_REJECTION_SURFACE,
        REASONING_LEASE_SURFACE,
    ]
    payload = {
        "schema_version": "mailbox_delivery_hermes_consumption.v1",
        "consumption_proof_id": str(consumption_proof_id),
        "source_graphify_snapshot_id": str(source_snapshot["snapshot_proof_id"]),
        "source_delta_id": str(source_snapshot["source_delta_id"]),
        "source_artifact_bundle_id": str(source_snapshot["source_artifact_bundle_id"]),
        "provider_name": str(source_snapshot["provider_name"]),
        "provider_profile": str(source_snapshot["provider_profile"]),
        "session_ref": str(source_snapshot["session_ref"]),
        "support_bundle_fingerprint": None,
        "delivery_receipt": None,
        "hermes_consumption_receipt": None,
        "stale_decoy_rejection_receipts": [],
        "safe_evidence_pointer_count": 0,
        "raw_transcript_included": False,
        "mailbox_delivery_proven": False,
        "hermes_consumption_proven": False,
        "stale_decoy_rejection_proven": False,
        "reasoning_lease_isolation_refs": [],
        "typed_unavailable_surfaces": surfaces,
        "rerun_condition": "provide_mailbox_delivery_hermes_consumption",
        "evidence_required": [EVIDENCE_REQUIREMENTS[surface] for surface in surfaces],
        "claim_scope": "typed_unavailable_not_live_proven",
        "decision": "typed_unavailable_not_live_proven",
        "readiness_state": "not_ready",
        "checked_at": generated_at,
    }
    if reason_code:
        payload["evidence_required"] = list(dict.fromkeys(payload["evidence_required"]))
    validate_mailbox_delivery_hermes_consumption(payload, source_snapshot=source_snapshot)
    return payload
