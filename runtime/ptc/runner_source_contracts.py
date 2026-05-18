from __future__ import annotations


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
RUNNER_RESPONSE_NO_OVERCLAIM_FLAG_SUFFIXES = (
    "runner_response_ingress_relabelled_as_invocation",
    "runner_response_ingress_claimed_live_proof",
    "raw_runner_payload_material_included",
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
SAME_RUN_TYPED_REF_SOURCE_NO_OVERCLAIM_FLAG_SUFFIXES = (
    "same_run_typed_ref_source_relabelled_as_invocation",
    "same_run_typed_ref_source_claimed_live_proof",
    "fixture_refs_used",
)

PROVIDER_SUBAGENT_PTC_RUNNER_SOURCE_PACKET_PRODUCER_HARD_NONCLAIMS = (
    "This runner source packet producer only assembles typed non-fixture refs.",
    "This runner source packet producer does not execute provider or subagent work.",
    "This runner source packet producer is not proof of real provider/subagent invocation.",
)
RUNNER_SOURCE_PACKET_PRODUCER_NO_OVERCLAIM_FLAG_SUFFIXES = (
    "runner_source_packet_producer_relabelled_as_invocation",
    "runner_source_packet_producer_claimed_live_proof",
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
RUNNER_SOURCE_BOUNDARY_NO_OVERCLAIM_FLAG_SUFFIXES = (
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
PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS = (
    "fixture",
    "mock://",
    "runner-response-producer",
)


__all__ = [
    name
    for name in globals()
    if name.startswith("PROVIDER_SUBAGENT_PTC_RUNNER")
    or name.startswith("PROVIDER_SUBAGENT_PTC_SAME_RUN")
    or name.endswith("_NO_OVERCLAIM_FLAG_SUFFIXES")
]
