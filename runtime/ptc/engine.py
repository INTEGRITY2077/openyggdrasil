"""PTC engine primitives extracted behind compatibility-preserving imports."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE = "structural_anchor_fallback_without_hermes"
QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION = "ptc_query_adaptive_pathfinder_plan.v1"
QUERY_ADAPTIVE_PLAN_STATUS = "bounded_query_adaptive"
MAX_PATHFINDER_TOOL_STEP_COUNT = 6
MAX_PATHFINDER_JSON_TOOL_STEP_COUNT = 7
DEFAULT_MAX_RECENT_LIMIT = 8
LEASE_BACKED_LLM_PLANNER_MODE = "lease_backed_llm_dynamic_assembly"
EXTERNAL_LLM_PLANNER_MODE = "external_llm_dynamic_assembly"
DETERMINISTIC_PLANNER_MODE = "deterministic_query_signals"
FALLBACK_PLANNER_MODE = "deterministic_fallback_after_llm_failure"
PATHFINDER_RUNTIME_APPROVED_EFFORT = "high"
PATHFINDER_RUNTIME_LEASE_GROUP = "semantic_routing"
ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION = "ptc_role_polymorphic_telemetry.v1"
ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS = "same_run_role_prompt_context_ready"
ROLE_POLYMORPHIC_PTC_CLAIM_SCOPE = (
    "minimal_ptc_telemetry_candidate_not_production_ptc_implemented"
)
ROLE_POLYMORPHIC_SAME_RUN_SOURCE_KIND = "physical_live_same_run"
ROLE_POLYMORPHIC_EVIDENCE_CHAIN_STATUS = "upstream_verified"
REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES = (
    "distiller",
    "evaluator",
    "amundsen",
    "pathfinder",
    "postman",
    "map_maker",
    "gardener",
    "receipt_consumer",
)
SAFE_PORTABLE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
UNSAFE_PORTABLE_REF_TOKENS = (
    "file://",
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    ".skill.md",
    "transcript.txt",
    "transcripts/",
    "auth.json",
    ".env",
)

PATHFINDER_JSON_TOOL_CAPABILITIES = {
    "locate_region",
    "select_topic_anchor",
    "read_origin_claims",
    "read_recent_claims",
    "collect_claim_ids",
    "read_source_paths",
    "assemble_support_bundle",
    "assemble_unanchored_bundle",
}

RECENCY_TERMS = {
    "recent",
    "recently",
    "latest",
    "current",
    "changed",
    "change",
    "today",
    "yesterday",
    "new",
}
COMPARISON_TERMS = {
    "compare",
    "conflict",
    "conflicts",
    "versus",
    "vs",
    "stale",
    "superseded",
    "supersession",
}
ORIGIN_TERMS = {"origin", "first", "initial", "root", "source"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _route_token(*values: Any) -> str:
    encoded = "|".join(str(value) for value in values).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


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


def _safe_portable_ref(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    lowered = text.lower().replace("\\", "/")
    if not SAFE_PORTABLE_REF_RE.match(text):
        raise ValueError(f"{field_name} must be a safe portable ref")
    if any(token.replace("\\", "/") in lowered for token in UNSAFE_PORTABLE_REF_TOKENS):
        raise ValueError(f"{field_name} contains unsafe provider material")
    return text


def _safe_identifier(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128 or not re.match(r"^[A-Za-z0-9._:-]+$", text):
        raise ValueError(f"{field_name} must be a safe identifier")
    return text


def _normalize_role_map(
    values: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a role ref map")
    normalized = {str(key).strip().lower().replace("-", "_"): value for key, value in values.items()}
    missing = [role for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES if role not in normalized]
    if missing:
        raise ValueError(f"{field_name} missing required roles: {', '.join(missing)}")
    return {
        role: _safe_portable_ref(normalized[role], field_name=f"{field_name}.{role}")
        for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES
    }


def _normalize_same_run_ptc_context(same_run_context: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(same_run_context, Mapping):
        raise ValueError("same_run_context must be an object")
    allowed = {
        "same_run_id",
        "same_run_witness_ref",
        "same_run_source_kind",
        "evidence_chain_status",
        "mailbox_delivery_ref",
        "hermes_consumption_ref",
        "ptc_trace_ref",
        "bubblewrap_trace_ref",
        "producer_receipt_ref",
        "consumer_usage_ref",
    }
    unknown = sorted(str(key) for key in set(same_run_context) - allowed)
    if unknown:
        raise ValueError(f"same_run_context has unsupported keys: {', '.join(unknown)}")
    normalized = {
        "same_run_id": _safe_identifier(
            same_run_context.get("same_run_id"),
            field_name="same_run_context.same_run_id",
        ),
        "same_run_witness_ref": _safe_portable_ref(
            same_run_context.get("same_run_witness_ref"),
            field_name="same_run_context.same_run_witness_ref",
        ),
        "same_run_source_kind": str(same_run_context.get("same_run_source_kind") or "").strip(),
        "evidence_chain_status": str(same_run_context.get("evidence_chain_status") or "").strip(),
    }
    if normalized["same_run_source_kind"] != ROLE_POLYMORPHIC_SAME_RUN_SOURCE_KIND:
        raise ValueError("same_run_context.same_run_source_kind must be physical_live_same_run")
    if normalized["evidence_chain_status"] != ROLE_POLYMORPHIC_EVIDENCE_CHAIN_STATUS:
        raise ValueError("same_run_context.evidence_chain_status must be upstream_verified")
    for key in sorted(allowed - set(normalized)):
        if key in same_run_context:
            normalized[key] = _safe_portable_ref(
                same_run_context[key],
                field_name=f"same_run_context.{key}",
            )
    return normalized


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


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _query_terms(query_text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query_text)}


def render_default_pathfinder_program(*, recent_limit: int) -> str:
    return (
        "region = tools['find_region'](query_text=query_text)\n"
        "anchor = tools['find_topic_anchor'](query_text=query_text, region_id=region['region_id'])\n"
        "if anchor['topic_id'] is None:\n"
        "    RESULT = tools['build_unanchored_bundle'](query_text=query_text)\n"
        "else:\n"
        "    origin_rows = tools['get_origin_claims'](topic_id=anchor['topic_id'], limit=1)\n"
        f"    recent_rows = tools['get_recent_episodes'](topic_id=anchor['topic_id'], limit={max(1, recent_limit)})\n"
        "    claim_ids = [row['claim_id'] for row in recent_rows + origin_rows if row.get('claim_id')]\n"
        "    source_paths = tools['get_raw_sources'](topic_id=anchor['topic_id'], claim_ids=claim_ids)\n"
        "    RESULT = tools['build_support_bundle'](\n"
        "        query_text=query_text,\n"
        "        anchor=anchor,\n"
        "        origin_rows=origin_rows,\n"
        "        recent_rows=recent_rows,\n"
        "        source_paths=source_paths,\n"
        "    )\n"
    )


def render_default_pathfinder_json_plan(*, recent_limit: int) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "region",
            "capability_id": "locate_region",
            "input": {"query_text": {"from_context": "query_text"}},
        },
        {
            "step_id": "anchor",
            "capability_id": "select_topic_anchor",
            "input": {
                "query_text": {"from_context": "query_text"},
                "region_id": {"from_step": "region", "path": ["region_id"]},
            },
        },
        {
            "step_id": "origin",
            "capability_id": "read_origin_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": 1},
            },
        },
        {
            "step_id": "recent",
            "capability_id": "read_recent_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": max(1, recent_limit)},
            },
        },
        {
            "step_id": "claim_ids",
            "capability_id": "collect_claim_ids",
            "input": {
                "recent_rows": {"from_step": "recent"},
                "origin_rows": {"from_step": "origin"},
            },
        },
        {
            "step_id": "sources",
            "capability_id": "read_source_paths",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "claim_ids": {"from_step": "claim_ids"},
            },
        },
        {
            "step_id": "bundle",
            "capability_id": "assemble_support_bundle",
            "input": {
                "query_text": {"from_context": "query_text"},
                "anchor": {"from_step": "anchor"},
                "origin_rows": {"from_step": "origin"},
                "recent_rows": {"from_step": "recent"},
                "source_paths": {"from_step": "sources"},
            },
        },
    ]


def validate_pathfinder_json_tool_plan(plan: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(plan, Sequence) or isinstance(plan, (str, bytes)):
        raise ValueError("pathfinder JSON tool plan must be a sequence")
    if not plan or len(plan) > MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("pathfinder JSON tool plan exceeds bounded step count")
    seen_step_ids: set[str] = set()
    for raw_step in plan:
        if not isinstance(raw_step, Mapping):
            raise ValueError("pathfinder JSON tool plan steps must be objects")
        step_id = str(raw_step.get("step_id") or "").strip()
        capability_id = str(raw_step.get("capability_id") or "").strip()
        if not step_id or step_id in seen_step_ids:
            raise ValueError("pathfinder JSON tool plan step_id must be unique and non-empty")
        seen_step_ids.add(step_id)
        if capability_id not in PATHFINDER_JSON_TOOL_CAPABILITIES:
            raise ValueError(f"unknown pathfinder JSON tool capability: {capability_id}")
        if not isinstance(raw_step.get("input"), Mapping):
            raise ValueError(f"{step_id}.input must be an object")
    if str(plan[-1].get("step_id") or "") != "bundle":
        raise ValueError("pathfinder JSON tool plan must finish at bundle")


def _normalized_json_tool_plan(plan: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validate_pathfinder_json_tool_plan(plan)
    return [
        {
            "step_id": str(step["step_id"]),
            "capability_id": str(step["capability_id"]),
            "input": dict(step["input"]),
        }
        for step in plan
    ]


def _extract_lease_ptc_tool_plan(lease_consumer_result: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    if not lease_consumer_result:
        return None
    if lease_consumer_result.get("consumer_status") != "completed":
        return None
    job_results = lease_consumer_result.get("job_results")
    if not isinstance(job_results, Sequence) or isinstance(job_results, (str, bytes)) or not job_results:
        return None
    first_job = job_results[0]
    if not isinstance(first_job, Mapping) or first_job.get("job_status") != "completed":
        return None
    lease_result = first_job.get("lease_result")
    if not isinstance(lease_result, Mapping) or lease_result.get("lease_status") != "completed":
        return None
    output = lease_result.get("output")
    if not isinstance(output, Mapping):
        return None
    trace = output.get("bubblewrap_trace")
    if not isinstance(trace, Mapping):
        return None
    if "ptc_plan_generation_recorded" not in trace.get("reason_codes", []):
        return None
    return _normalized_json_tool_plan(output.get("ptc_tool_plan") or [])


def build_query_adaptive_pathfinder_plan(
    *,
    query_text: str,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
    llm_tool_plan: Sequence[Mapping[str, Any]] | None = None,
    lease_consumer_result: Mapping[str, Any] | None = None,
    fallback_reason_code: str | None = None,
) -> dict[str, Any]:
    """Build a bounded Pathfinder PTC plan from query signals or a lease-backed LLM plan."""

    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")
    if max_step_count < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("max_step_count must allow the bounded Pathfinder plan")

    max_recent = _clamp_int(max_recent_limit, minimum=1, maximum=DEFAULT_MAX_RECENT_LIMIT)
    selected_recent = _clamp_int(recent_limit, minimum=1, maximum=max_recent)
    terms = _query_terms(query)
    reason_codes = [
        "query_adaptive_bounded_plan_built",
        "fixed_default_plan_replaced_by_query_adaptive_hook",
        "dynamic_program_source_disabled",
    ]
    strategy = "default_pathfinder_support_bundle"

    if terms & RECENCY_TERMS:
        selected_recent = max(selected_recent, min(max_recent, selected_recent + 2))
        strategy = "recency_weighted_support_bundle"
        reason_codes.append("query_recency_signal_detected")
    if terms & COMPARISON_TERMS:
        selected_recent = max(selected_recent, min(max_recent, selected_recent + 1))
        strategy = (
            "recency_comparison_support_bundle"
            if strategy == "recency_weighted_support_bundle"
            else "comparison_support_bundle"
        )
        reason_codes.append("query_comparison_signal_detected")
    if terms & ORIGIN_TERMS:
        reason_codes.append("query_origin_signal_detected")
        if strategy == "default_pathfinder_support_bundle":
            strategy = "origin_weighted_support_bundle"
    if len(terms) <= 3 and not (terms & (RECENCY_TERMS | COMPARISON_TERMS)):
        selected_recent = min(selected_recent, 2)
        reason_codes.append("short_query_bounded_recent_limit")

    extracted_llm_tool_plan = (
        _normalized_json_tool_plan(llm_tool_plan)
        if llm_tool_plan is not None
        else _extract_lease_ptc_tool_plan(lease_consumer_result)
    )
    json_tool_plan = extracted_llm_tool_plan or render_default_pathfinder_json_plan(
        recent_limit=selected_recent
    )
    if extracted_llm_tool_plan is not None and lease_consumer_result is not None:
        planner_mode = LEASE_BACKED_LLM_PLANNER_MODE
    elif extracted_llm_tool_plan is not None:
        planner_mode = EXTERNAL_LLM_PLANNER_MODE
    elif fallback_reason_code:
        planner_mode = FALLBACK_PLANNER_MODE
    else:
        planner_mode = DETERMINISTIC_PLANNER_MODE
    program_source = render_default_pathfinder_program(recent_limit=selected_recent)
    plan_hash = hashlib.sha256(
        f"{query}\n{selected_recent}\n{max_recent}\n{strategy}\n{planner_mode}\n{json_tool_plan}".encode("utf-8")
    ).hexdigest()[:32]
    plan = {
        "schema_version": QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION,
        "plan_id": f"ptc-query-adaptive-plan-{plan_hash}",
        "query_ref": f"query-ref://openyggdrasil/ptc-query-adaptive/{plan_hash}",
        "plan_status": QUERY_ADAPTIVE_PLAN_STATUS,
        "strategy": strategy,
        "planner_execution_mode": planner_mode,
        "bounded_tool_plan": True,
        "max_step_count": MAX_PATHFINDER_TOOL_STEP_COUNT,
        "max_json_tool_step_count": MAX_PATHFINDER_JSON_TOOL_STEP_COUNT,
        "requested_max_step_count": max_step_count,
        "base_recent_limit": _clamp_int(recent_limit, minimum=1, maximum=max_recent),
        "selected_recent_limit": selected_recent,
        "max_recent_limit": max_recent,
        "dynamic_code_execution_allowed": False,
        "program_source_status": (
            "bounded_json_plan_from_llm_not_dynamic_code"
            if extracted_llm_tool_plan is not None
            else "deterministic_plan_not_executed_as_code"
        ),
        "program_source": program_source,
        "json_tool_plan": json_tool_plan,
        "tool_step_order": [step["capability_id"] for step in json_tool_plan],
        "reason_codes": reason_codes,
    }
    if extracted_llm_tool_plan is not None:
        plan.update(
            {
                "lease_consumer_status": lease_consumer_result.get("consumer_status")
                if lease_consumer_result
                else "external_llm_tool_plan",
                "bubblewrap_trace_ref": (
                    lease_consumer_result.get("job_results", [{}])[0].get("bubblewrap_trace_ref")
                    if lease_consumer_result
                    else None
                ),
            }
        )
        plan["reason_codes"].extend(
            [
                "llm_json_plan_generated_via_phase2_lease_consumer",
                (
                    "ptc_plan_generation_recorded_in_bwrap_trace"
                    if lease_consumer_result is not None
                    else "external_llm_json_plan_validated"
                ),
            ]
        )
    if fallback_reason_code:
        plan["reason_codes"].append(str(fallback_reason_code))
    validate_query_adaptive_pathfinder_plan(plan)
    return plan


def build_lease_backed_query_adaptive_pathfinder_plan(
    *,
    query_text: str,
    sandbox_decision: Mapping[str, Any],
    bwrap_command: Sequence[str],
    provider_descriptor: Mapping[str, Any] | None = None,
    db_path: Path | None = None,
    popen_factory=None,
    scratch_root: Path | None = None,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
) -> dict[str, Any]:
    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")

    from delivery.mailbox_store import append_message
    from reasoning.lease_executor import (
        build_reasoning_lease_mailbox_job,
        consume_reasoning_lease_mailbox_jobs,
    )
    from reasoning.provider_resource_boundary import build_provider_headless_lease_request

    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]
    descriptor = {
        "provider_id": "hermes",
        "provider_profile": "phase3a-ptc",
        "provider_session_id": f"ptc-plan-{query_hash}",
        "session_uid": f"hermes:phase3a-ptc:ptc-plan-{query_hash}",
        **dict(provider_descriptor or {}),
    }
    lease_request = build_provider_headless_lease_request(
        provider_descriptor=descriptor,
        requested_by_role="pathfinder",
        job_type="pathfinding_review",
        objective="Generate a bounded JSON Programmatic Tool Calling plan from safe refs.",
        input_refs={
            "query_ref": f"query-ref://openyggdrasil/ptc-dynamic-plan/{query_hash}",
            "tool_registry_ref": "ptc-tool-registry-ref://openyggdrasil/pathfinder/v1",
        },
        priority="medium",
        time_budget_seconds=120,
        expected_output_schema="pathfinder_json_tool_plan",
    )
    message = build_reasoning_lease_mailbox_job(
        lease_request,
        job_id=f"ptc-dynamic-plan-{query_hash}",
    )
    append_message(message, db_path=db_path)
    lease_consumer_result = consume_reasoning_lease_mailbox_jobs(
        lease_request_resolver=lambda _message: lease_request,
        sandbox_decision=sandbox_decision,
        bwrap_command=bwrap_command,
        db_path=db_path,
        max_jobs=1,
        popen_factory=popen_factory,
        scratch_root=scratch_root,
        evidence_ref_prefix=(
            "private-evidence://Dev_history/runs/phase3a-ptc-dynamic-plan"
        ),
    )
    extracted_plan = _extract_lease_ptc_tool_plan(lease_consumer_result)
    if extracted_plan is None:
        return build_query_adaptive_pathfinder_plan(
            query_text=query,
            recent_limit=recent_limit,
            max_recent_limit=max_recent_limit,
            max_step_count=max_step_count,
            fallback_reason_code="llm_plan_generation_failed_default_pathfinder_program_used",
        )
    return build_query_adaptive_pathfinder_plan(
        query_text=query,
        recent_limit=recent_limit,
        max_recent_limit=max_recent_limit,
        max_step_count=max_step_count,
        lease_consumer_result=lease_consumer_result,
    )


def validate_query_adaptive_pathfinder_plan(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION:
        raise ValueError("invalid query-adaptive Pathfinder plan schema_version")
    if payload.get("plan_status") != QUERY_ADAPTIVE_PLAN_STATUS:
        raise ValueError("query-adaptive Pathfinder plan must be bounded")
    if payload.get("bounded_tool_plan") is not True:
        raise ValueError("query-adaptive Pathfinder plan must be bounded")
    if payload.get("dynamic_code_execution_allowed") is not False:
        raise ValueError("query-adaptive Pathfinder plan must not allow dynamic code")
    max_recent = int(payload.get("max_recent_limit") or 0)
    selected_recent = int(payload.get("selected_recent_limit") or 0)
    if max_recent < 1 or max_recent > DEFAULT_MAX_RECENT_LIMIT:
        raise ValueError("max_recent_limit is out of bounds")
    if selected_recent < 1 or selected_recent > max_recent:
        raise ValueError("selected_recent_limit is out of bounds")
    if int(payload.get("max_step_count") or 0) != MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("max_step_count must match bounded Pathfinder tool plan")
    if int(payload.get("max_json_tool_step_count") or 0) != MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("max_json_tool_step_count must match bounded JSON tool plan")
    if int(payload.get("requested_max_step_count") or 0) < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("requested_max_step_count is below the required bounded plan")
    tool_steps = payload.get("tool_step_order")
    if not isinstance(tool_steps, list) or len(tool_steps) > MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("tool_step_order must be a bounded list")
    validate_pathfinder_json_tool_plan(payload.get("json_tool_plan") or [])
    program_source = str(payload.get("program_source") or "")
    if f"limit={selected_recent}" not in program_source:
        raise ValueError("program_source must use selected_recent_limit")
    if "query_text" in payload:
        raise ValueError("query_text must not be copied into portable plan metadata")
    planner_mode = str(payload.get("planner_execution_mode") or "")
    if planner_mode == LEASE_BACKED_LLM_PLANNER_MODE:
        if payload.get("lease_consumer_status") != "completed":
            raise ValueError("lease-backed LLM plan requires completed lease consumer status")
        if not str(payload.get("bubblewrap_trace_ref") or "").startswith("ptc-trace-ref://"):
            raise ValueError("lease-backed LLM plan requires a safe bubblewrap_trace_ref")


def render_query_adaptive_pathfinder_program(
    *,
    query_text: str,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
) -> str:
    plan = build_query_adaptive_pathfinder_plan(
        query_text=query_text,
        recent_limit=recent_limit,
        max_recent_limit=max_recent_limit,
        max_step_count=max_step_count,
    )
    return str(plan["program_source"])


def structural_anchor_fallback_evaluator(
    *,
    query_text: str,
    existing_topics: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    _ = query_text
    _ = existing_topics
    return {
        "topic_key": None,
        "reason_labels": [STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE],
        "summary": "PTC structural path did not use Hermes; returning an unanchored fallback.",
    }


__all__ = [
    "DEFAULT_MAX_RECENT_LIMIT",
    "MAX_PATHFINDER_TOOL_STEP_COUNT",
    "MAX_PATHFINDER_JSON_TOOL_STEP_COUNT",
    "EXTERNAL_LLM_PLANNER_MODE",
    "FALLBACK_PLANNER_MODE",
    "LEASE_BACKED_LLM_PLANNER_MODE",
    "QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION",
    "QUERY_ADAPTIVE_PLAN_STATUS",
    "REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES",
    "ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION",
    "ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS",
    "STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE",
    "build_lease_backed_query_adaptive_pathfinder_plan",
    "build_pathfinder_ptc_routing_trace",
    "build_query_adaptive_pathfinder_plan",
    "build_role_polymorphic_ptc_telemetry_trace",
    "render_default_pathfinder_program",
    "render_default_pathfinder_json_plan",
    "render_query_adaptive_pathfinder_program",
    "structural_anchor_fallback_evaluator",
    "validate_pathfinder_json_tool_plan",
    "validate_query_adaptive_pathfinder_plan",
    "validate_role_polymorphic_ptc_telemetry_trace",
]
