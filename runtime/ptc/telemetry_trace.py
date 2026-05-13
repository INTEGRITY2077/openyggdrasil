from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.engine_contracts import *  # noqa: F401,F403
from runtime.ptc.engine_contracts import (  # noqa: F401
    _assert_additive_only_hard_nonclaims,
    _safe_portable_ref,
)
from runtime.ptc.base_utils import *  # noqa: F401,F403

def build_pathfinder_ptc_routing_trace(
    *,
    query_ref: str,
    support_bundle_ref: str,
    ptc_trace_ref: str,
    route_id: str | None = None,
    approved_routing_fact_ref: str | None = None,
    approved_effort: str = PATHFINDER_RUNTIME_APPROVED_EFFORT,
    lease_group: str = PATHFINDER_RUNTIME_LEASE_GROUP,
    provider_route_summary: str | None = None,
    selected_memory_refs: Sequence[Mapping[str, Any]] | None = None,
    rejected_memory_refs: Sequence[Mapping[str, Any]] | None = None,
    evidence_refs: Sequence[Mapping[str, Any]] | None = None,
    advisory_effort: str | None = None,
    evidence_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Project Pathfinder/PTC trace refs into a route trace for Hermes receipt building.

    This trace carries only safe refs and routing metadata. It does not claim
    live provider readiness or solve Reasoning Lease execution.
    """

    token = _route_token(query_ref, support_bundle_ref, ptc_trace_ref)
    active_route_id = route_id or f"route-pathfinder-ptc-{token}"
    active_fact_ref = (
        approved_routing_fact_ref
        or f"approved-routing-fact-ref://openyggdrasil/pathfinder-ptc/{active_route_id}"
    )
    active_evidence_id = evidence_id or f"ptc-trace-{token[:16]}"
    advisory = str(advisory_effort or "").strip() or None
    override_applied = bool(advisory and advisory != approved_effort)
    reason_codes = [
        "pathfinder_ptc_trace_linked_to_route",
        "runtime_authoritative_route",
        "skill_body_excluded",
    ]
    if override_applied:
        reason_codes.append("runtime_authoritative_override_advisory_effort_mismatch")

    return {
        "schema_version": "pathfinder_ptc_routing_trace.v1",
        "route_id": active_route_id,
        "evidence_id": active_evidence_id,
        "approved_routing_fact_ref": active_fact_ref,
        "query_ref": query_ref,
        "support_bundle_ref": support_bundle_ref,
        "ptc_trace_ref": ptc_trace_ref,
        "runtime_authoritative": True,
        "approved_effort": approved_effort,
        "lease_group": lease_group,
        "provider_route_summary": provider_route_summary
        or "Use the runtime-approved Pathfinder support bundle route with provenance refs.",
        "selected_memory_refs": list(
            selected_memory_refs
            or [
                {
                    "ref": support_bundle_ref,
                    "role": "support_bundle_source",
                    "reason_code": "runtime_approved_route",
                },
                {
                    "ref": ptc_trace_ref,
                    "role": "ptc_trace",
                    "reason_code": "programmatic_tool_runtime_trace",
                },
            ]
        ),
        "rejected_memory_refs": list(rejected_memory_refs or []),
        "evidence_refs": list(
            evidence_refs
            or [
                {
                    "evidence_id": active_evidence_id,
                    "ref": ptc_trace_ref,
                    "evidence_kind": "ptc_trace",
                    "pointer_accounting_key": "ptc_trace_ref",
                },
                {
                    "evidence_id": f"support-bundle-{token[:16]}",
                    "ref": support_bundle_ref,
                    "evidence_kind": "support_bundle",
                    "pointer_accounting_key": "support_bundle_ref",
                },
            ]
        ),
        "runtime_authoritative_override": {
            "override_applied": override_applied,
            "advisory_effort": advisory,
            "approved_effort": approved_effort,
            "lease_group": lease_group,
            "reason_code": (
                "runtime_authoritative_override_advisory_effort_mismatch"
                if override_applied
                else "runtime_authoritative_route"
            ),
        },
        "skill_body_included": False,
        "raw_provider_material_included": False,
        "portable_local_path_included": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "target_readiness_claimed": False,
        "reason_codes": reason_codes,
        "generated_at": generated_at or _utc_now_iso(),
    }

def build_role_polymorphic_ptc_telemetry_trace(
    *,
    same_run_context: Mapping[str, Any],
    ptc_trace_ref: str,
    reasoning_lease_ref: str,
    typed_task_ref: str,
    role_manifest_refs: Mapping[str, Any],
    role_prompt_context_refs: Mapping[str, Any],
    role_execution_refs: Mapping[str, Any],
    typed_result_ref: str | None = None,
    typed_unavailable_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a bounded role-polymorphic PTC telemetry candidate.

    The trace records typed same-run refs and prompt-context refs only. It does
    not include raw prompt bodies, claim provider answer quality, or claim final
    production PTC implementation.
    """

    normalized_context = _normalize_same_run_ptc_context(same_run_context)
    active_ptc_trace_ref = _safe_portable_ref(ptc_trace_ref, field_name="ptc_trace_ref")
    active_reasoning_lease_ref = _safe_portable_ref(
        reasoning_lease_ref,
        field_name="reasoning_lease_ref",
    )
    active_typed_task_ref = _safe_portable_ref(typed_task_ref, field_name="typed_task_ref")
    active_typed_result_ref = (
        _safe_portable_ref(typed_result_ref, field_name="typed_result_ref")
        if typed_result_ref is not None
        else None
    )
    active_typed_unavailable_ref = (
        _safe_portable_ref(typed_unavailable_ref, field_name="typed_unavailable_ref")
        if typed_unavailable_ref is not None
        else None
    )
    if active_typed_result_ref is None and active_typed_unavailable_ref is None:
        raise ValueError("typed_result_ref or typed_unavailable_ref is required")

    manifests = _normalize_role_map(role_manifest_refs, field_name="role_manifest_refs")
    prompt_contexts = _normalize_role_map(
        role_prompt_context_refs,
        field_name="role_prompt_context_refs",
    )
    execution_refs = _normalize_role_map(role_execution_refs, field_name="role_execution_refs")

    token = _route_token(
        normalized_context["same_run_id"],
        active_ptc_trace_ref,
        active_reasoning_lease_ref,
        tuple(manifests.items()),
        tuple(prompt_contexts.items()),
        tuple(execution_refs.items()),
    )
    role_rows = [
        {
            "role": role,
            "persona_manifest_ref": manifests[role],
            "prompt_context_ref": prompt_contexts[role],
            "role_execution_ref": execution_refs[role],
            "reasoning_lease_ref": active_reasoning_lease_ref,
            "typed_task_ref": active_typed_task_ref,
            "status": "same_run_role_prompt_context_referenced",
            "persona_manifest_ref_in_prompt_context": True,
            "prompt_surface_included": False,
            "safe_refs_only": True,
        }
        for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES
    ]
    trace = {
        "schema_version": ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION,
        "telemetry_id": f"ptc-role-polymorphic-telemetry-{token}",
        "telemetry_ref": f"ptc-telemetry-ref://openyggdrasil/role-polymorphic/{token}",
        "telemetry_status": ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS,
        "claim_scope": ROLE_POLYMORPHIC_PTC_CLAIM_SCOPE,
        "same_run_context_status": "accepted",
        "same_run_context": normalized_context,
        "ptc_trace_ref": active_ptc_trace_ref,
        "reasoning_lease_ref": active_reasoning_lease_ref,
        "typed_task_ref": active_typed_task_ref,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "required_roles": list(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES),
        "role_prompt_contexts": role_rows,
        "role_count": len(role_rows),
        "role_polymorphic": True,
        "all_required_roles_covered": True,
        "persona_manifests_referenced_by_prompt_context": True,
        "runtime_authoritative": True,
        "skill_body_included": False,
        "raw_provider_material_included": False,
        "portable_local_path_included": False,
        "thin_worker_chain_relabelled_as_ptc": False,
        "static_bridge_relabelled_as_execution": False,
        "reasoning_lease_solved_claimed": False,
        "r10_complete_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "production_ptc_implemented_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "background_live_integration_claimed": False,
        "hermes_answer_quality_claimed": False,
        "consumer_ux_complete_claimed": False,
        "wiki_production_safety_complete_claimed": False,
        "full_product_readiness_claimed": False,
        "reason_codes": [
            "minimal_role_polymorphic_ptc_telemetry_built",
            "same_run_context_refs_accepted",
            "persona_manifest_refs_linked_to_prompt_context_refs",
            "all_required_roles_covered",
            "production_ptc_not_claimed",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_role_polymorphic_ptc_telemetry_trace(trace)
    return trace

def validate_role_polymorphic_ptc_telemetry_trace(payload: Mapping[str, Any]) -> None:
    trace = dict(payload)
    if trace.get("schema_version") != ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION:
        raise ValueError("invalid role-polymorphic PTC telemetry schema_version")
    if trace.get("telemetry_status") != ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS:
        raise ValueError("invalid role-polymorphic PTC telemetry status")
    if trace.get("claim_scope") != ROLE_POLYMORPHIC_PTC_CLAIM_SCOPE:
        raise ValueError("invalid role-polymorphic PTC claim_scope")
    if trace.get("same_run_context_status") != "accepted":
        raise ValueError("same-run role-polymorphic PTC telemetry requires accepted context")
    _normalize_same_run_ptc_context(trace.get("same_run_context") or {})
    for field in (
        "telemetry_ref",
        "ptc_trace_ref",
        "reasoning_lease_ref",
        "typed_task_ref",
    ):
        _safe_portable_ref(trace.get(field), field_name=field)
    if trace.get("typed_result_ref") is None and trace.get("typed_unavailable_ref") is None:
        raise ValueError("typed result or typed unavailable ref is required")
    if trace.get("typed_result_ref") is not None:
        _safe_portable_ref(trace.get("typed_result_ref"), field_name="typed_result_ref")
    if trace.get("typed_unavailable_ref") is not None:
        _safe_portable_ref(trace.get("typed_unavailable_ref"), field_name="typed_unavailable_ref")
    role_rows = trace.get("role_prompt_contexts")
    if not isinstance(role_rows, Sequence) or isinstance(role_rows, (str, bytes)):
        raise ValueError("role_prompt_contexts must be a list")
    roles = [str(row.get("role") or "") for row in role_rows if isinstance(row, Mapping)]
    if roles != list(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES):
        raise ValueError("role_prompt_contexts must cover required roles in order")
    if trace.get("role_count") != len(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES):
        raise ValueError("role_count must match required role count")
    if trace.get("required_roles") != list(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES):
        raise ValueError("required_roles must match role-polymorphic PTC roles")
    if trace.get("all_required_roles_covered") is not True:
        raise ValueError("all required roles must be covered")
    if trace.get("persona_manifests_referenced_by_prompt_context") is not True:
        raise ValueError("persona manifest refs must be linked to prompt context refs")
    for index, row in enumerate(role_rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"role_prompt_contexts[{index}] must be an object")
        for field in (
            "persona_manifest_ref",
            "prompt_context_ref",
            "role_execution_ref",
            "reasoning_lease_ref",
            "typed_task_ref",
        ):
            _safe_portable_ref(row.get(field), field_name=f"role_prompt_contexts[{index}].{field}")
        if row.get("persona_manifest_ref_in_prompt_context") is not True:
            raise ValueError("role prompt context must reference persona manifest")
        if row.get("prompt_surface_included") is not False:
            raise ValueError("role prompt context must not copy prompt surface")
        if row.get("safe_refs_only") is not True:
            raise ValueError("role prompt context must use safe refs only")
    for flag in (
        "skill_body_included",
        "raw_provider_material_included",
        "portable_local_path_included",
        "thin_worker_chain_relabelled_as_ptc",
        "static_bridge_relabelled_as_execution",
        "reasoning_lease_solved_claimed",
        "r10_complete_claimed",
        "live_readiness_claimed",
        "production_readiness_claimed",
        "production_ptc_implemented_claimed",
        "public_runtime_integration_complete_claimed",
        "background_live_integration_claimed",
        "hermes_answer_quality_claimed",
        "consumer_ux_complete_claimed",
        "wiki_production_safety_complete_claimed",
        "full_product_readiness_claimed",
    ):
        if trace.get(flag) is not False:
            raise ValueError(f"unsafe role-polymorphic PTC flag: {flag}")

def _role_execution_refs_from_ptc_telemetry(
    ptc_telemetry_trace: Mapping[str, Any],
) -> dict[str, str]:
    validate_role_polymorphic_ptc_telemetry_trace(ptc_telemetry_trace)
    role_rows = ptc_telemetry_trace.get("role_prompt_contexts") or []
    return {
        str(row["role"]): str(row["role_execution_ref"])
        for row in role_rows
        if isinstance(row, Mapping)
    }


__all__ = [
    "build_pathfinder_ptc_routing_trace",
    "build_role_polymorphic_ptc_telemetry_trace",
    "validate_role_polymorphic_ptc_telemetry_trace",
    "_role_execution_refs_from_ptc_telemetry",
]
