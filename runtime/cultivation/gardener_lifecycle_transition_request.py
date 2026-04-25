from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso

from .vault_record_lifecycle import (
    mark_vault_record_stale,
    mark_vault_record_superseded,
    validate_vault_record_lifecycle,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
GARDENER_LIFECYCLE_TRANSITION_REQUEST_SCHEMA_PATH = (
    CONTRACTS_ROOT / "gardener_lifecycle_transition_request.v1.schema.json"
)


@lru_cache(maxsize=1)
def load_gardener_lifecycle_transition_request_schema() -> dict[str, Any]:
    return json.loads(GARDENER_LIFECYCLE_TRANSITION_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_gardener_lifecycle_transition_request(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_gardener_lifecycle_transition_request_schema(),
    )
    validate_vault_record_lifecycle(payload["proposed_transition"])


def _require_mapping(name: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not dict(value):
        raise ValueError(f"{name} is required")
    return dict(value)


def _require_active_record(record: Mapping[str, Any]) -> dict[str, Any]:
    active = dict(record)
    validate_vault_record_lifecycle(active)
    if active.get("lifecycle_state") != "ACTIVE":
        raise ValueError("Gardener can only request transitions from ACTIVE records")
    if active.get("physical_delete_allowed") is not False:
        raise ValueError("physical deletion is not allowed")
    return active


def _active_record_ref(active: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_record_id": str(active["lifecycle_record_id"]),
        "canonical_record_id": str(active["canonical_record_id"]),
        "lifecycle_state": "ACTIVE",
        "canonical_ref": dict(active["canonical_ref"]),
        "valid_from": str(active["valid_from"]),
        "archive_trace_refs": [dict(ref) for ref in active["archive_trace_refs"]],
    }


def _candidate_ref(
    *,
    candidate_kind: str,
    candidate_id: str,
    evidence_ref: Mapping[str, Any],
) -> dict[str, Any]:
    kind = str(candidate_kind).strip()
    candidate = str(candidate_id).strip()
    if kind not in {"vault_promotion_request", "contradiction", "lint", "simplicity"}:
        raise ValueError("candidate_kind must be a lifecycle proposal source")
    if not candidate:
        raise ValueError("candidate_id is required")
    return {
        "candidate_kind": kind,
        "candidate_id": candidate,
        "candidate_status": "proposed",
        "evidence_ref": _require_mapping("evidence_ref", evidence_ref),
    }


def _base_request(
    *,
    active: Mapping[str, Any],
    proposed_transition: Mapping[str, Any],
    requested_lifecycle_state: str,
    successor_record_id: str | None,
    supersession_reason: str,
    invalidated_by: Mapping[str, Any],
    candidate_kind: str,
    candidate_id: str,
    evidence_ref: Mapping[str, Any],
    requested_at: str,
) -> dict[str, Any]:
    reason = str(supersession_reason).strip()
    if not reason:
        raise ValueError("supersession_reason is required")
    request = {
        "schema_version": "gardener_lifecycle_transition_request.v1",
        "transition_request_id": uuid.uuid4().hex,
        "request_kind": "gardener_lifecycle_transition_request",
        "request_status": "pending_gate_review",
        "requested_lifecycle_state": requested_lifecycle_state,
        "active_record_ref": _active_record_ref(active),
        "successor_record_id": successor_record_id,
        "candidate_ref": _candidate_ref(
            candidate_kind=candidate_kind,
            candidate_id=candidate_id,
            evidence_ref=evidence_ref,
        ),
        "source_refs": [dict(ref) for ref in active["source_refs"]],
        "provenance": dict(active["provenance"]),
        "invalidated_by": _require_mapping("invalidated_by", invalidated_by),
        "supersession_reason": reason,
        "proposed_transition": dict(proposed_transition),
        "gate_metadata": {
            "candidate_gate": "proposal_only",
            "lifecycle_review_gate": "pending_lifecycle_review",
            "direct_mutation_gate": "not_authorized_by_request",
        },
        "gardener_authority": "lifecycle_transition_request_only",
        "candidate_authority": "proposal_only",
        "lifecycle_review_required": True,
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "direct_canonical_mutation_status": "not_mutated",
        "vault_mutation_allowed": False,
        "physical_delete_allowed": False,
        "traceability_preserved": True,
        "reason_codes": [
            "gardener_lifecycle_transition_requested",
            f"target:{requested_lifecycle_state.lower()}",
            "candidate_proposal_only",
            "lifecycle_review_required",
            "canonical_write_not_authorized",
        ],
        "requested_at": requested_at,
    }
    validate_gardener_lifecycle_transition_request(request)
    return request


def build_gardener_supersession_request(
    *,
    active_record: Mapping[str, Any],
    successor_record_id: str,
    supersession_reason: str,
    invalidated_by: Mapping[str, Any],
    candidate_kind: str,
    candidate_id: str,
    evidence_ref: Mapping[str, Any],
    requested_at: str | None = None,
) -> dict[str, Any]:
    active = _require_active_record(active_record)
    requested = requested_at or utc_now_iso()
    successor = str(successor_record_id).strip()
    if not successor:
        raise ValueError("successor_record_id is required")
    proposed = mark_vault_record_superseded(
        active,
        superseded_by=successor,
        supersession_reason=supersession_reason,
        invalidated_by=invalidated_by,
        superseded_at=requested,
    )
    return _base_request(
        active=active,
        proposed_transition=proposed,
        requested_lifecycle_state="SUPERSEDED",
        successor_record_id=successor,
        supersession_reason=supersession_reason,
        invalidated_by=invalidated_by,
        candidate_kind=candidate_kind,
        candidate_id=candidate_id,
        evidence_ref=evidence_ref,
        requested_at=requested,
    )


def build_gardener_stale_request(
    *,
    active_record: Mapping[str, Any],
    supersession_reason: str,
    invalidated_by: Mapping[str, Any],
    candidate_kind: str,
    candidate_id: str,
    evidence_ref: Mapping[str, Any],
    requested_at: str | None = None,
) -> dict[str, Any]:
    active = _require_active_record(active_record)
    requested = requested_at or utc_now_iso()
    proposed = mark_vault_record_stale(
        active,
        supersession_reason=supersession_reason,
        invalidated_by=invalidated_by,
        stale_at=requested,
    )
    return _base_request(
        active=active,
        proposed_transition=proposed,
        requested_lifecycle_state="STALE",
        successor_record_id=None,
        supersession_reason=supersession_reason,
        invalidated_by=invalidated_by,
        candidate_kind=candidate_kind,
        candidate_id=candidate_id,
        evidence_ref=evidence_ref,
        requested_at=requested,
    )
