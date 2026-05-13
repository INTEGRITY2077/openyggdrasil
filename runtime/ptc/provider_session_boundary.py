from __future__ import annotations


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
PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAG_SUFFIXES = (
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
PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES = (
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
PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAG_SUFFIXES = (
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
PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES = (
    "provider_session_executor_boundary_relabelled_as_live",
    "provider_session_executor_completed_invocation_claimed",
    "provider_session_executor_refs_claimed_without_live_verification",
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


__all__ = [
    name
    for name in globals()
    if name.startswith("PROVIDER_SESSION_")
    or name.startswith("PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_")
]
