from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.base_utils import _route_token, _safe_identifier, _string_list, _utc_now_iso
from runtime.ptc.engine_contracts import (
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_NAME,
    PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_INVOCATION_COMMAND_STATUS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_UNAVAILABLE_RESULT_SCHEMA_VERSION,
    _assert_additive_only_hard_nonclaims,
    _safe_portable_ref,
)
from runtime.ptc.execution_trace_packet import validate_provider_subagent_ptc_execution_trace_packet

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


__all__ = [
    "_normalize_invocation_hard_nonclaims",
    "_validate_invocation_hard_nonclaims",
    "_validate_invocation_no_overclaim_flags",
    "_default_provider_subagent_invocation_llm_contract",
    "_validate_invocation_llm_contract",
    "_validate_provider_material_absence",
    "build_provider_subagent_ptc_invocation_command",
    "validate_provider_subagent_ptc_invocation_command",
    "build_provider_subagent_ptc_invocation_unavailable_result",
    "validate_provider_subagent_ptc_invocation_unavailable_result",
]
