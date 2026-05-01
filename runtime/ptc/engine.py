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
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION = (
    "provider_subagent_ptc_provider_session_ref.v1"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS = "provider_session_ref_surface_ready"
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE = (
    "provider_session_ref_surface_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_KIND = "bounded_provider_session_reference"
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SOURCE = "openyggdrasil_owned_runtime_packet"
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS = (
    "This provider_session_ref surface does not execute a provider or subagent.",
    "This provider_session_ref surface does not prove real provider/subagent invocation.",
    "This provider_session_ref surface is not proof of production PTC implementation.",
    "This provider_session_ref surface is not proof of live readiness or production readiness.",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS,
    "provider_session_ref_relabelled_as_invocation",
    "provider_session_ref_claimed_live_proof",
    "provider_cli_executed",
    "provider_profile_or_state_accessed",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION = (
    "provider_subagent_ptc_provider_session_invocation_boundary.v1"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS = (
    "provider_session_invocation_boundary_ready"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE = (
    "provider_session_invocation_boundary_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME = (
    "openyggdrasil.provider_session.invoke.v1"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND = (
    "safe_provider_session_invocation_boundary"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS = (
    "provider_or_subagent_invocation_ref",
    "typed_result_ref_or_typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
    "role_execution_refs",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS = (
    "This provider/session invocation boundary validates safe refs only.",
    "This provider/session invocation boundary does not execute provider or subagent work.",
    "This provider/session invocation boundary is not proof of real provider/subagent invocation.",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS,
    "provider_session_invocation_boundary_relabelled_as_live",
    "provider_session_invocation_completed_claimed",
    "provider_run_refs_fabricated",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION = (
    "provider_subagent_ptc_provider_session_runner_result.v1"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS = (
    "provider_session_runner_typed_unavailable"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE = (
    "provider_session_runner_enablement_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND = (
    "safe_provider_session_runner_typed_unavailable_result"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_UNAVAILABLE_REASON = (
    "provider_session_runner_executor_unavailable"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS = (
    "This provider/session runner surface returns typed unavailable without executing provider work.",
    "This provider/session runner surface does not prove real provider/subagent invocation.",
    "This provider/session runner surface is not proof of live readiness or production readiness.",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS,
    "provider_session_runner_relabelled_as_live",
    "provider_session_runner_completed_invocation_claimed",
    "provider_run_refs_fabricated_by_runner",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION = (
    "provider_subagent_ptc_provider_session_executor_boundary.v1"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS = (
    "provider_session_executor_boundary_validated"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE = (
    "provider_session_executor_boundary_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND = (
    "safe_provider_session_executor_refs_boundary"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS = (
    "provider_session_executor_refs_verified_by_caller"
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_HARD_NONCLAIMS = (
    "This provider/session executor boundary validates caller-supplied safe refs only.",
    "This provider/session executor boundary does not execute provider or subagent work.",
    "This provider/session executor boundary is not proof of real provider/subagent invocation or row 8 LIVE.",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS,
    "provider_session_executor_boundary_relabelled_as_live",
    "provider_session_executor_completed_invocation_claimed",
    "provider_session_executor_refs_claimed_without_live_verification",
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_SCHEMA_VERSION = (
    "provider_subagent_ptc_runner_response_ingress.v1"
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_STATUS = "runner_response_ingress_validated"
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_CLAIM_SCOPE = (
    "safe_runner_response_ingress_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS = (
    "This runner response ingress validates safe refs only.",
    "This runner response ingress is not a provider or subagent runner.",
    "This runner response ingress does not prove a real Hermes live invocation.",
    "This runner response ingress is not proof of production PTC implementation.",
    "This runner response ingress is not proof of live readiness or production readiness.",
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS = (
    "This runner response producer only assembles already-typed safe refs.",
    "This runner response producer does not execute provider or subagent work.",
    "This runner response producer is not proof of real provider/subagent invocation.",
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_SCHEMA_VERSION = (
    "provider_subagent_ptc_same_run_typed_ref_source.v1"
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_STATUS = (
    "same_run_typed_ref_source_validated"
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_CLAIM_SCOPE = (
    "safe_same_run_typed_ref_source_boundary_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND = (
    "same_run_non_fixture_typed_ref_source"
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS = (
    "same_run_source_verified_by_caller"
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS = (
    "This same-run typed ref source only validates already-safe source packet refs.",
    "This same-run typed ref source does not execute provider or subagent work.",
    "This same-run typed ref source is not proof of real provider/subagent invocation.",
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS = (
    "This runner source packet producer only assembles typed non-fixture refs.",
    "This runner source packet producer does not execute provider or subagent work.",
    "This runner source packet producer is not proof of real provider/subagent invocation.",
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_SCHEMA_VERSION = (
    "provider_subagent_ptc_runner_source_boundary.v1"
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_STATUS = "runner_source_boundary_validated"
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_CLAIM_SCOPE = (
    "safe_runner_provider_source_boundary_not_live_invocation_proof"
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_KIND = (
    "same_run_runner_provider_typed_ref_boundary"
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_EVIDENCE_STATUS = (
    "same_run_runner_provider_refs_verified_by_caller"
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_HARD_NONCLAIMS = (
    "This runner/provider source boundary validates typed non-fixture refs only.",
    "This runner/provider source boundary does not execute provider or subagent work.",
    "This runner/provider source boundary is not proof of real provider/subagent invocation.",
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS,
    "runner_response_ingress_relabelled_as_invocation",
    "runner_response_ingress_claimed_live_proof",
    "raw_runner_payload_material_included",
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS,
    "same_run_typed_ref_source_relabelled_as_invocation",
    "same_run_typed_ref_source_claimed_live_proof",
    "fixture_refs_used",
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS,
    "runner_source_packet_producer_relabelled_as_invocation",
    "runner_source_packet_producer_claimed_live_proof",
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAGS = (
    *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS,
    "runner_source_boundary_relabelled_as_invocation",
    "runner_source_boundary_claimed_live_proof",
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_ALLOWED_FIELDS = (
    "same_run_invocation_command",
    "typed_task_id",
    "provider_or_subagent_invocation_ref",
    "role_execution_refs",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
    "hard_nonclaims",
    "no_overclaim_flags",
    "runner_response_ref",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS = (
    "raw_provider_material",
    "raw_runner_payload",
    "raw_transcript",
    "transcript",
    "raw_prompt",
    "prompt",
    "credentials",
    "credential_material",
    "provider_profile",
    "provider_state",
    "provider_state_db",
    "state_db",
    "mcp_result",
    "generic_gateway_result",
    "agent_adapter_result",
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_ALLOWED_FIELDS = (
    "source_packet_ref",
    "source_kind",
    "source_evidence_status",
    "same_run_witness_ref",
    "same_run_invocation_command",
    "typed_task_id",
    "provider_or_subagent_invocation_ref",
    "role_execution_refs",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
    "fixture_refs_used",
    "non_fixture_refs_only",
    "provider_gateway_called",
    "provider_state_read",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "hard_nonclaims",
    "no_overclaim_flags",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_ALLOWED_FIELDS = (
    "source_boundary_ref",
    "source_boundary_kind",
    "source_boundary_evidence_status",
    "source_packet_ref",
    "same_run_witness_ref",
    "same_run_invocation_command",
    "typed_task_id",
    "provider_or_subagent_invocation_ref",
    "role_execution_refs",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
    "fixture_refs_used",
    "non_fixture_refs_only",
    "provider_gateway_called",
    "provider_state_read",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "hard_nonclaims",
    "no_overclaim_flags",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_ALLOWED_FIELDS = (
    "provider_session_ref_schema_version",
    "provider_session_ref_id",
    "provider_session_ref",
    "provider_session_ref_status",
    "provider_session_ref_claim_scope",
    "provider_session_ref_kind",
    "provider_session_ref_source",
    "provider_session_id",
    "typed_task_id",
    "session_binding_ref",
    "typed_unavailable_ref",
    "required_future_invocation_refs",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "provider_profile_or_state_accessed",
    "provider_gateway_called",
    "provider_state_read",
    "provider_cli_executed",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "safe_for_future_invocation_binding",
    "hard_nonclaims_preserved",
    "additive_only_hard_nonclaims",
    "hard_nonclaims",
    "no_overclaim_flags",
    "runtime_owner",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_ALLOWED_FIELDS = (
    "schema_version",
    "boundary_id",
    "boundary_status",
    "claim_scope",
    "boundary_kind",
    "same_run_invocation_command",
    "provider_session_ref",
    "provider_session_ref_schema_version",
    "provider_session_ref_status",
    "provider_session_ref_claim_scope",
    "provider_session_ref_validated",
    "provider_session_ref_id",
    "provider_session_id",
    "typed_task_id",
    "typed_task_ref",
    "typed_task_ref_status",
    "invocation_request_ref",
    "required_provider_run_refs",
    "provider_or_subagent_invocation_ref_status",
    "typed_result_ref_status",
    "typed_unavailable_ref_status",
    "typed_result_or_unavailable_ref_status",
    "before_context_ref_status",
    "after_context_ref_status",
    "role_execution_refs_status",
    "row_8_live_status",
    "boundary_surface_only",
    "safe_provider_session_invocation_boundary",
    "provider_runner_required",
    "provider_gateway_called",
    "provider_state_read",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "provider_profile_or_state_accessed",
    "provider_cli_executed",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "hard_nonclaims_preserved",
    "additive_only_hard_nonclaims",
    "hard_nonclaims",
    "no_overclaim_flags",
    "llm_facing_contract",
    "runtime_owner",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_ALLOWED_FIELDS = (
    "schema_version",
    "runner_result_id",
    "runner_result_status",
    "runner_result_kind",
    "claim_scope",
    "same_run_invocation_command",
    "boundary_id",
    "boundary_status",
    "boundary_schema_version",
    "boundary_claim_scope",
    "provider_session_ref",
    "provider_session_ref_validated",
    "typed_task_id",
    "typed_task_ref",
    "invocation_request_ref",
    "provider_or_subagent_invocation_ref",
    "provider_or_subagent_invocation_typed_unavailable_ref",
    "provider_or_subagent_invocation_unavailable",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_context_ref",
    "before_context_typed_unavailable_ref",
    "before_context_unavailable",
    "after_context_ref",
    "after_context_typed_unavailable_ref",
    "after_context_unavailable",
    "role_execution_refs",
    "role_execution_typed_unavailable_refs",
    "role_execution_refs_unavailable",
    "required_provider_run_refs",
    "runner_surface_only",
    "provider_runner_executor_available",
    "safe_typed_unavailable_refs_emitted",
    "row_8_live_status",
    "provider_gateway_called",
    "provider_state_read",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "provider_profile_or_state_accessed",
    "provider_cli_executed",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "hard_nonclaims_preserved",
    "additive_only_hard_nonclaims",
    "hard_nonclaims",
    "no_overclaim_flags",
    "llm_facing_contract",
    "runtime_owner",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_ALLOWED_FIELDS = (
    "schema_version",
    "boundary_id",
    "boundary_ref",
    "executor_boundary_ref",
    "executor_boundary_status",
    "claim_scope",
    "executor_boundary_kind",
    "executor_evidence_status",
    "same_run_invocation_command",
    "provider_session_invocation_boundary_id",
    "provider_session_invocation_boundary_status",
    "provider_session_invocation_boundary_claim_scope",
    "provider_session_ref",
    "provider_session_ref_validated",
    "typed_task_id",
    "typed_task_ref",
    "invocation_request_ref",
    "required_provider_run_refs",
    "provider_or_subagent_invocation_ref",
    "role_execution_refs",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_context_ref",
    "after_context_ref",
    "executor_result_packet_validated",
    "executor_refs_validated",
    "typed_result_ref_validated",
    "context_refs_validated",
    "role_execution_refs_validated",
    "safe_refs_only",
    "non_fixture_refs_only",
    "fixture_refs_used",
    "executor_boundary_only",
    "executor_executed_by_runtime",
    "row_8_live_status",
    "provider_gateway_called",
    "provider_state_read",
    "raw_provider_material_included",
    "raw_transcript_included",
    "raw_prompt_included",
    "credential_material_included",
    "provider_profile_material_included",
    "provider_state_db_material_included",
    "provider_profile_or_state_accessed",
    "provider_cli_executed",
    "mcp_generic_gateway_or_agent_adapter_used",
    "real_provider_subagent_invocation_claimed",
    "hard_nonclaims_preserved",
    "additive_only_hard_nonclaims",
    "hard_nonclaims",
    "no_overclaim_flags",
    "llm_facing_contract",
    "runtime_owner",
    "reason_codes",
    "generated_at",
)
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS = (
    "fixture",
    "mock://",
    "runner-response-producer",
)
HARD_NONCLAIM_WEAKENING_TOKENS = (
    "override global",
    "weaken global",
    "remove global",
    "ignore global",
    "relax global",
    "waive global",
    "claim reasoning lease solved",
    "claim live readiness",
    "claim production readiness",
    "claim production ptc implemented",
    "claim full product readiness",
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


def _string_list(values: Sequence[str] | None, *, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a string list")
    return [str(value).strip() for value in values if str(value).strip()]


def _assert_additive_only_hard_nonclaims(hard_nonclaims: Sequence[str]) -> None:
    normalized = "\n".join(str(value) for value in hard_nonclaims).lower()
    for token in HARD_NONCLAIM_WEAKENING_TOKENS:
        if token in normalized:
            raise ValueError("hard_nonclaims must not weaken global hard nonclaims")


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


def _normalize_strict_role_map(
    values: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a role ref map")
    normalized_keys = {str(key).strip().lower().replace("-", "_") for key in values}
    unknown = sorted(normalized_keys - set(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES))
    if unknown:
        raise ValueError(f"{field_name} has unsupported roles: {', '.join(unknown)}")
    return _normalize_role_map(values, field_name=field_name)


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


def _normalize_execution_trace_hard_nonclaims(
    packet_hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    hard_nonclaims = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *_string_list(packet_hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(hard_nonclaims)
    return hard_nonclaims


def _validate_execution_trace_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider/subagent execution trace packet requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider/subagent execution trace packet missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(f"no_overclaim_flags missing required flags: {', '.join(missing)}")
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe provider/subagent execution trace flag: {flag_name}")


def build_provider_subagent_ptc_execution_trace_packet(
    *,
    provider_or_subagent_invocation_ref: str,
    ptc_telemetry_trace: Mapping[str, Any],
    role_execution_refs: Mapping[str, Any] | None = None,
    execution_trace_ref: str | None = None,
    typed_result_ref: str | None = None,
    typed_unavailable_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed packet surface for provider/subagent PTC execution refs.

    The packet validates the shape needed by a later provider/subagent run. It
    does not call Hermes, inspect provider state, copy raw transcripts, or prove
    that a real live invocation happened.
    """

    active_invocation_ref = _safe_portable_ref(
        provider_or_subagent_invocation_ref,
        field_name="provider_or_subagent_invocation_ref",
    )
    telemetry_role_refs = _role_execution_refs_from_ptc_telemetry(ptc_telemetry_trace)
    active_role_refs = _normalize_strict_role_map(
        role_execution_refs or telemetry_role_refs,
        field_name="role_execution_refs",
    )
    if active_role_refs != telemetry_role_refs:
        raise ValueError("role_execution_refs must match the validated PTC telemetry trace")

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

    telemetry_ref = _safe_portable_ref(
        ptc_telemetry_trace.get("telemetry_ref"),
        field_name="ptc_telemetry_ref",
    )
    token = _route_token(
        active_invocation_ref,
        telemetry_ref,
        tuple(active_role_refs.items()),
        active_typed_result_ref,
        active_typed_unavailable_ref,
    )
    active_execution_trace_ref = _safe_portable_ref(
        execution_trace_ref
        or f"execution-trace-ref://openyggdrasil/provider-subagent-ptc/{token}",
        field_name="execution_trace_ref",
    )
    packet = {
        "schema_version": PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_SCHEMA_VERSION,
        "execution_trace_id": f"provider-subagent-ptc-execution-trace-{token}",
        "execution_trace_ref": active_execution_trace_ref,
        "execution_trace_status": PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_CLAIM_SCOPE,
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_refs,
        "ptc_telemetry_ref": telemetry_ref,
        "ptc_telemetry_schema_version": ptc_telemetry_trace.get("schema_version"),
        "ptc_telemetry_claim_scope": ptc_telemetry_trace.get("claim_scope"),
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "required_roles": list(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES),
        "role_count": len(active_role_refs),
        "same_run_context": dict(ptc_telemetry_trace.get("same_run_context") or {}),
        "ptc_telemetry_trace_validated": True,
        "role_execution_refs_match_ptc_telemetry": True,
        "packet_surface_only": True,
        "safe_refs_only": True,
        "provider_subagent_invocation_material_included": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": _normalize_execution_trace_hard_nonclaims(hard_nonclaims),
        "no_overclaim_flags": {
            flag: False for flag in PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_NO_OVERCLAIM_FLAGS
        },
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_subagent_ptc_execution_trace_packet_surface_built",
            "ptc_telemetry_trace_validated",
            "role_execution_refs_match_ptc_telemetry",
            "hard_nonclaims_preserved",
            "live_invocation_not_claimed",
            "production_ptc_not_claimed",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_execution_trace_packet(packet)
    return packet


def validate_provider_subagent_ptc_execution_trace_packet(payload: Mapping[str, Any]) -> None:
    packet = dict(payload)
    if packet.get("schema_version") != PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent PTC execution trace packet schema_version")
    if packet.get("execution_trace_status") != PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_STATUS:
        raise ValueError("invalid provider/subagent PTC execution trace packet status")
    if packet.get("claim_scope") != PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_CLAIM_SCOPE:
        raise ValueError("invalid provider/subagent PTC execution trace claim_scope")
    for field in (
        "execution_trace_ref",
        "provider_or_subagent_invocation_ref",
        "ptc_telemetry_ref",
    ):
        _safe_portable_ref(packet.get(field), field_name=field)
    if packet.get("typed_result_ref") is None and packet.get("typed_unavailable_ref") is None:
        raise ValueError("typed result or typed unavailable ref is required")
    if packet.get("typed_result_ref") is not None:
        _safe_portable_ref(packet.get("typed_result_ref"), field_name="typed_result_ref")
    if packet.get("typed_unavailable_ref") is not None:
        _safe_portable_ref(packet.get("typed_unavailable_ref"), field_name="typed_unavailable_ref")
    if packet.get("required_roles") != list(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES):
        raise ValueError("required_roles must match role-polymorphic PTC roles")
    role_refs = _normalize_strict_role_map(
        packet.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    if packet.get("role_count") != len(role_refs):
        raise ValueError("role_count must match role_execution_refs count")
    _normalize_same_run_ptc_context(packet.get("same_run_context") or {})
    for field in (
        "ptc_telemetry_trace_validated",
        "role_execution_refs_match_ptc_telemetry",
        "packet_surface_only",
        "safe_refs_only",
        "additive_only_hard_nonclaims",
    ):
        if packet.get(field) is not True:
            raise ValueError(f"provider/subagent execution trace packet requires {field}=True")
    if packet.get("provider_subagent_invocation_material_included") is not False:
        raise ValueError("provider/subagent execution trace packet must not include provider material")
    _validate_execution_trace_hard_nonclaims(packet.get("hard_nonclaims"))
    _validate_no_overclaim_flags(packet.get("no_overclaim_flags"))
    reason_codes = packet.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("reason_codes are required")


def _normalize_invocation_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_invocation_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider/subagent invocation command requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider/subagent invocation command missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_invocation_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("no_overclaim_flags must be an object")
    missing = [
        flag for flag in PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS if flag not in flags
    ]
    if missing:
        raise ValueError(f"no_overclaim_flags missing required flags: {', '.join(missing)}")
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe provider/subagent invocation command flag: {flag_name}")


def _default_provider_subagent_invocation_llm_contract(
    hard_nonclaims: Sequence[str],
) -> dict[str, Any]:
    return {
        "Use this when": (
            "R5 verified that no safe same-run provider/subagent invocation command exists "
            "and R7 needs the bounded local command contract to attempt one."
        ),
        "Do not use this when": (
            "Calling MCP, a generic gateway, an agent adapter, raw provider state, transcripts, "
            "prompts, credentials, provider profiles, or claiming readiness/product completion."
        ),
        "If ambiguous": (
            "Return a typed-unavailable result with exact missing refs rather than unsafe "
            "provider material."
        ),
        "Typed unavailable when": (
            "A provider/subagent runner does not return provider_or_subagent_invocation_ref, "
            "typed_result_ref or typed_unavailable_ref, before_context_ref, and after_context_ref."
        ),
        "Required evidence refs": [
            "same_run_invocation_command",
            "typed_task_id",
            "provider_or_subagent_invocation_ref",
            "execution_trace_ref",
            "ptc_telemetry_ref",
            "typed_result_ref_or_typed_unavailable_ref",
            "before_context_ref",
            "after_context_ref",
        ],
        "Hard nonclaims": list(hard_nonclaims),
    }


def _validate_invocation_llm_contract(contract: Any) -> None:
    if not isinstance(contract, Mapping):
        raise ValueError("llm_facing_contract must be an object")
    missing = [
        section
        for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS
        if section not in contract
    ]
    if missing:
        raise ValueError(f"llm_facing_contract missing sections: {', '.join(missing)}")
    for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS:
        value = contract.get(section)
        if value is None or value == "" or value == []:
            raise ValueError(f"llm_facing_contract section is empty: {section}")
    _validate_invocation_hard_nonclaims(contract.get("Hard nonclaims"))


def _validate_provider_material_absence(payload: Mapping[str, Any]) -> None:
    for field in (
        "provider_gateway_called",
        "provider_state_read",
        "raw_provider_material_included",
        "raw_transcript_included",
        "raw_prompt_included",
        "credential_material_included",
        "provider_profile_material_included",
        "provider_state_db_material_included",
        "mcp_generic_gateway_or_agent_adapter_used",
        "real_provider_subagent_invocation_claimed",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"provider/subagent invocation surface requires {field}=False")


def _validate_provider_session_ref_payload_fields(payload: Mapping[str, Any]) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in payload
    ]
    if forbidden:
        raise ValueError(
            "provider_session_ref contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in payload
        if field not in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "provider_session_ref contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _normalize_provider_session_ref_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_provider_session_ref_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider_session_ref requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider_session_ref missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_provider_session_ref_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("provider_session_ref no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "provider_session_ref no_overclaim_flags missing: " + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe provider_session_ref flag: {flag_name}")


def build_provider_subagent_ptc_provider_session_ref(
    *,
    provider_session_id: str,
    typed_task_id: str,
    session_binding_ref: str,
    provider_session_ref: str | None = None,
    typed_unavailable_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a bounded provider_session_ref packet for future invocation binding.

    The surface is owned by OpenYggdrasil runtime code and carries safe refs
    only. It does not execute a provider/subagent and is not live invocation
    proof.
    """

    active_provider_session_id = _safe_identifier(
        provider_session_id,
        field_name="provider_session_id",
    )
    active_typed_task_id = _safe_identifier(typed_task_id, field_name="typed_task_id")
    active_session_binding_ref = _safe_portable_ref(
        session_binding_ref,
        field_name="session_binding_ref",
    )
    token = _route_token(
        active_provider_session_id,
        active_typed_task_id,
        active_session_binding_ref,
    )
    active_provider_session_ref = _safe_portable_ref(
        provider_session_ref or f"provider-session-ref://openyggdrasil/ptc/{token}",
        field_name="provider_session_ref",
    )
    active_typed_unavailable_ref = _safe_portable_ref(
        typed_unavailable_ref
        or f"typed-unavailable-ref://openyggdrasil/provider-session-ref/{token}",
        field_name="typed_unavailable_ref",
    )
    active_hard_nonclaims = _normalize_provider_session_ref_hard_nonclaims(
        hard_nonclaims
    )
    provider_session_packet = {
        "provider_session_ref_schema_version": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION
        ),
        "provider_session_ref_id": f"provider-session-ref-surface-{token}",
        "provider_session_ref": active_provider_session_ref,
        "provider_session_ref_status": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS,
        "provider_session_ref_claim_scope": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE
        ),
        "provider_session_ref_kind": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_KIND,
        "provider_session_ref_source": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SOURCE,
        "provider_session_id": active_provider_session_id,
        "typed_task_id": active_typed_task_id,
        "session_binding_ref": active_session_binding_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "required_future_invocation_refs": list(
            PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
        ),
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "provider_profile_or_state_accessed": False,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "provider_cli_executed": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "safe_for_future_invocation_binding": True,
        "hard_nonclaims_preserved": True,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False
            for flag in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS
        },
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_session_ref_surface_built",
            "openyggdrasil_owned_runtime_packet",
            "safe_refs_only",
            "raw_provider_material_excluded",
            "provider_session_ref_not_live_invocation_proof",
            "hard_nonclaims_preserved",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_provider_session_ref(provider_session_packet)
    return provider_session_packet


def validate_provider_subagent_ptc_provider_session_ref(payload: Mapping[str, Any]) -> None:
    provider_session_packet = dict(payload)
    _validate_provider_session_ref_payload_fields(provider_session_packet)
    if (
        provider_session_packet.get("provider_session_ref_schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION
    ):
        raise ValueError("invalid provider_session_ref schema version")
    if (
        provider_session_packet.get("provider_session_ref_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS
    ):
        raise ValueError("invalid provider_session_ref status")
    if (
        provider_session_packet.get("provider_session_ref_claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE
    ):
        raise ValueError("invalid provider_session_ref claim scope")
    if (
        provider_session_packet.get("provider_session_ref_kind")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_KIND
    ):
        raise ValueError("invalid provider_session_ref kind")
    if (
        provider_session_packet.get("provider_session_ref_source")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SOURCE
    ):
        raise ValueError("invalid provider_session_ref source")
    _safe_identifier(
        provider_session_packet.get("provider_session_ref_id"),
        field_name="provider_session_ref_id",
    )
    _safe_identifier(
        provider_session_packet.get("provider_session_id"),
        field_name="provider_session_id",
    )
    _safe_identifier(provider_session_packet.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "provider_session_ref",
        "session_binding_ref",
        "typed_unavailable_ref",
    ):
        _safe_portable_ref(provider_session_packet.get(field), field_name=field)
    if provider_session_packet.get("required_future_invocation_refs") != list(
        PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
    ):
        raise ValueError(
            "required_future_invocation_refs must match provider/subagent invocation contract"
        )
    for field in (
        "safe_for_future_invocation_binding",
        "hard_nonclaims_preserved",
        "additive_only_hard_nonclaims",
    ):
        if provider_session_packet.get(field) is not True:
            raise ValueError(f"provider_session_ref requires {field}=True")
    _validate_provider_material_absence(provider_session_packet)
    for field in ("provider_profile_or_state_accessed", "provider_cli_executed"):
        if provider_session_packet.get(field) is not False:
            raise ValueError(f"provider_session_ref requires {field}=False")
    _validate_provider_session_ref_hard_nonclaims(
        provider_session_packet.get("hard_nonclaims")
    )
    _validate_provider_session_ref_no_overclaim_flags(
        provider_session_packet.get("no_overclaim_flags")
    )
    if provider_session_packet.get("runtime_owner") != "runtime/ptc/engine.py":
        raise ValueError("provider_session_ref runtime_owner must be runtime/ptc/engine.py")
    reason_codes = provider_session_packet.get("reason_codes")
    if (
        not isinstance(reason_codes, Sequence)
        or isinstance(reason_codes, (str, bytes))
        or not reason_codes
    ):
        raise ValueError("reason_codes are required")


def _validate_provider_session_invocation_boundary_payload_fields(
    payload: Mapping[str, Any],
) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in payload
    ]
    if forbidden:
        raise ValueError(
            "provider/session invocation boundary contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in payload
        if field not in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "provider/session invocation boundary contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _normalize_provider_session_invocation_boundary_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_provider_session_invocation_boundary_hard_nonclaims(
    hard_nonclaims: Any,
) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider/session invocation boundary requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider/session invocation boundary missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_provider_session_invocation_boundary_no_overclaim_flags(
    flags: Any,
) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError(
            "provider/session invocation boundary no_overclaim_flags must be an object"
        )
    missing = [
        flag
        for flag in (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS
        )
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "provider/session invocation boundary no_overclaim_flags missing: "
            + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(
                f"unsafe provider/session invocation boundary flag: {flag_name}"
            )


def _default_provider_session_invocation_boundary_llm_contract(
    hard_nonclaims: Sequence[str],
) -> dict[str, Any]:
    return {
        "Use this when": (
            "R23 verified that the provider_session_ref exists but a safe "
            "provider/session invocation boundary is missing."
        ),
        "Do not use this when": (
            "Executing provider CLIs, scraping transcripts, reading prompts, "
            "credentials, provider profiles, state DBs, MCP, generic gateways, "
            "agent adapters, or claiming live invocation/readiness."
        ),
        "If ambiguous": (
            "Return typed unavailable with exact missing provider-run refs "
            "instead of using unsafe provider material."
        ),
        "Typed unavailable when": (
            "A provider/session runner does not return provider_or_subagent_invocation_ref, "
            "exactly one typed_result_ref or typed_unavailable_ref, before_context_ref, "
            "after_context_ref, and all role_execution_refs."
        ),
        "Required evidence refs": [
            "provider_session_ref",
            "typed_task_ref",
            "provider_or_subagent_invocation_ref",
            "typed_result_ref_or_typed_unavailable_ref",
            "before_context_ref",
            "after_context_ref",
            "role_execution_refs",
            "Worker4_row_8_verification",
        ],
        "Hard nonclaims": list(hard_nonclaims),
    }


def _validate_provider_session_invocation_boundary_llm_contract(contract: Any) -> None:
    if not isinstance(contract, Mapping):
        raise ValueError("llm_facing_contract must be an object")
    missing = [
        section
        for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS
        if section not in contract
    ]
    if missing:
        raise ValueError(f"llm_facing_contract missing sections: {', '.join(missing)}")
    for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS:
        value = contract.get(section)
        if value is None or value == "" or value == []:
            raise ValueError(f"llm_facing_contract section is empty: {section}")
    _validate_provider_session_invocation_boundary_hard_nonclaims(
        contract.get("Hard nonclaims")
    )


def build_provider_subagent_ptc_provider_session_invocation_boundary(
    *,
    provider_session_ref_packet: Mapping[str, Any],
    typed_task_ref: str,
    invocation_request_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed boundary for a future provider/session invocation.

    The boundary validates the verified R22 provider_session_ref surface and a
    safe typed_task_ref. It defines the refs a provider runner must return, but
    does not execute the provider and is not live invocation proof.
    """

    validate_provider_subagent_ptc_provider_session_ref(provider_session_ref_packet)
    packet = dict(provider_session_ref_packet)
    active_provider_session_ref = _safe_portable_ref(
        packet.get("provider_session_ref"),
        field_name="provider_session_ref",
    )
    active_typed_task_ref = _safe_portable_ref(
        typed_task_ref,
        field_name="typed_task_ref",
    )
    active_provider_session_id = _safe_identifier(
        packet.get("provider_session_id"),
        field_name="provider_session_id",
    )
    active_typed_task_id = _safe_identifier(
        packet.get("typed_task_id"),
        field_name="typed_task_id",
    )
    provider_session_ref_id = _safe_identifier(
        packet.get("provider_session_ref_id"),
        field_name="provider_session_ref_id",
    )
    token = _route_token(
        active_provider_session_ref,
        active_typed_task_ref,
        provider_session_ref_id,
    )
    active_invocation_request_ref = _safe_portable_ref(
        invocation_request_ref
        or f"provider-session-invocation-request-ref://openyggdrasil/ptc/{token}",
        field_name="invocation_request_ref",
    )
    active_hard_nonclaims = (
        _normalize_provider_session_invocation_boundary_hard_nonclaims(hard_nonclaims)
    )
    boundary = {
        "schema_version": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
        ),
        "boundary_id": f"provider-session-invocation-boundary-{token}",
        "boundary_status": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
        ),
        "claim_scope": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
        ),
        "boundary_kind": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND,
        "same_run_invocation_command": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
        ),
        "provider_session_ref": active_provider_session_ref,
        "provider_session_ref_schema_version": packet.get(
            "provider_session_ref_schema_version"
        ),
        "provider_session_ref_status": packet.get("provider_session_ref_status"),
        "provider_session_ref_claim_scope": packet.get(
            "provider_session_ref_claim_scope"
        ),
        "provider_session_ref_validated": True,
        "provider_session_ref_id": provider_session_ref_id,
        "provider_session_id": active_provider_session_id,
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": active_typed_task_ref,
        "typed_task_ref_status": "boundary_input_validated",
        "invocation_request_ref": active_invocation_request_ref,
        "required_provider_run_refs": list(
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
        ),
        "provider_or_subagent_invocation_ref_status": "required_from_provider_runner",
        "typed_result_ref_status": "provider_runner_may_return_exactly_one",
        "typed_unavailable_ref_status": "provider_runner_may_return_exactly_one",
        "typed_result_or_unavailable_ref_status": (
            "required_from_provider_runner_exactly_one"
        ),
        "before_context_ref_status": "required_from_provider_runner",
        "after_context_ref_status": "required_from_provider_runner",
        "role_execution_refs_status": "required_from_provider_runner",
        "row_8_live_status": "BOUNDARY_CANDIDATE_NOT_LIVE",
        "boundary_surface_only": True,
        "safe_provider_session_invocation_boundary": True,
        "provider_runner_required": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "provider_profile_or_state_accessed": False,
        "provider_cli_executed": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "hard_nonclaims_preserved": True,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False
            for flag in (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS
            )
        },
        "llm_facing_contract": _default_provider_session_invocation_boundary_llm_contract(
            active_hard_nonclaims
        ),
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_session_invocation_boundary_built",
            "provider_session_ref_validated",
            "typed_task_ref_validated",
            "provider_runner_required_for_live_refs",
            "raw_provider_material_excluded",
            "boundary_not_live_invocation_proof",
            "hard_nonclaims_preserved",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_provider_session_invocation_boundary(boundary)
    return boundary


def validate_provider_subagent_ptc_provider_session_invocation_boundary(
    payload: Mapping[str, Any],
) -> None:
    boundary = dict(payload)
    _validate_provider_session_invocation_boundary_payload_fields(boundary)
    if (
        boundary.get("schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
    ):
        raise ValueError("invalid provider/session invocation boundary schema_version")
    if (
        boundary.get("boundary_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
    ):
        raise ValueError("invalid provider/session invocation boundary status")
    if (
        boundary.get("claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
    ):
        raise ValueError("invalid provider/session invocation boundary claim_scope")
    if (
        boundary.get("boundary_kind")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND
    ):
        raise ValueError("invalid provider/session invocation boundary kind")
    if (
        boundary.get("same_run_invocation_command")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
    ):
        raise ValueError("invalid provider/session invocation boundary command")
    _safe_identifier(boundary.get("boundary_id"), field_name="boundary_id")
    _safe_identifier(
        boundary.get("provider_session_ref_id"),
        field_name="provider_session_ref_id",
    )
    _safe_identifier(
        boundary.get("provider_session_id"),
        field_name="provider_session_id",
    )
    _safe_identifier(boundary.get("typed_task_id"), field_name="typed_task_id")
    for field in ("provider_session_ref", "typed_task_ref", "invocation_request_ref"):
        _safe_portable_ref(boundary.get(field), field_name=field)
    if (
        boundary.get("provider_session_ref_schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION
    ):
        raise ValueError("invalid source provider_session_ref schema version")
    if (
        boundary.get("provider_session_ref_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS
    ):
        raise ValueError("invalid source provider_session_ref status")
    if (
        boundary.get("provider_session_ref_claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE
    ):
        raise ValueError("invalid source provider_session_ref claim scope")
    if boundary.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    expected_statuses = {
        "typed_task_ref_status": "boundary_input_validated",
        "provider_or_subagent_invocation_ref_status": "required_from_provider_runner",
        "typed_result_ref_status": "provider_runner_may_return_exactly_one",
        "typed_unavailable_ref_status": "provider_runner_may_return_exactly_one",
        "typed_result_or_unavailable_ref_status": (
            "required_from_provider_runner_exactly_one"
        ),
        "before_context_ref_status": "required_from_provider_runner",
        "after_context_ref_status": "required_from_provider_runner",
        "role_execution_refs_status": "required_from_provider_runner",
        "row_8_live_status": "BOUNDARY_CANDIDATE_NOT_LIVE",
    }
    for field, expected in expected_statuses.items():
        if boundary.get(field) != expected:
            raise ValueError(f"invalid provider/session invocation boundary {field}")
    for field in (
        "provider_session_ref_validated",
        "boundary_surface_only",
        "safe_provider_session_invocation_boundary",
        "provider_runner_required",
        "hard_nonclaims_preserved",
        "additive_only_hard_nonclaims",
    ):
        if boundary.get(field) is not True:
            raise ValueError(f"provider/session invocation boundary requires {field}=True")
    _validate_provider_material_absence(boundary)
    for field in ("provider_profile_or_state_accessed", "provider_cli_executed"):
        if boundary.get(field) is not False:
            raise ValueError(f"provider/session invocation boundary requires {field}=False")
    _validate_provider_session_invocation_boundary_hard_nonclaims(
        boundary.get("hard_nonclaims")
    )
    _validate_provider_session_invocation_boundary_no_overclaim_flags(
        boundary.get("no_overclaim_flags")
    )
    _validate_provider_session_invocation_boundary_llm_contract(
        boundary.get("llm_facing_contract")
    )
    if boundary.get("runtime_owner") != "runtime/ptc/engine.py":
        raise ValueError(
            "provider/session invocation boundary runtime_owner must be runtime/ptc/engine.py"
        )
    reason_codes = boundary.get("reason_codes")
    if (
        not isinstance(reason_codes, Sequence)
        or isinstance(reason_codes, (str, bytes))
        or not reason_codes
    ):
        raise ValueError("reason_codes are required")


def _validate_provider_session_runner_result_payload_fields(
    payload: Mapping[str, Any],
) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in payload
    ]
    if forbidden:
        raise ValueError(
            "provider/session runner result contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in payload
        if field not in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "provider/session runner result contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _normalize_provider_session_runner_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_provider_session_runner_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider/session runner result requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider/session runner result missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_provider_session_runner_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError(
            "provider/session runner result no_overclaim_flags must be an object"
        )
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "provider/session runner result no_overclaim_flags missing: "
            + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe provider/session runner result flag: {flag_name}")


def _default_provider_session_runner_llm_contract(
    hard_nonclaims: Sequence[str],
) -> dict[str, Any]:
    return {
        "Use this when": (
            "R25 verified that a safe provider/session runner for "
            "openyggdrasil.provider_session.invoke.v1 is missing and R26 needs "
            "a fail-closed runner result surface."
        ),
        "Do not use this when": (
            "Claiming real provider/subagent invocation, executing provider CLIs, "
            "scraping transcripts, reading prompts, credentials, provider profiles, "
            "state DBs, MCP, generic gateways, or agent adapters."
        ),
        "If ambiguous": (
            "Return typed unavailable refs with exact missing provider-run terms "
            "instead of using unsafe provider material."
        ),
        "Typed unavailable when": (
            "No safe provider runner executor is available to return a real "
            "provider_or_subagent_invocation_ref, before_context_ref, "
            "after_context_ref, and role_execution_refs."
        ),
        "Required evidence refs": [
            "provider_session_ref",
            "typed_task_ref",
            "provider_or_subagent_invocation_ref_or_typed_unavailable_ref",
            "typed_result_ref_or_typed_unavailable_ref",
            "before_context_ref_or_typed_unavailable_ref",
            "after_context_ref_or_typed_unavailable_ref",
            "role_execution_refs_or_typed_unavailable_refs",
            "Worker4_row_8_verification",
        ],
        "Hard nonclaims": list(hard_nonclaims),
    }


def _validate_provider_session_runner_llm_contract(contract: Any) -> None:
    if not isinstance(contract, Mapping):
        raise ValueError("llm_facing_contract must be an object")
    missing = [
        section
        for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS
        if section not in contract
    ]
    if missing:
        raise ValueError(f"llm_facing_contract missing sections: {', '.join(missing)}")
    for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS:
        value = contract.get(section)
        if value is None or value == "" or value == []:
            raise ValueError(f"llm_facing_contract section is empty: {section}")
    _validate_provider_session_runner_hard_nonclaims(contract.get("Hard nonclaims"))


def build_provider_subagent_ptc_provider_session_runner_typed_unavailable_result(
    *,
    provider_session_invocation_boundary: Mapping[str, Any],
    unavailable_reason_code: str = (
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_UNAVAILABLE_REASON
    ),
    typed_unavailable_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed provider/session runner result from an R24 boundary.

    This is a runner surface enablement, not a provider executor. When no safe
    executor is available it emits typed-unavailable refs for the required
    provider-run terms and preserves the bounded R24 command contract.
    """

    validate_provider_subagent_ptc_provider_session_invocation_boundary(
        provider_session_invocation_boundary
    )
    boundary = dict(provider_session_invocation_boundary)
    active_reason = _safe_identifier(
        unavailable_reason_code,
        field_name="unavailable_reason_code",
    )
    token = _route_token(
        boundary["boundary_id"],
        boundary["typed_task_ref"],
        active_reason,
    )
    base_unavailable_ref = typed_unavailable_ref or (
        f"typed-unavailable-ref://openyggdrasil/provider-session-runner/{token}"
    )
    active_typed_unavailable_ref = _safe_portable_ref(
        base_unavailable_ref,
        field_name="typed_unavailable_ref",
    )
    provider_invocation_typed_unavailable_ref = _safe_portable_ref(
        f"{active_typed_unavailable_ref}/provider-or-subagent-invocation",
        field_name="provider_or_subagent_invocation_typed_unavailable_ref",
    )
    before_context_typed_unavailable_ref = _safe_portable_ref(
        f"{active_typed_unavailable_ref}/before-context",
        field_name="before_context_typed_unavailable_ref",
    )
    after_context_typed_unavailable_ref = _safe_portable_ref(
        f"{active_typed_unavailable_ref}/after-context",
        field_name="after_context_typed_unavailable_ref",
    )
    role_execution_typed_unavailable_refs = {
        role: f"{active_typed_unavailable_ref}/role/{role}"
        for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES
    }
    normalized_role_unavailable_refs = _normalize_strict_role_map(
        role_execution_typed_unavailable_refs,
        field_name="role_execution_typed_unavailable_refs",
    )
    active_hard_nonclaims = _normalize_provider_session_runner_hard_nonclaims(
        hard_nonclaims
    )
    result = {
        "schema_version": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION
        ),
        "runner_result_id": f"provider-session-runner-result-{token}",
        "runner_result_status": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS
        ),
        "runner_result_kind": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND
        ),
        "claim_scope": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE,
        "same_run_invocation_command": boundary["same_run_invocation_command"],
        "boundary_id": boundary["boundary_id"],
        "boundary_status": boundary["boundary_status"],
        "boundary_schema_version": boundary["schema_version"],
        "boundary_claim_scope": boundary["claim_scope"],
        "provider_session_ref": boundary["provider_session_ref"],
        "provider_session_ref_validated": True,
        "typed_task_id": boundary["typed_task_id"],
        "typed_task_ref": boundary["typed_task_ref"],
        "invocation_request_ref": boundary["invocation_request_ref"],
        "provider_or_subagent_invocation_ref": None,
        "provider_or_subagent_invocation_typed_unavailable_ref": (
            provider_invocation_typed_unavailable_ref
        ),
        "provider_or_subagent_invocation_unavailable": active_reason,
        "typed_result_ref": None,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": None,
        "before_context_typed_unavailable_ref": before_context_typed_unavailable_ref,
        "before_context_unavailable": "before_context_ref_not_returned_without_provider_runner",
        "after_context_ref": None,
        "after_context_typed_unavailable_ref": after_context_typed_unavailable_ref,
        "after_context_unavailable": "after_context_ref_not_returned_without_provider_runner",
        "role_execution_refs": None,
        "role_execution_typed_unavailable_refs": normalized_role_unavailable_refs,
        "role_execution_refs_unavailable": (
            "role_execution_refs_not_returned_without_provider_runner"
        ),
        "required_provider_run_refs": boundary["required_provider_run_refs"],
        "runner_surface_only": True,
        "provider_runner_executor_available": False,
        "safe_typed_unavailable_refs_emitted": True,
        "row_8_live_status": "RUNNER_TYPED_UNAVAILABLE_NOT_LIVE",
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "provider_profile_or_state_accessed": False,
        "provider_cli_executed": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "hard_nonclaims_preserved": True,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False
            for flag in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS
        },
        "llm_facing_contract": _default_provider_session_runner_llm_contract(
            active_hard_nonclaims
        ),
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_session_runner_typed_unavailable_surface_built",
            active_reason,
            "provider_session_invocation_boundary_validated",
            "unsafe_provider_material_not_used",
            "hard_nonclaims_preserved",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_provider_session_runner_result(result)
    return result


def validate_provider_subagent_ptc_provider_session_runner_result(
    payload: Mapping[str, Any],
) -> None:
    result = dict(payload)
    _validate_provider_session_runner_result_payload_fields(result)
    if (
        result.get("schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION
    ):
        raise ValueError("invalid provider/session runner result schema_version")
    if (
        result.get("runner_result_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS
    ):
        raise ValueError("invalid provider/session runner result status")
    if (
        result.get("runner_result_kind")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND
    ):
        raise ValueError("invalid provider/session runner result kind")
    if (
        result.get("claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE
    ):
        raise ValueError("invalid provider/session runner result claim_scope")
    if (
        result.get("same_run_invocation_command")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
    ):
        raise ValueError("invalid provider/session runner result command")
    if (
        result.get("boundary_schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
    ):
        raise ValueError("invalid provider/session runner boundary schema")
    if (
        result.get("boundary_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
    ):
        raise ValueError("invalid provider/session runner boundary status")
    if (
        result.get("boundary_claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
    ):
        raise ValueError("invalid provider/session runner boundary claim_scope")
    _safe_identifier(result.get("runner_result_id"), field_name="runner_result_id")
    _safe_identifier(result.get("boundary_id"), field_name="boundary_id")
    _safe_identifier(result.get("typed_task_id"), field_name="typed_task_id")
    _safe_identifier(
        result.get("provider_or_subagent_invocation_unavailable"),
        field_name="provider_or_subagent_invocation_unavailable",
    )
    for field in (
        "provider_session_ref",
        "typed_task_ref",
        "invocation_request_ref",
        "provider_or_subagent_invocation_typed_unavailable_ref",
        "typed_unavailable_ref",
        "before_context_typed_unavailable_ref",
        "after_context_typed_unavailable_ref",
    ):
        _safe_portable_ref(result.get(field), field_name=field)
    if result.get("provider_or_subagent_invocation_ref") is not None:
        raise ValueError(
            "provider/session runner typed-unavailable result must not claim provider_or_subagent_invocation_ref"
        )
    if result.get("typed_result_ref") is not None:
        raise ValueError(
            "provider/session runner typed-unavailable result must not claim typed_result_ref"
        )
    if result.get("before_context_ref") is not None:
        raise ValueError(
            "provider/session runner typed-unavailable result must not claim before_context_ref"
        )
    if result.get("after_context_ref") is not None:
        raise ValueError(
            "provider/session runner typed-unavailable result must not claim after_context_ref"
        )
    if result.get("role_execution_refs") is not None:
        raise ValueError(
            "provider/session runner typed-unavailable result must not claim role_execution_refs"
        )
    role_unavailable_refs = _normalize_strict_role_map(
        result.get("role_execution_typed_unavailable_refs") or {},
        field_name="role_execution_typed_unavailable_refs",
    )
    if result.get("role_execution_typed_unavailable_refs") != role_unavailable_refs:
        raise ValueError("role_execution_typed_unavailable_refs must be normalized")
    for field in (
        "before_context_unavailable",
        "after_context_unavailable",
        "role_execution_refs_unavailable",
    ):
        _safe_identifier(result.get(field), field_name=field)
    if result.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    for field in (
        "provider_session_ref_validated",
        "runner_surface_only",
        "safe_typed_unavailable_refs_emitted",
        "hard_nonclaims_preserved",
        "additive_only_hard_nonclaims",
    ):
        if result.get(field) is not True:
            raise ValueError(f"provider/session runner result requires {field}=True")
    if result.get("provider_runner_executor_available") is not False:
        raise ValueError(
            "provider/session runner result requires provider_runner_executor_available=False"
        )
    if result.get("row_8_live_status") != "RUNNER_TYPED_UNAVAILABLE_NOT_LIVE":
        raise ValueError("provider/session runner result must keep row_8 not live")
    _validate_provider_material_absence(result)
    for field in ("provider_profile_or_state_accessed", "provider_cli_executed"):
        if result.get(field) is not False:
            raise ValueError(f"provider/session runner result requires {field}=False")
    _validate_provider_session_runner_hard_nonclaims(result.get("hard_nonclaims"))
    _validate_provider_session_runner_no_overclaim_flags(
        result.get("no_overclaim_flags")
    )
    _validate_provider_session_runner_llm_contract(result.get("llm_facing_contract"))
    if result.get("runtime_owner") != "runtime/ptc/engine.py":
        raise ValueError(
            "provider/session runner result runtime_owner must be runtime/ptc/engine.py"
        )
    reason_codes = result.get("reason_codes")
    if (
        not isinstance(reason_codes, Sequence)
        or isinstance(reason_codes, (str, bytes))
        or not reason_codes
    ):
        raise ValueError("reason_codes are required")


def _validate_provider_session_executor_boundary_payload_fields(
    payload: Mapping[str, Any],
) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in payload
    ]
    if forbidden:
        raise ValueError(
            "provider/session executor boundary contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in payload
        if field
        not in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "provider/session executor boundary contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _normalize_provider_session_executor_boundary_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_provider_session_executor_boundary_hard_nonclaims(
    hard_nonclaims: Any,
) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("provider/session executor boundary requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("provider/session executor boundary missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_provider_session_executor_boundary_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError(
            "provider/session executor boundary no_overclaim_flags must be an object"
        )
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "provider/session executor boundary no_overclaim_flags missing: "
            + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(
                f"unsafe provider/session executor boundary flag: {flag_name}"
            )


def _require_safe_ref_prefix(value: str, *, field_name: str, prefixes: Sequence[str]) -> str:
    active = _safe_portable_ref(value, field_name=field_name)
    if not any(active.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"{field_name} has invalid safe ref scheme")
    lowered = active.lower()
    if "typed-unavailable" in lowered or "unavailable" in lowered:
        raise ValueError(f"{field_name} must be non-unavailable")
    return active


def _default_provider_session_executor_boundary_llm_contract(
    hard_nonclaims: Sequence[str],
) -> dict[str, Any]:
    return {
        "Use this when": (
            "R26 verified only a typed-unavailable provider/session runner "
            "surface and R27 needs a bounded executor-ref validator over the "
            "R24 provider/session invocation boundary."
        ),
        "Do not use this when": (
            "Executing provider CLIs, scraping transcripts, reading prompts, "
            "credentials, provider profiles, state DBs, MCP, generic gateways, "
            "agent adapters, or claiming row 8 LIVE/readiness from boundary validation."
        ),
        "If ambiguous": (
            "Return typed unavailable with exact missing executor source refs "
            "instead of accepting raw provider material or relabeling a boundary "
            "as live invocation."
        ),
        "Typed unavailable when": (
            "A safe caller-verified executor source packet cannot provide "
            "provider_or_subagent_invocation_ref, typed_result_ref, "
            "before_context_ref, after_context_ref, and all role_execution_refs."
        ),
        "Required evidence refs": [
            "provider_session_invocation_boundary",
            "executor_boundary_ref",
            "provider_or_subagent_invocation_ref",
            "typed_result_ref",
            "before_context_ref",
            "after_context_ref",
            "role_execution_refs",
            "Worker4_row_8_verification",
        ],
        "Hard nonclaims": list(hard_nonclaims),
    }


def _validate_provider_session_executor_boundary_llm_contract(contract: Any) -> None:
    if not isinstance(contract, Mapping):
        raise ValueError("llm_facing_contract must be an object")
    missing = [
        section
        for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS
        if section not in contract
    ]
    if missing:
        raise ValueError(f"llm_facing_contract missing sections: {', '.join(missing)}")
    for section in PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS:
        value = contract.get(section)
        if value is None or value == "" or value == []:
            raise ValueError(f"llm_facing_contract section is empty: {section}")
    _validate_provider_session_executor_boundary_hard_nonclaims(
        contract.get("Hard nonclaims")
    )


def materialize_provider_subagent_ptc_provider_session_executor_boundary(
    *,
    provider_session_invocation_boundary: Mapping[str, Any],
    executor_result_packet: Mapping[str, Any],
    boundary_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate caller-supplied provider/session executor refs over R24.

    The runtime validates safe ref shape and no-overclaim flags only. It does
    not execute provider/subagent work and does not turn the refs into row 8 LIVE
    proof without later Worker 4 live verification.
    """

    validate_provider_subagent_ptc_provider_session_invocation_boundary(
        provider_session_invocation_boundary
    )
    boundary_input = dict(provider_session_invocation_boundary)
    if not isinstance(executor_result_packet, Mapping):
        raise ValueError("executor_result_packet must be an object")
    packet = dict(executor_result_packet)
    _validate_provider_session_executor_boundary_payload_fields(packet)
    _validate_provider_material_absence(packet)
    if (
        packet.get("executor_boundary_kind")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND
    ):
        raise ValueError("provider/session executor boundary kind is invalid")
    if (
        packet.get("executor_evidence_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS
    ):
        raise ValueError("provider/session executor evidence status is invalid")
    if packet.get("fixture_refs_used") is not False:
        raise ValueError("provider/session executor boundary must not use fixture refs")
    if packet.get("non_fixture_refs_only") is not True:
        raise ValueError(
            "provider/session executor boundary requires non_fixture_refs_only=True"
        )
    if (
        packet.get("same_run_invocation_command")
        != boundary_input.get("same_run_invocation_command")
    ):
        raise ValueError(
            "provider/session executor boundary command must match R24 boundary"
        )
    if packet.get("provider_session_ref") != boundary_input.get("provider_session_ref"):
        raise ValueError(
            "provider/session executor boundary provider_session_ref must match R24 boundary"
        )
    active_typed_task_id = _safe_identifier(
        packet.get("typed_task_id"),
        field_name="typed_task_id",
    )
    if active_typed_task_id != boundary_input.get("typed_task_id"):
        raise ValueError(
            "provider/session executor boundary typed_task_id must match R24 boundary"
        )
    for field in ("typed_task_ref", "invocation_request_ref"):
        if packet.get(field) != boundary_input.get(field):
            raise ValueError(
                f"provider/session executor boundary {field} must match R24 boundary"
            )

    active_executor_boundary_ref = _safe_portable_ref(
        packet.get("executor_boundary_ref"),
        field_name="executor_boundary_ref",
    )
    active_provider_session_ref = _safe_portable_ref(
        packet.get("provider_session_ref"),
        field_name="provider_session_ref",
    )
    active_typed_task_ref = _safe_portable_ref(
        packet.get("typed_task_ref"),
        field_name="typed_task_ref",
    )
    active_invocation_request_ref = _safe_portable_ref(
        packet.get("invocation_request_ref"),
        field_name="invocation_request_ref",
    )
    active_invocation_ref = _require_safe_ref_prefix(
        packet.get("provider_or_subagent_invocation_ref"),
        field_name="provider_or_subagent_invocation_ref",
        prefixes=(
            "provider-session-invocation-ref://",
            "provider-subagent-invocation-ref://",
        ),
    )
    active_role_execution_refs = _normalize_strict_role_map(
        packet.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    active_role_execution_refs = {
        role: _require_safe_ref_prefix(
            ref,
            field_name=f"role_execution_refs.{role}",
            prefixes=("role-execution-ref://",),
        )
        for role, ref in active_role_execution_refs.items()
    }
    active_typed_result_ref = _require_safe_ref_prefix(
        packet.get("typed_result_ref"),
        field_name="typed_result_ref",
        prefixes=("typed-result-ref://",),
    )
    if packet.get("typed_unavailable_ref") is not None:
        raise ValueError(
            "provider/session executor boundary requires typed_result_ref, not typed_unavailable_ref"
        )
    active_before_context_ref = _require_safe_ref_prefix(
        packet.get("before_context_ref"),
        field_name="before_context_ref",
        prefixes=("context-ref://",),
    )
    active_after_context_ref = _require_safe_ref_prefix(
        packet.get("after_context_ref"),
        field_name="after_context_ref",
        prefixes=("context-ref://",),
    )
    _reject_fixture_typed_ref_terms(
        active_executor_boundary_ref,
        active_provider_session_ref,
        active_typed_task_ref,
        active_invocation_request_ref,
        active_invocation_ref,
        active_role_execution_refs,
        active_typed_result_ref,
        active_before_context_ref,
        active_after_context_ref,
    )
    active_hard_nonclaims = _normalize_provider_session_executor_boundary_hard_nonclaims(
        packet.get("hard_nonclaims")
    )
    active_no_overclaim_flags = dict(
        packet.get("no_overclaim_flags")
        or {
            flag: False
            for flag in (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAGS
            )
        }
    )
    _validate_provider_session_executor_boundary_no_overclaim_flags(
        active_no_overclaim_flags
    )
    packet_reason_codes = _string_list(
        packet.get("reason_codes"),
        field_name="executor_result_packet.reason_codes",
    )
    if not packet_reason_codes:
        raise ValueError("provider/session executor boundary reason_codes are required")
    token = _route_token(
        boundary_input["boundary_id"],
        active_executor_boundary_ref,
        active_provider_session_ref,
        active_invocation_ref,
        active_typed_result_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_boundary_ref = _safe_portable_ref(
        boundary_ref
        or f"provider-session-executor-boundary-ref://openyggdrasil/ptc/{token}",
        field_name="boundary_ref",
    )
    executor_boundary = {
        "schema_version": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION
        ),
        "boundary_id": f"provider-session-executor-boundary-{token}",
        "boundary_ref": active_boundary_ref,
        "executor_boundary_ref": active_executor_boundary_ref,
        "executor_boundary_status": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS
        ),
        "claim_scope": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE
        ),
        "executor_boundary_kind": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND
        ),
        "executor_evidence_status": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS
        ),
        "same_run_invocation_command": boundary_input["same_run_invocation_command"],
        "provider_session_invocation_boundary_id": boundary_input["boundary_id"],
        "provider_session_invocation_boundary_status": boundary_input[
            "boundary_status"
        ],
        "provider_session_invocation_boundary_claim_scope": boundary_input[
            "claim_scope"
        ],
        "provider_session_ref": active_provider_session_ref,
        "provider_session_ref_validated": True,
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": active_typed_task_ref,
        "invocation_request_ref": active_invocation_request_ref,
        "required_provider_run_refs": list(
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
        ),
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": None,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "executor_result_packet_validated": True,
        "executor_refs_validated": True,
        "typed_result_ref_validated": True,
        "context_refs_validated": True,
        "role_execution_refs_validated": True,
        "safe_refs_only": True,
        "non_fixture_refs_only": True,
        "fixture_refs_used": False,
        "executor_boundary_only": True,
        "executor_executed_by_runtime": False,
        "row_8_live_status": "EXECUTOR_BOUNDARY_NOT_LIVE_UNTIL_WORKER4_LIVE_VERIFICATION",
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "provider_profile_or_state_accessed": False,
        "provider_cli_executed": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "hard_nonclaims_preserved": True,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": active_no_overclaim_flags,
        "llm_facing_contract": _default_provider_session_executor_boundary_llm_contract(
            active_hard_nonclaims
        ),
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_session_executor_boundary_validated",
            "r24_provider_session_invocation_boundary_validated",
            "executor_result_packet_safe_refs_validated",
            "non_unavailable_provider_run_refs_validated",
            "boundary_not_live_invocation_proof",
            "hard_nonclaims_preserved",
            *packet_reason_codes,
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_provider_session_executor_boundary(
        executor_boundary
    )
    return executor_boundary


def validate_provider_subagent_ptc_provider_session_executor_boundary(
    payload: Mapping[str, Any],
) -> None:
    boundary = dict(payload)
    _validate_provider_session_executor_boundary_payload_fields(boundary)
    if (
        boundary.get("schema_version")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION
    ):
        raise ValueError("invalid provider/session executor boundary schema_version")
    if (
        boundary.get("executor_boundary_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS
    ):
        raise ValueError("invalid provider/session executor boundary status")
    if (
        boundary.get("claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE
    ):
        raise ValueError("invalid provider/session executor boundary claim_scope")
    if (
        boundary.get("executor_boundary_kind")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND
    ):
        raise ValueError("invalid provider/session executor boundary kind")
    if (
        boundary.get("executor_evidence_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS
    ):
        raise ValueError("invalid provider/session executor boundary evidence status")
    if (
        boundary.get("same_run_invocation_command")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
    ):
        raise ValueError("invalid provider/session executor boundary command")
    if (
        boundary.get("provider_session_invocation_boundary_status")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
    ):
        raise ValueError("invalid source provider/session invocation boundary status")
    if (
        boundary.get("provider_session_invocation_boundary_claim_scope")
        != PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
    ):
        raise ValueError("invalid source provider/session invocation boundary claim")
    _safe_identifier(boundary.get("boundary_id"), field_name="boundary_id")
    _safe_identifier(
        boundary.get("provider_session_invocation_boundary_id"),
        field_name="provider_session_invocation_boundary_id",
    )
    _safe_identifier(boundary.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "boundary_ref",
        "executor_boundary_ref",
        "provider_session_ref",
        "typed_task_ref",
        "invocation_request_ref",
    ):
        _safe_portable_ref(boundary.get(field), field_name=field)
    _require_safe_ref_prefix(
        boundary.get("provider_or_subagent_invocation_ref"),
        field_name="provider_or_subagent_invocation_ref",
        prefixes=(
            "provider-session-invocation-ref://",
            "provider-subagent-invocation-ref://",
        ),
    )
    role_refs = _normalize_strict_role_map(
        boundary.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    if boundary.get("role_execution_refs") != role_refs:
        raise ValueError("role_execution_refs must be normalized required role refs")
    for role, ref in role_refs.items():
        _require_safe_ref_prefix(
            ref,
            field_name=f"role_execution_refs.{role}",
            prefixes=("role-execution-ref://",),
        )
    _require_safe_ref_prefix(
        boundary.get("typed_result_ref"),
        field_name="typed_result_ref",
        prefixes=("typed-result-ref://",),
    )
    if boundary.get("typed_unavailable_ref") is not None:
        raise ValueError(
            "provider/session executor boundary must not carry typed_unavailable_ref"
        )
    _require_safe_ref_prefix(
        boundary.get("before_context_ref"),
        field_name="before_context_ref",
        prefixes=("context-ref://",),
    )
    _require_safe_ref_prefix(
        boundary.get("after_context_ref"),
        field_name="after_context_ref",
        prefixes=("context-ref://",),
    )
    if boundary.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    for field in (
        "provider_session_ref_validated",
        "executor_result_packet_validated",
        "executor_refs_validated",
        "typed_result_ref_validated",
        "context_refs_validated",
        "role_execution_refs_validated",
        "safe_refs_only",
        "non_fixture_refs_only",
        "executor_boundary_only",
        "hard_nonclaims_preserved",
        "additive_only_hard_nonclaims",
    ):
        if boundary.get(field) is not True:
            raise ValueError(
                f"provider/session executor boundary requires {field}=True"
            )
    for field in ("fixture_refs_used", "executor_executed_by_runtime"):
        if boundary.get(field) is not False:
            raise ValueError(
                f"provider/session executor boundary requires {field}=False"
            )
    if (
        boundary.get("row_8_live_status")
        != "EXECUTOR_BOUNDARY_NOT_LIVE_UNTIL_WORKER4_LIVE_VERIFICATION"
    ):
        raise ValueError("provider/session executor boundary must keep row 8 not live")
    _validate_provider_material_absence(boundary)
    for field in ("provider_profile_or_state_accessed", "provider_cli_executed"):
        if boundary.get(field) is not False:
            raise ValueError(
                f"provider/session executor boundary requires {field}=False"
            )
    _validate_provider_session_executor_boundary_hard_nonclaims(
        boundary.get("hard_nonclaims")
    )
    _validate_provider_session_executor_boundary_no_overclaim_flags(
        boundary.get("no_overclaim_flags")
    )
    _validate_provider_session_executor_boundary_llm_contract(
        boundary.get("llm_facing_contract")
    )
    _reject_fixture_typed_ref_terms(
        boundary.get("boundary_ref"),
        boundary.get("executor_boundary_ref"),
        boundary.get("provider_session_ref"),
        boundary.get("typed_task_ref"),
        boundary.get("invocation_request_ref"),
        boundary.get("provider_or_subagent_invocation_ref"),
        role_refs,
        boundary.get("typed_result_ref"),
        boundary.get("before_context_ref"),
        boundary.get("after_context_ref"),
    )
    if boundary.get("runtime_owner") != "runtime/ptc/engine.py":
        raise ValueError(
            "provider/session executor boundary runtime_owner must be runtime/ptc/engine.py"
        )
    reason_codes = boundary.get("reason_codes")
    if (
        not isinstance(reason_codes, Sequence)
        or isinstance(reason_codes, (str, bytes))
        or not reason_codes
    ):
        raise ValueError("reason_codes are required")


def build_provider_subagent_ptc_invocation_command(
    *,
    execution_trace_packet: Mapping[str, Any],
    typed_task_id: str,
    typed_task_ref: str,
    invocation_request_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the bounded local command contract for a later same-run invocation.

    The command enables an R7 runner to attempt provider/subagent execution over
    the verified packet surface. It does not call a provider and cannot be used
    as proof that provider/subagent execution happened.
    """

    validate_provider_subagent_ptc_execution_trace_packet(execution_trace_packet)
    packet = dict(execution_trace_packet)
    active_typed_task_id = _safe_identifier(typed_task_id, field_name="typed_task_id")
    active_typed_task_ref = _safe_portable_ref(typed_task_ref, field_name="typed_task_ref")
    execution_trace_ref = _safe_portable_ref(
        packet.get("execution_trace_ref"),
        field_name="execution_trace_ref",
    )
    ptc_telemetry_ref = _safe_portable_ref(
        packet.get("ptc_telemetry_ref"),
        field_name="ptc_telemetry_ref",
    )
    token = _route_token(active_typed_task_id, active_typed_task_ref, execution_trace_ref)
    active_invocation_request_ref = _safe_portable_ref(
        invocation_request_ref
        or f"provider-subagent-invocation-request-ref://openyggdrasil/ptc/{token}",
        field_name="invocation_request_ref",
    )
    active_hard_nonclaims = _normalize_invocation_hard_nonclaims(hard_nonclaims)
    command = {
        "schema_version": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION,
        "command_id": f"provider-subagent-ptc-invocation-command-{token}",
        "same_run_invocation_command": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME,
        "command_status": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_CLAIM_SCOPE,
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": active_typed_task_ref,
        "typed_task_id_contract": "safe_identifier_required",
        "invocation_request_ref": active_invocation_request_ref,
        "execution_trace_ref": execution_trace_ref,
        "ptc_telemetry_ref": ptc_telemetry_ref,
        "execution_trace_packet_schema_version": packet.get("schema_version"),
        "execution_trace_packet_status": packet.get("execution_trace_status"),
        "execution_trace_packet_validated": True,
        "required_request_refs": {
            "typed_task_ref": active_typed_task_ref,
            "execution_trace_ref": execution_trace_ref,
            "ptc_telemetry_ref": ptc_telemetry_ref,
        },
        "required_response_refs": list(PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS),
        "typed_result_unavailable_contract": (
            "exactly_one_of_typed_result_ref_or_typed_unavailable_ref_required"
        ),
        "context_ref_contract": (
            "before_context_ref_and_after_context_ref_required_or_exact_unavailable_reason"
        ),
        "role_execution_ref_contract": "all_required_ptc_role_execution_refs_required",
        "provider_boundary_contract": (
            "no_mcp_no_generic_gateway_no_agent_adapter_no_raw_provider_material"
        ),
        "llm_facing_contract": _default_provider_subagent_invocation_llm_contract(
            active_hard_nonclaims
        ),
        "command_surface_only": True,
        "r7_same_run_attempt_enabled": True,
        "safe_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False for flag in PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS
        },
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_subagent_ptc_invocation_command_surface_built",
            "execution_trace_packet_validated",
            "safe_refs_only",
            "hard_nonclaims_preserved",
            "provider_subagent_invocation_not_claimed",
            "typed_unavailable_fallback_required_without_runner_response",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_invocation_command(command)
    return command


def validate_provider_subagent_ptc_invocation_command(payload: Mapping[str, Any]) -> None:
    command = dict(payload)
    if command.get("schema_version") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent PTC invocation command schema_version")
    if command.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent PTC invocation command name")
    if command.get("command_status") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS:
        raise ValueError("invalid provider/subagent PTC invocation command status")
    if command.get("claim_scope") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_CLAIM_SCOPE:
        raise ValueError("invalid provider/subagent PTC invocation command claim_scope")
    _safe_identifier(command.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "typed_task_ref",
        "invocation_request_ref",
        "execution_trace_ref",
        "ptc_telemetry_ref",
    ):
        _safe_portable_ref(command.get(field), field_name=field)
    if command.get("typed_task_id_contract") != "safe_identifier_required":
        raise ValueError("typed_task_id_contract must require safe identifiers")
    request_refs = command.get("required_request_refs")
    if not isinstance(request_refs, Mapping):
        raise ValueError("required_request_refs must be an object")
    for field in ("typed_task_ref", "execution_trace_ref", "ptc_telemetry_ref"):
        _safe_portable_ref(request_refs.get(field), field_name=f"required_request_refs.{field}")
        if request_refs.get(field) != command.get(field):
            raise ValueError(f"required_request_refs.{field} must match command field")
    if command.get("required_response_refs") != list(
        PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
    ):
        raise ValueError("required_response_refs must match provider/subagent invocation contract")
    for field in (
        "execution_trace_packet_validated",
        "command_surface_only",
        "r7_same_run_attempt_enabled",
        "safe_refs_only",
        "additive_only_hard_nonclaims",
    ):
        if command.get(field) is not True:
            raise ValueError(f"provider/subagent invocation command requires {field}=True")
    for field in (
        "typed_result_unavailable_contract",
        "context_ref_contract",
        "role_execution_ref_contract",
        "provider_boundary_contract",
    ):
        if not str(command.get(field) or "").strip():
            raise ValueError(f"{field} is required")
    _validate_invocation_llm_contract(command.get("llm_facing_contract"))
    _validate_provider_material_absence(command)
    _validate_invocation_hard_nonclaims(command.get("hard_nonclaims"))
    _validate_invocation_no_overclaim_flags(command.get("no_overclaim_flags"))
    reason_codes = command.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("reason_codes are required")


def build_provider_subagent_ptc_invocation_unavailable_result(
    *,
    invocation_command: Mapping[str, Any],
    unavailable_reason_code: str = "provider_subagent_invocation_runner_response_unavailable",
    typed_unavailable_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a typed-unavailable invocation result without unsafe provider material."""

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    active_reason = _safe_identifier(
        unavailable_reason_code,
        field_name="unavailable_reason_code",
    )
    token = _route_token(command.get("command_id"), command.get("typed_task_id"), active_reason)
    active_typed_unavailable_ref = _safe_portable_ref(
        typed_unavailable_ref
        or f"typed-unavailable-ref://openyggdrasil/provider-subagent-ptc-invocation/{token}",
        field_name="typed_unavailable_ref",
    )
    result = {
        "schema_version": PROVIDER_SUBAGENT_PTC_INVOCATION_UNAVAILABLE_RESULT_SCHEMA_VERSION,
        "invocation_status": "typed_unavailable",
        "same_run_invocation_command": command["same_run_invocation_command"],
        "command_id": command["command_id"],
        "typed_task_id": command["typed_task_id"],
        "typed_task_ref": command["typed_task_ref"],
        "invocation_request_ref": command["invocation_request_ref"],
        "execution_trace_ref": command["execution_trace_ref"],
        "ptc_telemetry_ref": command["ptc_telemetry_ref"],
        "provider_or_subagent_invocation_ref": None,
        "provider_or_subagent_invocation_unavailable": active_reason,
        "typed_result_ref": None,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": None,
        "before_context_unavailable": "before_context_ref_not_returned_without_invocation",
        "after_context_ref": None,
        "after_context_unavailable": "after_context_ref_not_returned_without_invocation",
        "role_execution_refs": None,
        "required_response_refs": command["required_response_refs"],
        "typed_result_unavailable_contract": command["typed_result_unavailable_contract"],
        "context_ref_contract": command["context_ref_contract"],
        "command_surface_only": True,
        "safe_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": list(command["hard_nonclaims"]),
        "no_overclaim_flags": dict(command["no_overclaim_flags"]),
        "reason_codes": [
            "provider_subagent_invocation_returned_typed_unavailable",
            active_reason,
            "unsafe_provider_material_not_used",
            "hard_nonclaims_preserved",
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_invocation_unavailable_result(result)
    return result


def validate_provider_subagent_ptc_invocation_unavailable_result(
    payload: Mapping[str, Any],
) -> None:
    result = dict(payload)
    if result.get("schema_version") != PROVIDER_SUBAGENT_PTC_INVOCATION_UNAVAILABLE_RESULT_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent PTC invocation unavailable schema_version")
    if result.get("invocation_status") != "typed_unavailable":
        raise ValueError("provider/subagent PTC invocation result must be typed_unavailable")
    if result.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent PTC invocation command name")
    _safe_identifier(result.get("typed_task_id"), field_name="typed_task_id")
    _safe_identifier(
        result.get("provider_or_subagent_invocation_unavailable"),
        field_name="provider_or_subagent_invocation_unavailable",
    )
    for field in (
        "typed_task_ref",
        "invocation_request_ref",
        "execution_trace_ref",
        "ptc_telemetry_ref",
        "typed_unavailable_ref",
    ):
        _safe_portable_ref(result.get(field), field_name=field)
    if result.get("provider_or_subagent_invocation_ref") is not None:
        raise ValueError("typed unavailable result must not include invocation ref")
    if result.get("typed_result_ref") is not None:
        raise ValueError("typed unavailable result must not include typed_result_ref")
    if result.get("before_context_ref") is not None or result.get("after_context_ref") is not None:
        raise ValueError("typed unavailable result must not include context refs")
    for field in ("before_context_unavailable", "after_context_unavailable"):
        _safe_identifier(result.get(field), field_name=field)
    if result.get("role_execution_refs") is not None:
        raise ValueError("typed unavailable result must not include role_execution_refs")
    if result.get("required_response_refs") != list(
        PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
    ):
        raise ValueError("required_response_refs must match provider/subagent invocation contract")
    for field in ("command_surface_only", "safe_refs_only", "additive_only_hard_nonclaims"):
        if result.get(field) is not True:
            raise ValueError(f"provider/subagent invocation result requires {field}=True")
    _validate_provider_material_absence(result)
    _validate_invocation_hard_nonclaims(result.get("hard_nonclaims"))
    _validate_invocation_no_overclaim_flags(result.get("no_overclaim_flags"))
    reason_codes = result.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("reason_codes are required")


def _validate_runner_response_payload_fields(runner_response: Mapping[str, Any]) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in runner_response
    ]
    if forbidden:
        raise ValueError(
            "runner response contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in runner_response
        if field not in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "runner response contains unsupported fields: " + ", ".join(sorted(unsupported))
        )


def _normalize_runner_response_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    runner_hard_nonclaims = _string_list(hard_nonclaims, field_name="runner_response.hard_nonclaims")
    if not runner_hard_nonclaims:
        raise ValueError("runner response requires hard_nonclaims")
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        *runner_hard_nonclaims,
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_runner_response_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("runner response ingress requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("runner response ingress missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_runner_response_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("runner response no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(f"runner response no_overclaim_flags missing: {', '.join(missing)}")
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe provider/subagent runner response flag: {flag_name}")


def _validate_same_run_typed_ref_source_payload_fields(source_packet: Mapping[str, Any]) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in source_packet
    ]
    if forbidden:
        raise ValueError(
            "same-run typed ref source contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in source_packet
        if field not in PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "same-run typed ref source contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _reject_fixture_typed_ref_terms(*refs: Any) -> None:
    flattened: list[str] = []
    for ref in refs:
        if isinstance(ref, Mapping):
            flattened.extend(str(value) for value in ref.values())
        elif isinstance(ref, Sequence) and not isinstance(ref, (str, bytes)):
            flattened.extend(str(value) for value in ref)
        elif ref is not None:
            flattened.append(str(ref))
    rendered = "\n".join(flattened).lower()
    if any(token in rendered for token in PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS):
        raise ValueError("same-run typed ref source must not use fixture refs")


def _normalize_same_run_typed_ref_source_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_same_run_typed_ref_source_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("same-run typed ref source requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("same-run typed ref source missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_same_run_typed_ref_source_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("same-run typed ref source no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "same-run typed ref source no_overclaim_flags missing: " + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe same-run typed ref source flag: {flag_name}")


def _normalize_runner_source_packet_producer_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_runner_source_packet_producer_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("runner source packet producer no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "runner source packet producer no_overclaim_flags missing: "
            + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe runner source packet producer flag: {flag_name}")


def _validate_runner_source_boundary_payload_fields(source_boundary: Mapping[str, Any]) -> None:
    forbidden = [
        field
        for field in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS
        if field in source_boundary
    ]
    if forbidden:
        raise ValueError(
            "runner source boundary contains unsupported raw provider material fields: "
            + ", ".join(forbidden)
        )
    unsupported = [
        field
        for field in source_boundary
        if field not in PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_ALLOWED_FIELDS
    ]
    if unsupported:
        raise ValueError(
            "runner source boundary contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )


def _normalize_runner_source_boundary_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def _validate_runner_source_boundary_hard_nonclaims(hard_nonclaims: Any) -> None:
    values = _string_list(hard_nonclaims, field_name="hard_nonclaims")
    if not values:
        raise ValueError("runner source boundary requires hard_nonclaims")
    missing = [
        hard_nonclaim
        for hard_nonclaim in (
            *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS,
            *PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_HARD_NONCLAIMS,
        )
        if hard_nonclaim not in values
    ]
    if missing:
        raise ValueError("runner source boundary missing hard nonclaims")
    _assert_additive_only_hard_nonclaims(values)


def _validate_runner_source_boundary_no_overclaim_flags(flags: Any) -> None:
    if not isinstance(flags, Mapping):
        raise ValueError("runner source boundary no_overclaim_flags must be an object")
    missing = [
        flag
        for flag in PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAGS
        if flag not in flags
    ]
    if missing:
        raise ValueError(
            "runner source boundary no_overclaim_flags missing: " + ", ".join(missing)
        )
    for flag_name, value in flags.items():
        if value is not False:
            raise ValueError(f"unsafe runner source boundary flag: {flag_name}")


def _normalize_runner_response_producer_hard_nonclaims(
    hard_nonclaims: Sequence[str] | None,
) -> list[str]:
    values = [
        *PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_HARD_NONCLAIMS,
        *PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS,
        *_string_list(hard_nonclaims, field_name="hard_nonclaims"),
    ]
    _assert_additive_only_hard_nonclaims(values)
    return values


def produce_provider_subagent_ptc_runner_source_packet(
    *,
    invocation_command: Mapping[str, Any],
    same_run_witness_ref: str,
    provider_or_subagent_invocation_ref: str,
    role_execution_refs: Mapping[str, Any],
    before_context_ref: str,
    after_context_ref: str,
    typed_result_ref: str | None = None,
    typed_unavailable_ref: str | None = None,
    source_packet_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    no_overclaim_flags: Mapping[str, Any] | None = None,
    reason_codes: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Produce an R12-compatible source packet from typed non-fixture refs only.

    This producer does not execute provider/subagent work. It assembles safe refs
    supplied by an upstream runner boundary into the packet shape accepted by the
    same-run typed ref source materializer, then validates that packet.
    """

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    active_same_run_witness_ref = _safe_portable_ref(
        same_run_witness_ref,
        field_name="same_run_witness_ref",
    )
    active_invocation_ref = _safe_portable_ref(
        provider_or_subagent_invocation_ref,
        field_name="provider_or_subagent_invocation_ref",
    )
    active_role_execution_refs = _normalize_strict_role_map(
        role_execution_refs,
        field_name="role_execution_refs",
    )
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
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError(
            "runner source packet producer requires exactly one typed result or unavailable ref"
        )
    active_before_context_ref = _safe_portable_ref(
        before_context_ref,
        field_name="before_context_ref",
    )
    active_after_context_ref = _safe_portable_ref(
        after_context_ref,
        field_name="after_context_ref",
    )
    _reject_fixture_typed_ref_terms(
        active_same_run_witness_ref,
        active_invocation_ref,
        active_role_execution_refs,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
    )
    active_hard_nonclaims = _normalize_runner_source_packet_producer_hard_nonclaims(
        hard_nonclaims
    )
    active_no_overclaim_flags = dict(
        no_overclaim_flags
        or {
            flag: False
            for flag in PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS
        }
    )
    _validate_runner_source_packet_producer_no_overclaim_flags(active_no_overclaim_flags)
    active_reason_codes = [
        "provider_subagent_ptc_runner_source_packet_produced_from_typed_refs_only",
        "producer_does_not_execute_provider_or_subagent",
        "r12_source_packet_validation_required",
        "non_fixture_refs_only",
        "hard_nonclaims_preserved",
        *_string_list(reason_codes, field_name="reason_codes"),
    ]
    token = _route_token(
        command.get("command_id"),
        command.get("typed_task_id"),
        active_same_run_witness_ref,
        active_invocation_ref,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_source_packet_ref = _safe_portable_ref(
        source_packet_ref
        or f"same-run-source-packet-ref://openyggdrasil/ptc-source-producer/{token}",
        field_name="source_packet_ref",
    )
    _reject_fixture_typed_ref_terms(active_source_packet_ref)
    source_packet = {
        "source_packet_ref": active_source_packet_ref,
        "source_kind": PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND,
        "source_evidence_status": (
            PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS
        ),
        "same_run_witness_ref": active_same_run_witness_ref,
        "same_run_invocation_command": command["same_run_invocation_command"],
        "typed_task_id": command["typed_task_id"],
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "fixture_refs_used": False,
        "non_fixture_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": active_no_overclaim_flags,
        "reason_codes": active_reason_codes,
        "generated_at": generated_at or _utc_now_iso(),
    }
    materialize_provider_subagent_ptc_same_run_typed_refs(
        invocation_command=command,
        source_packet=source_packet,
    )
    return source_packet


def materialize_provider_subagent_ptc_runner_source_boundary(
    *,
    invocation_command: Mapping[str, Any],
    source_boundary: Mapping[str, Any],
    boundary_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate a same-run runner/provider source boundary and feed R14.

    This boundary accepts typed non-fixture refs from an upstream runner/provider
    boundary only. It does not execute provider/subagent work and cannot prove
    that a real invocation happened.
    """

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    if not isinstance(source_boundary, Mapping):
        raise ValueError("source_boundary must be an object")
    source = dict(source_boundary)
    _validate_runner_source_boundary_payload_fields(source)
    _validate_provider_material_absence(source)
    if source.get("source_boundary_kind") != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_KIND:
        raise ValueError("runner source boundary kind is invalid")
    if (
        source.get("source_boundary_evidence_status")
        != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_EVIDENCE_STATUS
    ):
        raise ValueError("runner source boundary evidence status is invalid")
    if source.get("fixture_refs_used") is not False:
        raise ValueError("runner source boundary must not use fixture refs")
    if source.get("non_fixture_refs_only") is not True:
        raise ValueError("runner source boundary requires non_fixture_refs_only=True")
    if source.get("same_run_invocation_command") != command.get("same_run_invocation_command"):
        raise ValueError("runner source boundary command must match invocation command")
    active_typed_task_id = _safe_identifier(
        source.get("typed_task_id"),
        field_name="typed_task_id",
    )
    if active_typed_task_id != command.get("typed_task_id"):
        raise ValueError("runner source boundary typed_task_id must match invocation command")

    active_source_boundary_ref = _safe_portable_ref(
        source.get("source_boundary_ref"),
        field_name="source_boundary_ref",
    )
    active_source_packet_ref = _safe_portable_ref(
        source.get("source_packet_ref"),
        field_name="source_packet_ref",
    )
    active_same_run_witness_ref = _safe_portable_ref(
        source.get("same_run_witness_ref"),
        field_name="same_run_witness_ref",
    )
    active_invocation_ref = _safe_portable_ref(
        source.get("provider_or_subagent_invocation_ref"),
        field_name="provider_or_subagent_invocation_ref",
    )
    active_role_execution_refs = _normalize_strict_role_map(
        source.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    active_typed_result_ref = (
        _safe_portable_ref(source.get("typed_result_ref"), field_name="typed_result_ref")
        if source.get("typed_result_ref") is not None
        else None
    )
    active_typed_unavailable_ref = (
        _safe_portable_ref(
            source.get("typed_unavailable_ref"),
            field_name="typed_unavailable_ref",
        )
        if source.get("typed_unavailable_ref") is not None
        else None
    )
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError(
            "runner source boundary requires exactly one typed result or unavailable ref"
        )
    active_before_context_ref = _safe_portable_ref(
        source.get("before_context_ref"),
        field_name="before_context_ref",
    )
    active_after_context_ref = _safe_portable_ref(
        source.get("after_context_ref"),
        field_name="after_context_ref",
    )
    _reject_fixture_typed_ref_terms(
        active_source_boundary_ref,
        active_source_packet_ref,
        active_same_run_witness_ref,
        active_invocation_ref,
        active_role_execution_refs,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
    )
    active_hard_nonclaims = _normalize_runner_source_boundary_hard_nonclaims(
        source.get("hard_nonclaims")
    )
    active_no_overclaim_flags = dict(
        source.get("no_overclaim_flags")
        or {
            flag: False
            for flag in PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAGS
        }
    )
    _validate_runner_source_boundary_no_overclaim_flags(active_no_overclaim_flags)
    source_reason_codes = _string_list(
        source.get("reason_codes"),
        field_name="runner_source_boundary.reason_codes",
    )
    if not source_reason_codes:
        raise ValueError("runner source boundary reason_codes are required")

    r14_producer_input_refs = {
        "source_packet_ref": active_source_packet_ref,
        "same_run_witness_ref": active_same_run_witness_ref,
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
    }
    source_packet = produce_provider_subagent_ptc_runner_source_packet(
        invocation_command=command,
        hard_nonclaims=active_hard_nonclaims,
        no_overclaim_flags=active_no_overclaim_flags,
        reason_codes=[
            "runner_source_boundary_validated",
            "r14_producer_input_refs_ready",
            *source_reason_codes,
        ],
        generated_at=generated_at,
        **r14_producer_input_refs,
    )
    token = _route_token(
        command.get("command_id"),
        active_typed_task_id,
        active_source_boundary_ref,
        active_source_packet_ref,
        active_same_run_witness_ref,
        active_invocation_ref,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_boundary_ref = _safe_portable_ref(
        boundary_ref or f"runner-source-boundary-ref://openyggdrasil/ptc-boundary/{token}",
        field_name="boundary_ref",
    )
    _reject_fixture_typed_ref_terms(active_boundary_ref)
    boundary = {
        "schema_version": PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_SCHEMA_VERSION,
        "boundary_id": f"provider-subagent-ptc-runner-source-boundary-{token}",
        "boundary_ref": active_boundary_ref,
        "source_boundary_ref": active_source_boundary_ref,
        "runner_source_boundary_status": PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_CLAIM_SCOPE,
        "source_boundary_kind": PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_KIND,
        "source_boundary_evidence_status": (
            PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_EVIDENCE_STATUS
        ),
        "same_run_invocation_command": command["same_run_invocation_command"],
        "command_id": command["command_id"],
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": command["typed_task_ref"],
        "invocation_request_ref": command["invocation_request_ref"],
        "execution_trace_ref": command["execution_trace_ref"],
        "ptc_telemetry_ref": command["ptc_telemetry_ref"],
        "source_packet_ref": active_source_packet_ref,
        "same_run_witness_ref": active_same_run_witness_ref,
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "r14_producer_input_refs": r14_producer_input_refs,
        "r14_source_packet": source_packet,
        "r14_producer_used": True,
        "r12_materializer_accepts_packet": True,
        "source_boundary_validated": True,
        "safe_refs_only": True,
        "non_fixture_refs_only": True,
        "fixture_refs_used": False,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": active_no_overclaim_flags,
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_subagent_ptc_runner_source_boundary_validated",
            "source_boundary_safe_refs_validated",
            "r14_producer_input_refs_ready",
            "r14_producer_used_without_provider_execution",
            "hard_nonclaims_preserved",
            *source_reason_codes,
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_runner_source_boundary(boundary)
    return boundary


def validate_provider_subagent_ptc_runner_source_boundary(
    payload: Mapping[str, Any],
) -> None:
    boundary = dict(payload)
    if boundary.get("schema_version") != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent runner source boundary schema_version")
    if (
        boundary.get("runner_source_boundary_status")
        != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_STATUS
    ):
        raise ValueError("invalid provider/subagent runner source boundary status")
    if boundary.get("claim_scope") != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_CLAIM_SCOPE:
        raise ValueError("invalid provider/subagent runner source boundary claim_scope")
    if boundary.get("source_boundary_kind") != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_KIND:
        raise ValueError("invalid provider/subagent runner source boundary kind")
    if (
        boundary.get("source_boundary_evidence_status")
        != PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_EVIDENCE_STATUS
    ):
        raise ValueError("invalid provider/subagent runner source boundary evidence status")
    if boundary.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent runner source boundary command")
    _safe_identifier(boundary.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "boundary_ref",
        "source_boundary_ref",
        "source_packet_ref",
        "same_run_witness_ref",
        "typed_task_ref",
        "invocation_request_ref",
        "execution_trace_ref",
        "ptc_telemetry_ref",
        "provider_or_subagent_invocation_ref",
        "before_context_ref",
        "after_context_ref",
    ):
        _safe_portable_ref(boundary.get(field), field_name=field)
    role_refs = _normalize_strict_role_map(
        boundary.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    if boundary.get("role_execution_refs") != role_refs:
        raise ValueError("role_execution_refs must be normalized required role refs")
    active_typed_result_ref = boundary.get("typed_result_ref")
    active_typed_unavailable_ref = boundary.get("typed_unavailable_ref")
    if active_typed_result_ref is not None:
        _safe_portable_ref(active_typed_result_ref, field_name="typed_result_ref")
    if active_typed_unavailable_ref is not None:
        _safe_portable_ref(active_typed_unavailable_ref, field_name="typed_unavailable_ref")
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError(
            "runner source boundary requires exactly one typed result or unavailable ref"
        )
    r14_inputs = boundary.get("r14_producer_input_refs")
    if not isinstance(r14_inputs, Mapping):
        raise ValueError("r14_producer_input_refs must be an object")
    for field in (
        "source_packet_ref",
        "same_run_witness_ref",
        "provider_or_subagent_invocation_ref",
        "typed_result_ref",
        "typed_unavailable_ref",
        "before_context_ref",
        "after_context_ref",
    ):
        if r14_inputs.get(field) != boundary.get(field):
            raise ValueError(f"r14_producer_input_refs.{field} must match boundary field")
    normalized_r14_role_refs = _normalize_strict_role_map(
        r14_inputs.get("role_execution_refs") or {},
        field_name="r14_producer_input_refs.role_execution_refs",
    )
    if normalized_r14_role_refs != role_refs:
        raise ValueError("r14_producer_input_refs.role_execution_refs must match boundary roles")
    source_packet = boundary.get("r14_source_packet")
    if not isinstance(source_packet, Mapping):
        raise ValueError("r14_source_packet must be an object")
    invocation_hard_nonclaims = _normalize_invocation_hard_nonclaims(None)
    command = {
        "schema_version": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION,
        "command_id": boundary.get("command_id"),
        "same_run_invocation_command": boundary.get("same_run_invocation_command"),
        "command_status": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_CLAIM_SCOPE,
        "typed_task_id": boundary.get("typed_task_id"),
        "typed_task_id_contract": "safe_identifier_required",
        "typed_task_ref": boundary.get("typed_task_ref"),
        "invocation_request_ref": boundary.get("invocation_request_ref"),
        "execution_trace_ref": boundary.get("execution_trace_ref"),
        "ptc_telemetry_ref": boundary.get("ptc_telemetry_ref"),
        "required_request_refs": {
            "typed_task_ref": boundary.get("typed_task_ref"),
            "execution_trace_ref": boundary.get("execution_trace_ref"),
            "ptc_telemetry_ref": boundary.get("ptc_telemetry_ref"),
        },
        "required_response_refs": list(PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS),
        "execution_trace_packet_validated": True,
        "command_surface_only": True,
        "r7_same_run_attempt_enabled": True,
        "safe_refs_only": True,
        "additive_only_hard_nonclaims": True,
        "typed_result_unavailable_contract": "typed result or unavailable ref required",
        "context_ref_contract": "before and after context refs required",
        "role_execution_ref_contract": "role execution refs required",
        "provider_boundary_contract": "provider boundary refs only",
        "llm_facing_contract": _default_provider_subagent_invocation_llm_contract(
            invocation_hard_nonclaims
        ),
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "hard_nonclaims": invocation_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False for flag in PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS
        },
        "reason_codes": ["provider_subagent_ptc_invocation_command_reconstructed_for_boundary_validation"],
        "generated_at": boundary.get("generated_at"),
    }
    validate_provider_subagent_ptc_invocation_command(command)
    materialize_provider_subagent_ptc_same_run_typed_refs(
        invocation_command=command,
        source_packet=source_packet,
    )
    if source_packet.get("source_packet_ref") != boundary.get("source_packet_ref"):
        raise ValueError("r14_source_packet.source_packet_ref must match boundary field")
    for field in (
        "r14_producer_used",
        "r12_materializer_accepts_packet",
        "source_boundary_validated",
        "safe_refs_only",
        "non_fixture_refs_only",
        "additive_only_hard_nonclaims",
    ):
        if boundary.get(field) is not True:
            raise ValueError(f"runner source boundary requires {field}=True")
    if boundary.get("fixture_refs_used") is not False:
        raise ValueError("runner source boundary must not use fixture refs")
    _validate_provider_material_absence(boundary)
    _validate_runner_source_boundary_hard_nonclaims(boundary.get("hard_nonclaims"))
    _validate_runner_source_boundary_no_overclaim_flags(boundary.get("no_overclaim_flags"))
    _reject_fixture_typed_ref_terms(
        boundary.get("boundary_ref"),
        boundary.get("source_boundary_ref"),
        boundary.get("source_packet_ref"),
        boundary.get("same_run_witness_ref"),
        boundary.get("provider_or_subagent_invocation_ref"),
        role_refs,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        boundary.get("before_context_ref"),
        boundary.get("after_context_ref"),
    )
    reason_codes = boundary.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("runner source boundary reason_codes are required")


def materialize_provider_subagent_ptc_same_run_typed_refs(
    *,
    invocation_command: Mapping[str, Any],
    source_packet: Mapping[str, Any],
    source_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate a same-run source packet and expose R10 producer input refs.

    This boundary only accepts already-safe, non-fixture source packet refs. It
    does not execute provider/subagent work and cannot prove that a real live
    invocation happened.
    """

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    if not isinstance(source_packet, Mapping):
        raise ValueError("source_packet must be an object")
    packet = dict(source_packet)
    _validate_same_run_typed_ref_source_payload_fields(packet)
    _validate_provider_material_absence(packet)
    if packet.get("source_kind") != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND:
        raise ValueError("same-run typed ref source_kind is invalid")
    if (
        packet.get("source_evidence_status")
        != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS
    ):
        raise ValueError("same-run typed ref source_evidence_status is invalid")
    if packet.get("fixture_refs_used") is not False:
        raise ValueError("same-run typed ref source must not use fixture refs")
    if packet.get("non_fixture_refs_only") is not True:
        raise ValueError("same-run typed ref source requires non_fixture_refs_only=True")
    if packet.get("same_run_invocation_command") != command.get("same_run_invocation_command"):
        raise ValueError("same-run typed ref source command must match invocation command")
    active_typed_task_id = _safe_identifier(
        packet.get("typed_task_id"),
        field_name="typed_task_id",
    )
    if active_typed_task_id != command.get("typed_task_id"):
        raise ValueError("same-run typed ref source typed_task_id must match invocation command")

    active_source_packet_ref = _safe_portable_ref(
        packet.get("source_packet_ref"),
        field_name="source_packet_ref",
    )
    active_same_run_witness_ref = _safe_portable_ref(
        packet.get("same_run_witness_ref"),
        field_name="same_run_witness_ref",
    )
    active_invocation_ref = _safe_portable_ref(
        packet.get("provider_or_subagent_invocation_ref"),
        field_name="provider_or_subagent_invocation_ref",
    )
    active_role_execution_refs = _normalize_strict_role_map(
        packet.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    active_typed_result_ref = (
        _safe_portable_ref(packet.get("typed_result_ref"), field_name="typed_result_ref")
        if packet.get("typed_result_ref") is not None
        else None
    )
    active_typed_unavailable_ref = (
        _safe_portable_ref(
            packet.get("typed_unavailable_ref"),
            field_name="typed_unavailable_ref",
        )
        if packet.get("typed_unavailable_ref") is not None
        else None
    )
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError(
            "same-run typed ref source requires exactly one typed result or unavailable ref"
        )
    active_before_context_ref = _safe_portable_ref(
        packet.get("before_context_ref"),
        field_name="before_context_ref",
    )
    active_after_context_ref = _safe_portable_ref(
        packet.get("after_context_ref"),
        field_name="after_context_ref",
    )
    _reject_fixture_typed_ref_terms(
        active_source_packet_ref,
        active_same_run_witness_ref,
        active_invocation_ref,
        active_role_execution_refs,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
    )
    active_hard_nonclaims = _normalize_same_run_typed_ref_source_hard_nonclaims(
        packet.get("hard_nonclaims")
    )
    active_no_overclaim_flags = dict(
        packet.get("no_overclaim_flags")
        or {
            flag: False
            for flag in PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS
        }
    )
    _validate_same_run_typed_ref_source_no_overclaim_flags(active_no_overclaim_flags)
    source_reason_codes = _string_list(
        packet.get("reason_codes"),
        field_name="same_run_typed_ref_source.reason_codes",
    )
    if not source_reason_codes:
        raise ValueError("same-run typed ref source reason_codes are required")

    token = _route_token(
        command.get("command_id"),
        active_typed_task_id,
        active_source_packet_ref,
        active_invocation_ref,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_source_ref = _safe_portable_ref(
        source_ref or f"same-run-typed-ref-source-ref://openyggdrasil/ptc/{token}",
        field_name="source_ref",
    )
    r10_producer_input_refs = {
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
    }
    source = {
        "schema_version": PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_SCHEMA_VERSION,
        "source_id": f"provider-subagent-ptc-same-run-typed-ref-source-{token}",
        "source_ref": active_source_ref,
        "typed_ref_source_status": PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_CLAIM_SCOPE,
        "source_kind": PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND,
        "source_evidence_status": (
            PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS
        ),
        "source_packet_ref": active_source_packet_ref,
        "same_run_witness_ref": active_same_run_witness_ref,
        "same_run_invocation_command": command["same_run_invocation_command"],
        "command_id": command["command_id"],
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": command["typed_task_ref"],
        "invocation_request_ref": command["invocation_request_ref"],
        "execution_trace_ref": command["execution_trace_ref"],
        "ptc_telemetry_ref": command["ptc_telemetry_ref"],
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "r10_producer_input_refs": r10_producer_input_refs,
        "required_response_refs": list(PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS),
        "typed_result_unavailable_contract": command["typed_result_unavailable_contract"],
        "context_ref_contract": command["context_ref_contract"],
        "role_execution_ref_contract": command["role_execution_ref_contract"],
        "provider_boundary_contract": command["provider_boundary_contract"],
        "command_validated": True,
        "source_packet_validated": True,
        "r10_producer_input_refs_ready": True,
        "safe_refs_only": True,
        "non_fixture_refs_only": True,
        "fixture_refs_used": False,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": active_no_overclaim_flags,
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_subagent_ptc_same_run_typed_ref_source_validated",
            "source_packet_safe_refs_validated",
            "non_fixture_refs_only",
            "r10_producer_input_refs_ready",
            "provider_subagent_invocation_not_claimed",
            "hard_nonclaims_preserved",
            *source_reason_codes,
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_same_run_typed_ref_source(source)
    return source


def validate_provider_subagent_ptc_same_run_typed_ref_source(
    payload: Mapping[str, Any],
) -> None:
    source = dict(payload)
    if source.get("schema_version") != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent same-run typed ref source schema_version")
    if source.get("typed_ref_source_status") != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_STATUS:
        raise ValueError("invalid provider/subagent same-run typed ref source status")
    if source.get("claim_scope") != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_CLAIM_SCOPE:
        raise ValueError("invalid provider/subagent same-run typed ref source claim_scope")
    if source.get("source_kind") != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_KIND:
        raise ValueError("invalid provider/subagent same-run typed ref source_kind")
    if (
        source.get("source_evidence_status")
        != PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_EVIDENCE_STATUS
    ):
        raise ValueError("invalid provider/subagent same-run typed ref source_evidence_status")
    if source.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent same-run typed ref source command")
    _safe_identifier(source.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "source_ref",
        "source_packet_ref",
        "same_run_witness_ref",
        "typed_task_ref",
        "invocation_request_ref",
        "execution_trace_ref",
        "ptc_telemetry_ref",
        "provider_or_subagent_invocation_ref",
        "before_context_ref",
        "after_context_ref",
    ):
        _safe_portable_ref(source.get(field), field_name=field)
    role_refs = _normalize_strict_role_map(
        source.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    if source.get("role_execution_refs") != role_refs:
        raise ValueError("role_execution_refs must be normalized required role refs")
    active_typed_result_ref = source.get("typed_result_ref")
    active_typed_unavailable_ref = source.get("typed_unavailable_ref")
    if active_typed_result_ref is not None:
        _safe_portable_ref(active_typed_result_ref, field_name="typed_result_ref")
    if active_typed_unavailable_ref is not None:
        _safe_portable_ref(active_typed_unavailable_ref, field_name="typed_unavailable_ref")
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError(
            "same-run typed ref source requires exactly one typed result or unavailable ref"
        )
    r10_inputs = source.get("r10_producer_input_refs")
    if not isinstance(r10_inputs, Mapping):
        raise ValueError("r10_producer_input_refs must be an object")
    for field in (
        "provider_or_subagent_invocation_ref",
        "typed_result_ref",
        "typed_unavailable_ref",
        "before_context_ref",
        "after_context_ref",
    ):
        if r10_inputs.get(field) != source.get(field):
            raise ValueError(f"r10_producer_input_refs.{field} must match source field")
    normalized_r10_role_refs = _normalize_strict_role_map(
        r10_inputs.get("role_execution_refs") or {},
        field_name="r10_producer_input_refs.role_execution_refs",
    )
    if normalized_r10_role_refs != role_refs:
        raise ValueError("r10_producer_input_refs.role_execution_refs must match source roles")
    if source.get("required_response_refs") != list(
        PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
    ):
        raise ValueError("required_response_refs must match provider/subagent invocation contract")
    for field in (
        "typed_result_unavailable_contract",
        "context_ref_contract",
        "role_execution_ref_contract",
        "provider_boundary_contract",
    ):
        if not str(source.get(field) or "").strip():
            raise ValueError(f"{field} is required")
    for field in (
        "command_validated",
        "source_packet_validated",
        "r10_producer_input_refs_ready",
        "safe_refs_only",
        "non_fixture_refs_only",
        "additive_only_hard_nonclaims",
    ):
        if source.get(field) is not True:
            raise ValueError(f"same-run typed ref source requires {field}=True")
    if source.get("fixture_refs_used") is not False:
        raise ValueError("same-run typed ref source must not use fixture refs")
    _validate_provider_material_absence(source)
    _validate_same_run_typed_ref_source_hard_nonclaims(source.get("hard_nonclaims"))
    _validate_same_run_typed_ref_source_no_overclaim_flags(source.get("no_overclaim_flags"))
    _reject_fixture_typed_ref_terms(
        source.get("source_ref"),
        source.get("source_packet_ref"),
        source.get("same_run_witness_ref"),
        source.get("provider_or_subagent_invocation_ref"),
        role_refs,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        source.get("before_context_ref"),
        source.get("after_context_ref"),
    )
    reason_codes = source.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("same-run typed ref source reason_codes are required")


def produce_provider_subagent_ptc_runner_response(
    *,
    invocation_command: Mapping[str, Any],
    provider_or_subagent_invocation_ref: str,
    role_execution_refs: Mapping[str, Any],
    before_context_ref: str,
    after_context_ref: str,
    typed_result_ref: str | None = None,
    typed_unavailable_ref: str | None = None,
    runner_response_ref: str | None = None,
    hard_nonclaims: Sequence[str] | None = None,
    no_overclaim_flags: Mapping[str, Any] | None = None,
    reason_codes: Sequence[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Produce an R8-ingestible runner response from already-typed safe refs only.

    This producer is not a provider/subagent runner. It assembles caller-supplied
    typed refs into the exact response shape accepted by R8 ingress and then
    validates that response through the ingress contract.
    """

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    active_invocation_ref = _safe_portable_ref(
        provider_or_subagent_invocation_ref,
        field_name="provider_or_subagent_invocation_ref",
    )
    active_role_execution_refs = _normalize_strict_role_map(
        role_execution_refs,
        field_name="role_execution_refs",
    )
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
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError("runner response producer requires exactly one typed result or unavailable ref")
    active_before_context_ref = _safe_portable_ref(
        before_context_ref,
        field_name="before_context_ref",
    )
    active_after_context_ref = _safe_portable_ref(
        after_context_ref,
        field_name="after_context_ref",
    )
    active_hard_nonclaims = _normalize_runner_response_producer_hard_nonclaims(
        hard_nonclaims
    )
    active_no_overclaim_flags = dict(
        no_overclaim_flags
        or {flag: False for flag in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS}
    )
    _validate_runner_response_no_overclaim_flags(active_no_overclaim_flags)
    active_reason_codes = [
        "provider_subagent_ptc_runner_response_produced_from_typed_refs_only",
        "producer_does_not_execute_provider_or_subagent",
        "safe_refs_only",
        "hard_nonclaims_preserved",
        "r8_ingress_validation_required",
        *_string_list(reason_codes, field_name="reason_codes"),
    ]
    token = _route_token(
        command.get("command_id"),
        command.get("typed_task_id"),
        active_invocation_ref,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_runner_response_ref = _safe_portable_ref(
        runner_response_ref
        or f"provider-subagent-runner-response-ref://openyggdrasil/ptc-producer/{token}",
        field_name="runner_response_ref",
    )
    response = {
        "same_run_invocation_command": command["same_run_invocation_command"],
        "typed_task_id": command["typed_task_id"],
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": active_no_overclaim_flags,
        "runner_response_ref": active_runner_response_ref,
        "reason_codes": active_reason_codes,
        "generated_at": generated_at or _utc_now_iso(),
    }
    ingest_provider_subagent_ptc_runner_response(
        invocation_command=command,
        runner_response=response,
    )
    return response


def ingest_provider_subagent_ptc_runner_response(
    *,
    invocation_command: Mapping[str, Any],
    runner_response: Mapping[str, Any],
    runner_response_ref: str | None = None,
    ingress_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate and ingest safe refs from a provider/subagent runner response.

    This ingress does not execute a provider/subagent and does not prove live
    invocation. It only accepts the typed refs needed for a later verifier.
    """

    validate_provider_subagent_ptc_invocation_command(invocation_command)
    command = dict(invocation_command)
    if not isinstance(runner_response, Mapping):
        raise ValueError("runner_response must be an object")
    response = dict(runner_response)
    _validate_runner_response_payload_fields(response)
    if response.get("same_run_invocation_command") != command.get("same_run_invocation_command"):
        raise ValueError("runner response command must match invocation command")
    if response.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent runner response command")
    active_typed_task_id = _safe_identifier(
        response.get("typed_task_id"),
        field_name="typed_task_id",
    )
    if active_typed_task_id != command.get("typed_task_id"):
        raise ValueError("runner response typed_task_id must match invocation command")
    active_invocation_ref = _safe_portable_ref(
        response.get("provider_or_subagent_invocation_ref"),
        field_name="provider_or_subagent_invocation_ref",
    )
    active_role_execution_refs = _normalize_strict_role_map(
        response.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    active_typed_result_ref = (
        _safe_portable_ref(response.get("typed_result_ref"), field_name="typed_result_ref")
        if response.get("typed_result_ref") is not None
        else None
    )
    active_typed_unavailable_ref = (
        _safe_portable_ref(
            response.get("typed_unavailable_ref"),
            field_name="typed_unavailable_ref",
        )
        if response.get("typed_unavailable_ref") is not None
        else None
    )
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError("runner response requires exactly one typed result or typed unavailable ref")
    active_before_context_ref = _safe_portable_ref(
        response.get("before_context_ref"),
        field_name="before_context_ref",
    )
    active_after_context_ref = _safe_portable_ref(
        response.get("after_context_ref"),
        field_name="after_context_ref",
    )
    active_hard_nonclaims = _normalize_runner_response_hard_nonclaims(
        response.get("hard_nonclaims")
    )
    _validate_runner_response_no_overclaim_flags(response.get("no_overclaim_flags"))
    response_reason_codes = _string_list(
        response.get("reason_codes"),
        field_name="runner_response.reason_codes",
    )
    token = _route_token(
        command.get("command_id"),
        active_typed_task_id,
        active_invocation_ref,
        active_typed_result_ref,
        active_typed_unavailable_ref,
        active_before_context_ref,
        active_after_context_ref,
        tuple(active_role_execution_refs.items()),
    )
    active_runner_response_ref = _safe_portable_ref(
        runner_response_ref
        or response.get("runner_response_ref")
        or f"provider-subagent-runner-response-ref://openyggdrasil/ptc/{token}",
        field_name="runner_response_ref",
    )
    active_ingress_ref = _safe_portable_ref(
        ingress_ref or f"runner-response-ingress-ref://openyggdrasil/ptc/{token}",
        field_name="ingress_ref",
    )
    ingress = {
        "schema_version": PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_SCHEMA_VERSION,
        "ingress_id": f"provider-subagent-ptc-runner-response-ingress-{token}",
        "ingress_ref": active_ingress_ref,
        "ingress_status": PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_CLAIM_SCOPE,
        "same_run_invocation_command": command["same_run_invocation_command"],
        "command_id": command["command_id"],
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": command["typed_task_ref"],
        "invocation_request_ref": command["invocation_request_ref"],
        "execution_trace_ref": command["execution_trace_ref"],
        "ptc_telemetry_ref": command["ptc_telemetry_ref"],
        "runner_response_ref": active_runner_response_ref,
        "provider_or_subagent_invocation_ref": active_invocation_ref,
        "role_execution_refs": active_role_execution_refs,
        "typed_result_ref": active_typed_result_ref,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "before_context_ref": active_before_context_ref,
        "after_context_ref": active_after_context_ref,
        "required_response_refs": list(PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS),
        "typed_result_unavailable_contract": command["typed_result_unavailable_contract"],
        "context_ref_contract": command["context_ref_contract"],
        "role_execution_ref_contract": command["role_execution_ref_contract"],
        "provider_boundary_contract": command["provider_boundary_contract"],
        "command_validated": True,
        "runner_response_validated": True,
        "runner_response_ingress_only": True,
        "role_execution_refs_validated": True,
        "typed_result_contract_validated": True,
        "context_refs_validated": True,
        "safe_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_provider_material_included": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_material_included": False,
        "provider_profile_material_included": False,
        "provider_state_db_material_included": False,
        "mcp_generic_gateway_or_agent_adapter_used": False,
        "real_provider_subagent_invocation_claimed": False,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": active_hard_nonclaims,
        "no_overclaim_flags": {
            flag: False for flag in PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS
        },
        "runtime_owner": "runtime/ptc/engine.py",
        "reason_codes": [
            "provider_subagent_ptc_runner_response_ingress_validated",
            "invocation_command_validated",
            "runner_response_safe_refs_validated",
            "typed_result_or_unavailable_validated",
            "before_after_context_refs_validated",
            "role_execution_refs_validated",
            "hard_nonclaims_preserved",
            *response_reason_codes,
        ],
        "generated_at": generated_at or _utc_now_iso(),
    }
    validate_provider_subagent_ptc_runner_response_ingress(ingress)
    return ingress


def validate_provider_subagent_ptc_runner_response_ingress(
    payload: Mapping[str, Any],
) -> None:
    ingress = dict(payload)
    if ingress.get("schema_version") != PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_SCHEMA_VERSION:
        raise ValueError("invalid provider/subagent runner response ingress schema_version")
    if ingress.get("ingress_status") != PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_STATUS:
        raise ValueError("invalid provider/subagent runner response ingress status")
    if ingress.get("claim_scope") != PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_CLAIM_SCOPE:
        raise ValueError("invalid provider/subagent runner response ingress claim_scope")
    if ingress.get("same_run_invocation_command") != PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME:
        raise ValueError("invalid provider/subagent runner response ingress command")
    _safe_identifier(ingress.get("typed_task_id"), field_name="typed_task_id")
    for field in (
        "ingress_ref",
        "typed_task_ref",
        "invocation_request_ref",
        "execution_trace_ref",
        "ptc_telemetry_ref",
        "runner_response_ref",
        "provider_or_subagent_invocation_ref",
        "before_context_ref",
        "after_context_ref",
    ):
        _safe_portable_ref(ingress.get(field), field_name=field)
    role_refs = _normalize_strict_role_map(
        ingress.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    if ingress.get("role_execution_refs") != role_refs:
        raise ValueError("role_execution_refs must be normalized required role refs")
    active_typed_result_ref = ingress.get("typed_result_ref")
    active_typed_unavailable_ref = ingress.get("typed_unavailable_ref")
    if active_typed_result_ref is not None:
        _safe_portable_ref(active_typed_result_ref, field_name="typed_result_ref")
    if active_typed_unavailable_ref is not None:
        _safe_portable_ref(active_typed_unavailable_ref, field_name="typed_unavailable_ref")
    if (active_typed_result_ref is None) == (active_typed_unavailable_ref is None):
        raise ValueError("runner response ingress requires exactly one typed result or unavailable ref")
    if ingress.get("required_response_refs") != list(
        PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS
    ):
        raise ValueError("required_response_refs must match provider/subagent invocation contract")
    for field in (
        "typed_result_unavailable_contract",
        "context_ref_contract",
        "role_execution_ref_contract",
        "provider_boundary_contract",
    ):
        if not str(ingress.get(field) or "").strip():
            raise ValueError(f"{field} is required")
    for field in (
        "command_validated",
        "runner_response_validated",
        "runner_response_ingress_only",
        "role_execution_refs_validated",
        "typed_result_contract_validated",
        "context_refs_validated",
        "safe_refs_only",
        "additive_only_hard_nonclaims",
    ):
        if ingress.get(field) is not True:
            raise ValueError(f"provider/subagent runner response ingress requires {field}=True")
    _validate_provider_material_absence(ingress)
    _validate_runner_response_hard_nonclaims(ingress.get("hard_nonclaims"))
    _validate_runner_response_no_overclaim_flags(ingress.get("no_overclaim_flags"))
    reason_codes = ingress.get("reason_codes")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)) or not reason_codes:
        raise ValueError("reason_codes are required")


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
    "PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_STATUS",
    "PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME",
    "PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS",
    "PROVIDER_SUBAGENT_PTC_INVOCATION_UNAVAILABLE_RESULT_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_INGRESS_STATUS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_NO_OVERCLAIM_FLAGS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_PRODUCER_HARD_NONCLAIMS",
    "PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_STATUS",
    "PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAGS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAGS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_SCHEMA_VERSION",
    "PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_STATUS",
    "PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAGS",
    "REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES",
    "ROLE_POLYMORPHIC_PTC_TELEMETRY_SCHEMA_VERSION",
    "ROLE_POLYMORPHIC_PTC_TELEMETRY_STATUS",
    "STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE",
    "build_lease_backed_query_adaptive_pathfinder_plan",
    "build_pathfinder_ptc_routing_trace",
    "build_provider_subagent_ptc_execution_trace_packet",
    "build_provider_subagent_ptc_invocation_command",
    "build_provider_subagent_ptc_invocation_unavailable_result",
    "build_provider_subagent_ptc_provider_session_invocation_boundary",
    "build_provider_subagent_ptc_provider_session_ref",
    "build_provider_subagent_ptc_provider_session_runner_typed_unavailable_result",
    "build_query_adaptive_pathfinder_plan",
    "build_role_polymorphic_ptc_telemetry_trace",
    "ingest_provider_subagent_ptc_runner_response",
    "materialize_provider_subagent_ptc_provider_session_executor_boundary",
    "materialize_provider_subagent_ptc_runner_source_boundary",
    "materialize_provider_subagent_ptc_same_run_typed_refs",
    "produce_provider_subagent_ptc_runner_response",
    "produce_provider_subagent_ptc_runner_source_packet",
    "render_default_pathfinder_program",
    "render_default_pathfinder_json_plan",
    "render_query_adaptive_pathfinder_program",
    "structural_anchor_fallback_evaluator",
    "validate_pathfinder_json_tool_plan",
    "validate_provider_subagent_ptc_execution_trace_packet",
    "validate_provider_subagent_ptc_invocation_command",
    "validate_provider_subagent_ptc_invocation_unavailable_result",
    "validate_provider_subagent_ptc_provider_session_executor_boundary",
    "validate_provider_subagent_ptc_provider_session_invocation_boundary",
    "validate_provider_subagent_ptc_provider_session_ref",
    "validate_provider_subagent_ptc_provider_session_runner_result",
    "validate_provider_subagent_ptc_runner_response_ingress",
    "validate_provider_subagent_ptc_runner_source_boundary",
    "validate_provider_subagent_ptc_same_run_typed_ref_source",
    "validate_query_adaptive_pathfinder_plan",
    "validate_role_polymorphic_ptc_telemetry_trace",
]
