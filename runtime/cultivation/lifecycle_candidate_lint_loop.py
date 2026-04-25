from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso

from .gardener_lifecycle_transition_request import (
    build_gardener_stale_request,
    build_gardener_supersession_request,
    validate_gardener_lifecycle_transition_request,
)
from .vault_record_lifecycle import validate_vault_record_lifecycle


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
LIFECYCLE_CANDIDATE_LINT_LOOP_SCHEMA_PATH = (
    CONTRACTS_ROOT / "lifecycle_candidate_lint_loop.v1.schema.json"
)

ALLOWED_CANDIDATE_KINDS = {"lint", "simplicity"}
ALLOWED_TARGET_STATES = {"STALE", "SUPERSEDED"}


@lru_cache(maxsize=1)
def load_lifecycle_candidate_lint_loop_schema() -> dict[str, Any]:
    return json.loads(LIFECYCLE_CANDIDATE_LINT_LOOP_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_lifecycle_candidate_lint_loop(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_lifecycle_candidate_lint_loop_schema())
    for result in payload["candidate_results"]:
        validate_gardener_lifecycle_transition_request(result["transition_request"])


def _require_active_record(record: Mapping[str, Any]) -> dict[str, Any]:
    active = dict(record)
    validate_vault_record_lifecycle(active)
    if active.get("lifecycle_state") != "ACTIVE":
        raise ValueError("lifecycle candidate lint loop requires ACTIVE records")
    if active.get("physical_delete_allowed") is not False:
        raise ValueError("physical deletion is not allowed")
    return active


def _active_record_ref(active: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_record_id": str(active["lifecycle_record_id"]),
        "canonical_record_id": str(active["canonical_record_id"]),
        "lifecycle_state": "ACTIVE",
        "canonical_ref": dict(active["canonical_ref"]),
        "source_refs": [dict(ref) for ref in active["source_refs"]],
        "provenance": dict(active["provenance"]),
    }


def _require_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not dict(value):
        raise ValueError(f"{name} is required")
    return dict(value)


def _require_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _target_state(value: Any) -> str:
    state = str(value or "").strip().upper()
    if state not in ALLOWED_TARGET_STATES:
        raise ValueError("target_lifecycle_state must be STALE or SUPERSEDED")
    return state


def _candidate_kind(value: Any) -> str:
    kind = str(value or "").strip()
    if kind not in ALLOWED_CANDIDATE_KINDS:
        raise ValueError("lifecycle candidate lint loop accepts only lint or simplicity candidates")
    return kind


def _transition_request(
    *,
    active_record: Mapping[str, Any],
    finding: Mapping[str, Any],
    candidate_kind: str,
    candidate_id: str,
    target_state: str,
    requested_at: str,
) -> dict[str, Any]:
    supersession_reason = _require_text("supersession_reason", finding.get("supersession_reason"))
    invalidated_by = _require_mapping("invalidated_by", finding.get("invalidated_by"))
    evidence_ref = _require_mapping("evidence_ref", finding.get("evidence_ref"))
    if target_state == "STALE":
        return build_gardener_stale_request(
            active_record=active_record,
            supersession_reason=supersession_reason,
            invalidated_by=invalidated_by,
            candidate_kind=candidate_kind,
            candidate_id=candidate_id,
            evidence_ref=evidence_ref,
            requested_at=requested_at,
        )
    successor_record_id = _require_text("successor_record_id", finding.get("successor_record_id"))
    return build_gardener_supersession_request(
        active_record=active_record,
        successor_record_id=successor_record_id,
        supersession_reason=supersession_reason,
        invalidated_by=invalidated_by,
        candidate_kind=candidate_kind,
        candidate_id=candidate_id,
        evidence_ref=evidence_ref,
        requested_at=requested_at,
    )


def build_lifecycle_candidate_lint_loop(
    *,
    active_record: Mapping[str, Any],
    candidate_findings: Sequence[Mapping[str, Any]],
    requested_at: str | None = None,
) -> dict[str, Any]:
    """Emit typed lint/simplicity lifecycle candidates without mutation.

    The loop delegates each finding to Gardener lifecycle transition requests,
    so lint and Simplicity Criterion outputs can propose stale/supersession
    review while leaving canonical vault state untouched.
    """

    active = _require_active_record(active_record)
    requested = requested_at or utc_now_iso()
    findings = [dict(finding) for finding in candidate_findings if isinstance(finding, Mapping) and dict(finding)]
    if not findings:
        raise ValueError("candidate_findings are required")

    candidate_results: list[dict[str, Any]] = []
    for finding in findings:
        candidate_kind = _candidate_kind(finding.get("candidate_kind"))
        candidate_id = _require_text("candidate_id", finding.get("candidate_id"))
        target_state = _target_state(finding.get("target_lifecycle_state"))
        request = _transition_request(
            active_record=active,
            finding=finding,
            candidate_kind=candidate_kind,
            candidate_id=candidate_id,
            target_state=target_state,
            requested_at=requested,
        )
        candidate_results.append(
            {
                "candidate_kind": candidate_kind,
                "candidate_id": candidate_id,
                "candidate_status": "proposed",
                "target_lifecycle_state": target_state,
                "transition_request": request,
                "candidate_authority": "proposal_only",
                "lifecycle_review_required": True,
                "canonical_write_status": "not_written",
                "direct_canonical_mutation_status": "not_mutated",
                "vault_mutation_allowed": False,
                "physical_delete_allowed": False,
            }
        )

    loop = {
        "schema_version": "lifecycle_candidate_lint_loop.v1",
        "lint_loop_id": uuid.uuid4().hex,
        "loop_status": "candidates_proposed_for_review",
        "active_record_ref": _active_record_ref(active),
        "candidate_results": candidate_results,
        "loop_policy": "proposal_only",
        "lint_authority": "candidate_proposal_only",
        "simplicity_authority": "candidate_proposal_only",
        "lifecycle_review_required": True,
        "canonical_authority": "not_this_contract",
        "canonical_write_status": "not_written",
        "direct_canonical_mutation_status": "not_mutated",
        "vault_mutation_allowed": False,
        "physical_delete_allowed": False,
        "reason_codes": [
            "lifecycle_candidate_lint_loop_ran",
            "lint_candidates_proposal_only",
            "simplicity_candidates_proposal_only",
            "lifecycle_review_required",
            "canonical_write_not_authorized",
        ],
        "created_at": requested,
    }
    validate_lifecycle_candidate_lint_loop(loop)
    return loop
