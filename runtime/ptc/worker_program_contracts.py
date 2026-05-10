"""Worker-owned PTC program contracts.

These helpers make the TST/PTC lane prove more than "a result exists".
They keep the proof machine-readable: the worker program is reviewed before
execution and the observation must structurally change the next action.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


WORKER_PROGRAM_SCHEMA_VERSION = "worker_authored_ptc_program.v1"
PROGRAM_REVIEW_SCHEMA_VERSION = "ptc_program_review.v1"
TST_ALLOWLIST_SCHEMA_VERSION = "tst_capability_allowlist.v1"
PROGRAM_OBSERVATION_SCHEMA_VERSION = "ptc_program_observation.v1"
OBSERVATION_DELTA_SCHEMA_VERSION = "observation_delta_gate.v1"


MS_CANONICAL_FLOW = [
    "source_anchor_check",
    "extract_decisions",
    "build_spo_triples",
    "build_vault_node",
    "check_near_duplicate_or_supersession",
    "validate_admission",
    "save_to_vault",
]

MF_CANONICAL_FLOW = [
    "query_anchor_check",
    "candidate_generation",
    "source_provenance_read",
    "candidate_rerank_hard_gate",
    "support_or_typed_unavailable",
]

MF_CAPABILITY_GROUPS = {
    "candidate_generation": {
        "locate_region",
        "select_topic_anchor",
        "search_vault_bm25",
        "keyword_search",
        "korean_expansion",
        "edge_lookup",
        "community_lookup",
        "recent_episode_lookup",
        "source_ref_lookup",
    },
    "source_provenance_read": {
        "read_origin_claims",
        "read_recent_claims",
        "collect_claim_ids",
        "read_source_paths",
        "provenance_ring_lookup",
    },
    "candidate_rerank_hard_gate": {
        "candidate_feature_vector",
        "candidate_reranker",
        "recall_verifier",
    },
    "support_or_typed_unavailable": {
        "assemble_support_bundle",
        "assemble_unanchored_bundle",
        "normalize_support_receipt",
        "recall_permission_decision",
        "source_exposure_permission",
    },
}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _ids(rows: Sequence[Any]) -> list[str]:
    values: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            value = row.get("tool_id") or row.get("capability_id")
        else:
            value = row
        text = str(value or "").strip()
        if text:
            values.append(text)
    return values


def _ordered_contains(actual: Sequence[str], required: Sequence[str]) -> bool:
    cursor = 0
    for item in actual:
        if cursor < len(required) and item == required[cursor]:
            cursor += 1
    return cursor == len(required)


def _mf_canonical_steps_supported(capability_ids: Sequence[str]) -> bool:
    selected = set(capability_ids)
    return all(selected & group for group in MF_CAPABILITY_GROUPS.values())


def build_worker_authored_ptc_program(
    *,
    worker_role: str,
    work_order_ref: Mapping[str, Any] | str,
    self_defined_goal: str,
    requested_capabilities: Sequence[str],
    program_steps: Sequence[str],
    program_mode: str = "canonical_flow",
    success_condition: Sequence[str] | None = None,
    failure_condition: Sequence[str] | None = None,
    observation_targets: Sequence[str] | None = None,
    retry_plan: Mapping[str, Any] | None = None,
    reviewed_extension: Mapping[str, Any] | None = None,
    hard_nonclaims: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a provider-safe worker program receipt section."""
    role = str(worker_role or "").strip()
    mode = str(program_mode or "canonical_flow").strip()
    return {
        "schema_version": WORKER_PROGRAM_SCHEMA_VERSION,
        "worker_role": role,
        "work_order_ref": work_order_ref,
        "self_defined_goal": str(self_defined_goal or "").strip(),
        "success_condition": list(success_condition or [
            "source_or_provenance_backed_evidence_present",
            "role_scoped_capabilities_completed",
            "result_does_not_exceed_evidence",
        ]),
        "failure_condition": list(failure_condition or [
            "missing_source_or_provenance_evidence",
            "misaligned_support_or_save_candidate",
            "retry_would_repeat_same_angle",
        ]),
        "program_mode": mode,
        "requested_capabilities": [str(item) for item in requested_capabilities if str(item)],
        "program_steps": [str(item) for item in program_steps if str(item)],
        "observation_targets": list(observation_targets or [
            "tool_result_events",
            "source_or_write_evidence",
            "alignment_judgment",
            "next_action_candidate",
        ]),
        "retry_plan": dict(retry_plan or {
            "same_angle_retry_allowed": False,
            "changed_angle_required_when_weak": True,
        }),
        "reviewed_extension": dict(reviewed_extension or {}),
        "hard_nonclaims": list(hard_nonclaims or [
            "program_text_is_not_execution_success",
            "postman_delivery_is_not_semantic_success",
            "changed_next_action_self_claim_is_not_enough",
        ]),
    }


