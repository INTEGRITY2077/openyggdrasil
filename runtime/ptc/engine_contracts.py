"""PTC engine constants and imported contract constants."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.hard_nonclaims import (
    assert_additive_only_hard_nonclaims as _assert_additive_only_hard_nonclaims,
)
from runtime.ptc.provider_session_boundary import (
    PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
    PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
    PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAG_SUFFIXES,
    PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAG_SUFFIXES,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SOURCE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_UNAVAILABLE_REASON,
)
from runtime.ptc.runner_source_contracts import (
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_STATUS,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_EVIDENCE_STATUS,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_KIND,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_STATUS,
    PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_STATUS,
    RUNNER_RESPONSE_NO_OVERCLAIM_FLAG_SUFFIXES,
    RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
    RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAG_SUFFIXES,
    SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAG_SUFFIXES,
)
from runtime.ptc.typed_refs import safe_portable_ref as _safe_portable_ref
from runtime.common.role_aliases import (
    ROW_8_EXECUTOR_PENDING_STATUS,
    ROW_8_LIVE_VERIFICATION_LABEL,
)


STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE = "structural_anchor_fallback_without_hermes"
QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION = "ptc_query_adaptive_pathfinder_plan.v1"
QUERY_ADAPTIVE_PLAN_STATUS = "bounded_query_adaptive"
MAX_PATHFINDER_TOOL_STEP_COUNT = 6
MAX_PATHFINDER_JSON_TOOL_STEP_COUNT = 7
DEFAULT_MAX_RECENT_LIMIT = 8
LEASE_BACKED_LLM_PLANNER_MODE = "lease_backed_llm_dynamic_assembly"
EXTERNAL_LLM_PLANNER_MODE = "external_llm_dynamic_assembly"
DETERMINISTIC_PLANNER_MODE = "deterministic_query_signals"
FALLBACK_PLANNER_MODE = "typed_unavailable_after_llm_failure"
PATHFINDER_RUNTIME_APPROVED_EFFORT = "high"
PATHFINDER_RUNTIME_LEASE_GROUP = "semantic_routing"
ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION = "ptc_role_polymorphic_telemetry.v1"
ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS = "same_run_role_prompt_context_ready"
ROLE_POLYMORPHIC_PTC_CLAIM_SCOPE = (
    "minimal_ptc_telemetry_candidate_not_production_ptc_implemented"
)
ROLE_POLYMORPHIC_SAME_RUN_SOURCE_KIND = "physical_live_same_run"
ROLE_POLYMORPHIC_EVIDENCE_CHAIN_STATUS = "upstream_verified"
PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_SCHEMA_VERSION = (
    "provider_subagent_ptc_execution_trace_packet.v1"
)
PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_STATUS = "packet_surface_ready"
PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_CLAIM_SCOPE = (
    "provider_subagent_execution_trace_packet_surface_not_live_invocation_proof"
)
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
PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS = (
    "This packet surface does not prove a real Hermes live invocation.",
    "This packet surface is not proof of production PTC implementation.",
    "This packet surface is not proof that Reasoning Lease is solved or R10 is complete.",
    "This packet surface is not proof of live readiness or production readiness.",
)
PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_NO_OVERCLAIM_FLAGS = (
    "real_hermes_live_invocation_claimed",
    "provider_answer_quality_claimed",
    "reasoning_lease_solved_claimed",
    "r10_complete_claimed",
    "live_readiness_claimed",
    "production_readiness_claimed",
    "production_ptc_implemented_claimed",
    "public_runtime_integration_complete_claimed",
    "background_live_integration_claimed",
    "consumer_ux_complete_claimed",
    "wiki_production_safety_complete_claimed",
    "full_product_readiness_claimed",
    "thin_worker_chain_relabelled_as_execution",
    "static_bridge_relabelled_as_execution",
    "mcp_generic_gateway_or_agent_adapter_used",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
)
PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION = (
    "provider_subagent_ptc_invocation_command.v1"
)
PROVIDER_SUBAGENT_PTC_INVOCATION_UNAVAILABLE_RESULT_SCHEMA_VERSION = (
    "provider_subagent_ptc_invocation_unavailable_result.v1"
)
PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME = (
    "openyggdrasil.provider_subagent_ptc.invoke.v1"
)
PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS = "ready_for_r7_same_run_attempt"
PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_CLAIM_SCOPE = (
    "provider_subagent_invocation_command_enablement_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS = (
    "provider_or_subagent_invocation_ref",
    "role_execution_refs",
    "typed_result_ref_or_typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
)
PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS = (
    "Use this when",
    "Do not use this when",
    "If ambiguous",
    "Typed unavailable when",
    "Required evidence refs",
    "Hard nonclaims",
)
PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS = (
    "This command surface does not prove a real Hermes live invocation.",
    "This command surface does not prove a provider or subagent completed execution.",
    "This command surface is not proof of production PTC implementation.",
    "This command surface is not proof that Reasoning Lease is solved or R10 is complete.",
    "This command surface is not proof of live readiness or production readiness.",
)
PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_NO_OVERCLAIM_FLAGS,
    "provider_subagent_invocation_completed_claimed",
    "provider_gateway_called",
    "provider_state_read",
    "command_surface_relabelled_as_invocation",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS,
    *PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS,
    *PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS,
    *PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS,
    *PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS,
    *RUNNER_RESPONSE_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS,
    *SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS,
    *RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAG_SUFFIXES,
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS,
    *RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES,
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

__all__ = sorted(
    name
    for name in globals()
    if (
        name.isupper()
        or name in {
            "_assert_additive_only_hard_nonclaims",
            "_safe_portable_ref",
        }
    )
)
