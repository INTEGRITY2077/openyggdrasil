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


def _unsafe_serialized_tokens(payload: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True).replace("\\", "/").lower()
    return [
        token
        for token in ("d:/", "c:/", "file://", "raw_transcript", "transcript.txt", "api_key")
        if token in serialized
    ]


def _active_records_by_canonical_id(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    active_records: dict[str, dict[str, Any]] = {}
    for record in records:
        active = _require_active_record(record)
        canonical_record_id = str(active["canonical_record_id"])
        if canonical_record_id in active_records:
            raise ValueError("active_records must not contain duplicate canonical_record_id")
        active_records[canonical_record_id] = active
    if not active_records:
        raise ValueError("active_records are required")
    return active_records


def _scheduler_transition_result(
    *,
    loop: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    scheduler_id: str,
    scheduled_at: str,
) -> dict[str, Any]:
    request = dict(candidate_result["transition_request"])
    target_state = str(candidate_result["target_lifecycle_state"])
    applied_transition = dict(request["proposed_transition"])
    if applied_transition.get("lifecycle_state") != target_state:
        raise ValueError("applied transition state mismatch")
    validate_vault_record_lifecycle(applied_transition)
    if applied_transition.get("physical_delete_allowed") is not False:
        raise ValueError("physical delete is not allowed")
    if applied_transition.get("traceability_preserved") is not True:
        raise ValueError("traceability must be preserved")
    return {
        "proposal_loop_id": str(loop["lint_loop_id"]),
        "transition_request_id": str(request["transition_request_id"]),
        "canonical_record_id": str(applied_transition["canonical_record_id"]),
        "lifecycle_record_id": str(applied_transition["lifecycle_record_id"]),
        "candidate_kind": str(candidate_result["candidate_kind"]),
        "candidate_id": str(candidate_result["candidate_id"]),
        "target_lifecycle_state": target_state,
        "request_status_before_execution": str(request["request_status"]),
        "candidate_status_before_execution": str(candidate_result["candidate_status"]),
        "lifecycle_review_required_before_execution": bool(
            candidate_result["lifecycle_review_required"]
        ),
        "transition_execution_status": "executed_by_scheduler",
        "scheduler_id": scheduler_id,
        "scheduled_at": scheduled_at,
        "scheduler_authority": "scheduled_lifecycle_transition_executor",
        "applied_transition": applied_transition,
        "lifecycle_transition_write_allowed": True,
        "canonical_content_write_allowed": False,
        "physical_delete_allowed": False,
        "traceability_preserved": True,
    }


def validate_gardener_lifecycle_scheduler_run(payload: Mapping[str, Any]) -> None:
    run = dict(payload)
    required = {
        "schema_version",
        "scheduler_run_id",
        "run_status",
        "scheduler_triggered",
        "scheduler_id",
        "scheduled_at",
        "proposal_loop_count",
        "executed_transition_count",
        "proposal_only_transition_count",
        "proposal_loops",
        "transition_results",
        "execution_policy",
        "reason_codes",
        "created_at",
    }
    missing = sorted(required - set(run))
    if missing:
        raise ValueError(f"gardener lifecycle scheduler run is missing: {', '.join(missing)}")
    if run["schema_version"] != "gardener_lifecycle_scheduler_run.v1":
        raise ValueError("schema_version must be gardener_lifecycle_scheduler_run.v1")
    if run["run_status"] != "transitions_executed":
        raise ValueError("run_status must be transitions_executed")
    if run["scheduler_triggered"] is not True:
        raise ValueError("scheduler_triggered must be true")

    policy = dict(run["execution_policy"])
    if policy.get("trigger_kind") != "scheduler_tick":
        raise ValueError("scheduler trigger must be scheduler_tick")
    if policy.get("proposal_source") != "lifecycle_candidate_lint_loop":
        raise ValueError("proposal source must be lifecycle_candidate_lint_loop")
    if policy.get("lifecycle_transition_write_allowed") is not True:
        raise ValueError("lifecycle transition write must be allowed for scheduler execution")
    if policy.get("canonical_content_write_allowed") is not False:
        raise ValueError("canonical content write is not allowed")
    if policy.get("physical_delete_allowed") is not False:
        raise ValueError("physical delete is not allowed")
    if policy.get("raw_provider_material_included") is not False:
        raise ValueError("raw provider material is not allowed")
    if policy.get("local_filesystem_path_included") is not False:
        raise ValueError("local filesystem paths are not allowed")

    proposal_loops = [dict(loop) for loop in run["proposal_loops"]]
    transition_results = [dict(result) for result in run["transition_results"]]
    if int(run["proposal_loop_count"]) != len(proposal_loops):
        raise ValueError("proposal_loop_count mismatch")
    if int(run["executed_transition_count"]) != len(transition_results):
        raise ValueError("executed_transition_count mismatch")
    if int(run["proposal_only_transition_count"]) != 0:
        raise ValueError("proposal-only transitions were not executed by scheduler")
    if not proposal_loops or not transition_results:
        raise ValueError("scheduler run requires proposal loops and transition results")

    for loop in proposal_loops:
        validate_lifecycle_candidate_lint_loop(loop)

    for result in transition_results:
        if result.get("transition_execution_status") != "executed_by_scheduler":
            raise ValueError("transition must be executed by scheduler")
        if result.get("request_status_before_execution") != "pending_gate_review":
            raise ValueError("scheduler execution must consume pending gate review requests")
        if result.get("candidate_status_before_execution") != "proposed":
            raise ValueError("scheduler execution must consume proposed candidates")
        if result.get("lifecycle_review_required_before_execution") is not True:
            raise ValueError("scheduler execution must preserve review provenance")
        if result.get("lifecycle_transition_write_allowed") is not True:
            raise ValueError("lifecycle transition write must be allowed for scheduler execution")
        if result.get("canonical_content_write_allowed") is not False:
            raise ValueError("canonical content write is not allowed")
        if result.get("physical_delete_allowed") is not False:
            raise ValueError("physical delete is not allowed")
        if result.get("traceability_preserved") is not True:
            raise ValueError("traceability must be preserved")
        applied = dict(result["applied_transition"])
        if applied.get("lifecycle_state") != result.get("target_lifecycle_state"):
            raise ValueError("applied transition state mismatch")
        if applied.get("physical_delete_allowed") is not False:
            raise ValueError("physical delete is not allowed")
        if applied.get("traceability_preserved") is not True:
            raise ValueError("traceability must be preserved")
        validate_vault_record_lifecycle(applied)

    unsafe_tokens = _unsafe_serialized_tokens(run)
    if unsafe_tokens:
        raise ValueError(f"unsafe scheduler run material included: {', '.join(unsafe_tokens)}")


def build_gardener_lifecycle_scheduler_run(
    *,
    active_records: Sequence[Mapping[str, Any]],
    candidate_findings: Sequence[Mapping[str, Any]],
    scheduler_id: str,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """Execute Gardener stale/superseded transitions from scheduled proposals.

    The existing lint loop remains proposal-only. This scheduler facade uses
    those typed proposals as the input audit trail, then records the lifecycle
    transition result without authorizing canonical content writes or physical
    deletion.
    """

    scheduler = _require_text("scheduler_id", scheduler_id)
    scheduled = scheduled_at or utc_now_iso()
    records_by_id = _active_records_by_canonical_id(active_records)
    findings = [
        dict(finding)
        for finding in candidate_findings
        if isinstance(finding, Mapping) and dict(finding)
    ]
    if not findings:
        raise ValueError("candidate_findings are required")

    proposal_loops: list[dict[str, Any]] = []
    transition_results: list[dict[str, Any]] = []
    for finding in findings:
        canonical_record_id = _require_text("canonical_record_id", finding.get("canonical_record_id"))
        active = records_by_id.get(canonical_record_id)
        if active is None:
            raise ValueError("candidate finding references an unknown active record")
        loop = build_lifecycle_candidate_lint_loop(
            active_record=active,
            candidate_findings=[finding],
            requested_at=scheduled,
        )
        candidate_result = dict(loop["candidate_results"][0])
        proposal_loops.append(loop)
        transition_results.append(
            _scheduler_transition_result(
                loop=loop,
                candidate_result=candidate_result,
                scheduler_id=scheduler,
                scheduled_at=scheduled,
            )
        )

    run = {
        "schema_version": "gardener_lifecycle_scheduler_run.v1",
        "scheduler_run_id": uuid.uuid4().hex,
        "run_status": "transitions_executed",
        "scheduler_triggered": True,
        "scheduler_id": scheduler,
        "scheduled_at": scheduled,
        "proposal_loop_count": len(proposal_loops),
        "executed_transition_count": len(transition_results),
        "proposal_only_transition_count": 0,
        "proposal_loops": proposal_loops,
        "transition_results": transition_results,
        "execution_policy": {
            "trigger_kind": "scheduler_tick",
            "proposal_source": "lifecycle_candidate_lint_loop",
            "lifecycle_transition_write_allowed": True,
            "canonical_content_write_allowed": False,
            "physical_delete_allowed": False,
            "raw_provider_material_included": False,
            "local_filesystem_path_included": False,
        },
        "reason_codes": [
            "gardener_lifecycle_scheduler_ran",
            "stale_and_superseded_transitions_executed",
            "proposal_loop_audit_preserved",
            "canonical_content_write_not_authorized",
            "physical_delete_not_authorized",
        ],
        "created_at": scheduled,
    }
    validate_gardener_lifecycle_scheduler_run(run)
    return run