def review_ptc_program(
    program: Mapping[str, Any],
    *,
    selected_capability_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a worker-authored PTC program before execution."""
    role = str(program.get("worker_role") or "")
    mode = str(program.get("program_mode") or "")
    steps = [str(item) for item in _as_list(program.get("program_steps")) if str(item)]
    requested = [str(item) for item in _as_list(program.get("requested_capabilities")) if str(item)]
    selected = set(str(item) for item in (selected_capability_ids or requested) if str(item))
    goal = str(program.get("self_defined_goal") or "").strip()
    work_order_ref = program.get("work_order_ref")

    failures: list[str] = []
    goal_alignment = {
        "status": "pass" if goal and work_order_ref else "weak",
        "reason": "goal_and_work_order_ref_present" if goal and work_order_ref else "missing_goal_or_work_order_ref",
    }
    if goal_alignment["status"] != "pass":
        failures.append("program_rejected_unaligned_goal")

    missing_scope = [capability_id for capability_id in requested if selected and capability_id not in selected]
    capability_scope_check = {
        "status": "pass" if not missing_scope else "weak",
        "missing_from_allowlist": missing_scope,
    }
    if missing_scope:
        failures.append("program_rejected_capability_outside_allowlist")

    if role == "memory_saver":
        order_ok = _ordered_contains(steps, MS_CANONICAL_FLOW)
    elif role == "memory_finder":
        order_ok = steps == MF_CANONICAL_FLOW or _mf_canonical_steps_supported(requested)
    else:
        order_ok = False
    step_order_check = {
        "status": "pass" if order_ok else "weak",
        "expected": MS_CANONICAL_FLOW if role == "memory_saver" else MF_CANONICAL_FLOW,
        "actual": steps,
    }
    if not order_ok:
        failures.append("program_rejected_invalid_capability_order")

    evidence_text = " ".join(
        str(item)
        for item in [
            *_as_list(program.get("success_condition")),
            *_as_list(program.get("failure_condition")),
            *_as_list(program.get("observation_targets")),
        ]
    ).lower()
    evidence_ok = any(marker in evidence_text for marker in ["source", "provenance", "evidence"])
    evidence_gate_check = {
        "status": "pass" if evidence_ok else "weak",
        "requires_source_or_provenance_language": True,
    }
    if not evidence_ok:
        failures.append("program_rejected_missing_evidence_gate")

    retry_plan = program.get("retry_plan") if isinstance(program.get("retry_plan"), Mapping) else {}
    repetition_allowed = bool(retry_plan.get("same_angle_retry_allowed"))
    changed_angle_required = retry_plan.get("changed_angle_required_when_weak", True) is True
    retry_ok = not repetition_allowed and changed_angle_required
    retry_plan_check = {
        "status": "pass" if retry_ok else "weak",
        "same_angle_retry_allowed": repetition_allowed,
        "changed_angle_required_when_weak": changed_angle_required,
    }
    if not retry_ok:
        failures.append("program_rejected_retry_is_repetition")

    extension_review = {"status": "not_applicable"}
    if mode == "reviewed_extension":
        extension = program.get("reviewed_extension") if isinstance(program.get("reviewed_extension"), Mapping) else {}
        required = [
            "why_canonical_flow_is_insufficient",
            "proposed_step_order",
            "required_capabilities",
            "new_risk",
            "evidence_needed",
            "rollback_or_typed_unavailable_plan",
        ]
        missing = [key for key in required if not extension.get(key)]
        extension_review = {
            "status": "pass" if not missing else "weak",
            "missing_required_fields": missing,
        }
        if missing:
            failures.append("program_rejected_extension_without_risk_plan")
    elif mode != "canonical_flow":
        failures.append("program_rejected_unknown_program_mode")

    return {
        "schema_version": PROGRAM_REVIEW_SCHEMA_VERSION,
        "review_status": "accepted" if not failures else "rejected",
        "program_mode": mode,
        "goal_alignment": goal_alignment,
        "capability_scope_check": capability_scope_check,
        "step_order_check": step_order_check,
        "evidence_gate_check": evidence_gate_check,
        "retry_plan_check": retry_plan_check,
        "extension_review": extension_review,
        "rejection_reason": failures,
        "hard_nonclaims": [
            "accepted_review_is_not_execution_success",
            "canonical_flow_is_p0_guard_not_full_autonomy",
        ],
    }


def build_tst_capability_allowlist(
    *,
    worker_role: str,
    selected_capabilities: Sequence[Mapping[str, Any]],
    requested_capabilities: Sequence[str],
) -> dict[str, Any]:
    selected_ids = _ids(selected_capabilities)
    selected = set(selected_ids)
    requested = [str(item) for item in requested_capabilities if str(item)]
    rejected = [item for item in requested if item not in selected]
    return {
        "schema_version": TST_ALLOWLIST_SCHEMA_VERSION,
        "worker_role": worker_role,
        "selected_capabilities": selected_ids,
        "rejected_capabilities": rejected,
        "role_scope_reason": "role_scoped_catalog_records_only",
        "required_evidence_refs": [
            "tool_use_events",
            "ptc_program_review.v1",
            "ptc_program_observation.v1",
        ],
        "adapter_status": {
            str(row.get("tool_id") or row.get("capability_id")): row.get("adapter_status")
            for row in selected_capabilities
            if isinstance(row, Mapping)
        },
    }


def build_ptc_program_observation(
    *,
    program: Mapping[str, Any],
    tool_use_events: Sequence[Mapping[str, Any]],
    evaluation: Mapping[str, Any],
    result_summary: Mapping[str, Any] | None = None,
    alignment_judgment: str | None = None,
) -> dict[str, Any]:
    completed = [
        str(row.get("capability_id"))
        for row in tool_use_events
        if row.get("type") == "tool_result" and row.get("status") == "completed"
    ]
    selected = [str(item) for item in _as_list(program.get("requested_capabilities")) if str(item)]
    missing = [item for item in selected if item not in completed]
    quality = str(evaluation.get("quality") or "weak")
    next_action = "continue_with_result" if quality == "pass" and not missing else "typed_unavailable"
    if missing and program.get("retry_plan", {}).get("changed_angle_required_when_weak", True):
        next_action = "retry_with_changed_angle"
    return {
        "schema_version": PROGRAM_OBSERVATION_SCHEMA_VERSION,
        "executed_steps": completed,
        "tool_observations": [
            {
                "capability_id": row.get("capability_id"),
                "status": row.get("status"),
                "result_ref_present": bool(row.get("result_ref")),
                "result_hash_present": bool(row.get("result_sha256")),
            }
            for row in tool_use_events
            if row.get("type") == "tool_result"
        ],
        "evidence_found": {
            "completed_tool_count": len(completed),
            "result_summary": dict(result_summary or {}),
        },
        "evidence_missing": missing,
        "alignment_judgment": alignment_judgment or ("aligned" if quality == "pass" else "weak_or_incomplete"),
        "next_action_candidate": next_action,
    }


def build_observation_delta_gate(
    *,
    program: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    before = "execute_reviewed_program"
    after = str(observation.get("next_action_candidate") or "typed_unavailable")
    missing = list(observation.get("evidence_missing") or [])
    structural_diff = before != after
    weak_without_retry = bool(missing) and after == "continue_with_result"
    repeated_retry = after == "retry_with_changed_angle" and not program.get("retry_plan", {}).get(
        "changed_angle_required_when_weak",
        True,
    )
    passed = structural_diff and not weak_without_retry and not repeated_retry
    return {
        "schema_version": OBSERVATION_DELTA_SCHEMA_VERSION,
        "before_action_intent": str(program.get("self_defined_goal") or ""),
        "expected_observation": list(program.get("observation_targets") or []),
        "actual_observation": {
            "alignment_judgment": observation.get("alignment_judgment"),
            "next_action_candidate": after,
        },
        "missing_evidence": missing,
        "unexpected_evidence": [],
        "alignment_change": "observation_to_next_action" if structural_diff else "no_structural_change",
        "next_action_before": before,
        "next_action_after": after,
        "change_type": after,
        "change_reason_refs": [
            "ptc_program_observation.v1",
            "tool_use_events",
        ],
        "self_claim_accepted": False,
        "delta_verified": passed,
        "quality": "pass" if passed else "weak",
        "failure_reasons": [
            reason
            for reason, active in [
                ("no_structural_next_action_diff", not structural_diff),
                ("weak_evidence_cannot_continue_with_result", weak_without_retry),
                ("retry_repeats_same_angle", repeated_retry),
            ]
            if active
        ],
    }


__all__ = [
    "MF_CANONICAL_FLOW",
    "MS_CANONICAL_FLOW",
    "build_observation_delta_gate",
    "build_ptc_program_observation",
    "build_tst_capability_allowlist",
    "build_worker_authored_ptc_program",
    "review_ptc_program",
]
