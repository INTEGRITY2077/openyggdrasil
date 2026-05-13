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
from runtime.ptc.telemetry_trace import *  # noqa: F401,F403
from runtime.ptc.execution_trace_packet import *  # noqa: F401,F403
from runtime.ptc.provider_invocation_command import *  # noqa: F401,F403
from runtime.ptc.provider_session_runtime import *  # noqa: F401,F403

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


__all__ = [
    "_validate_runner_response_payload_fields",
    "_normalize_runner_response_hard_nonclaims",
    "_validate_runner_response_hard_nonclaims",
    "_validate_runner_response_no_overclaim_flags",
    "_validate_same_run_typed_ref_source_payload_fields",
    "_reject_fixture_typed_ref_terms",
    "_normalize_same_run_typed_ref_source_hard_nonclaims",
    "_validate_same_run_typed_ref_source_hard_nonclaims",
    "_validate_same_run_typed_ref_source_no_overclaim_flags",
    "_normalize_runner_source_packet_producer_hard_nonclaims",
    "_validate_runner_source_packet_producer_no_overclaim_flags",
    "_validate_runner_source_boundary_payload_fields",
    "_normalize_runner_source_boundary_hard_nonclaims",
    "_validate_runner_source_boundary_hard_nonclaims",
    "_validate_runner_source_boundary_no_overclaim_flags",
    "_normalize_runner_response_producer_hard_nonclaims",
    "produce_provider_subagent_ptc_runner_source_packet",
    "materialize_provider_subagent_ptc_runner_source_boundary",
    "validate_provider_subagent_ptc_runner_source_boundary",
    "materialize_provider_subagent_ptc_same_run_typed_refs",
    "validate_provider_subagent_ptc_same_run_typed_ref_source",
    "produce_provider_subagent_ptc_runner_response",
    "ingest_provider_subagent_ptc_runner_response",
    "validate_provider_subagent_ptc_runner_response_ingress",
]
