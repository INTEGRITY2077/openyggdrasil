"""PTC execution substrate package.

This package starts as a no-behavior-change skeleton. Existing Pathfinder and
programmatic tool runtime entry points stay on their current import paths until
an extraction slice is covered by compatibility tests.
"""

from __future__ import annotations

from .compat import (
    CLAIM_SCOPE,
    EXTRACTED_SURFACES,
    LEGACY_IMPORT_SURFACES,
    PACKAGE_STATUS,
    compatibility_policy,
)
from .engine import (
    build_lease_backed_query_adaptive_pathfinder_plan,
    build_pathfinder_ptc_routing_trace,
    build_provider_subagent_ptc_execution_trace_packet,
    build_provider_subagent_ptc_invocation_command,
    build_provider_subagent_ptc_invocation_unavailable_result,
    build_query_adaptive_pathfinder_plan,
    ingest_provider_subagent_ptc_runner_response,
    render_default_pathfinder_json_plan,
    render_default_pathfinder_program,
    render_query_adaptive_pathfinder_program,
    validate_pathfinder_json_tool_plan,
    validate_provider_subagent_ptc_execution_trace_packet,
    validate_provider_subagent_ptc_invocation_command,
    validate_provider_subagent_ptc_invocation_unavailable_result,
    validate_provider_subagent_ptc_runner_response_ingress,
    validate_query_adaptive_pathfinder_plan,
)

__all__ = [
    "CLAIM_SCOPE",
    "EXTRACTED_SURFACES",
    "LEGACY_IMPORT_SURFACES",
    "PACKAGE_STATUS",
    "compatibility_policy",
    "build_lease_backed_query_adaptive_pathfinder_plan",
    "build_pathfinder_ptc_routing_trace",
    "build_provider_subagent_ptc_execution_trace_packet",
    "build_provider_subagent_ptc_invocation_command",
    "build_provider_subagent_ptc_invocation_unavailable_result",
    "build_query_adaptive_pathfinder_plan",
    "ingest_provider_subagent_ptc_runner_response",
    "render_default_pathfinder_json_plan",
    "render_default_pathfinder_program",
    "render_query_adaptive_pathfinder_program",
    "validate_pathfinder_json_tool_plan",
    "validate_provider_subagent_ptc_execution_trace_packet",
    "validate_provider_subagent_ptc_invocation_command",
    "validate_provider_subagent_ptc_invocation_unavailable_result",
    "validate_provider_subagent_ptc_runner_response_ingress",
    "validate_query_adaptive_pathfinder_plan",
]
