from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.base_utils import (
    _normalize_strict_role_map,
    _reject_fixture_typed_ref_terms,
    _require_safe_ref_prefix,
    _route_token,
    _safe_identifier,
    _string_list,
    _utc_now_iso,
)
from runtime.ptc.engine_contracts import (
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_LLM_CONTRACT_SECTIONS,
    PROVIDER_SUBAGENT_PTC_INVOCATION_REQUIRED_RESPONSE_REFS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SOURCE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_ALLOWED_FIELDS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS,
    PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_UNAVAILABLE_REASON,
    PROVIDER_SUBAGENT_PTC_RUNNER_RESPONSE_FORBIDDEN_FIELDS,
    REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES,
    ROW_8_EXECUTOR_PENDING_STATUS,
    ROW_8_LIVE_VERIFICATION_LABEL,
    _assert_additive_only_hard_nonclaims,
    _safe_portable_ref,
)
from runtime.ptc.provider_invocation_command import _validate_provider_material_absence

def _provider_absence_flags() -> dict[str, bool]:
    return {
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
    }

def _require_expected_values(
    payload: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"invalid {label} {field}")

def _require_boolean_values(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    expected: bool,
    label: str,
) -> None:
    for field in fields:
        if payload.get(field) is not expected:
            raise ValueError(f"{label} requires {field}={expected}")

def _validate_portable_ref_fields(payload: Mapping[str, Any], fields: Sequence[str]) -> None:
    for field in fields:
        _safe_portable_ref(payload.get(field), field_name=field)

def _validate_identifier_fields(payload: Mapping[str, Any], fields: Sequence[str]) -> None:
    for field in fields:
        _safe_identifier(payload.get(field), field_name=field)

def _validate_required_reason_codes(
    payload: Mapping[str, Any],
    *,
    label: str,
) -> None:
    reason_codes = payload.get("reason_codes")
    if (
        not isinstance(reason_codes, Sequence)
        or isinstance(reason_codes, (str, bytes))
        or not reason_codes
    ):
        raise ValueError(f"{label} reason_codes are required")

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
            ROW_8_LIVE_VERIFICATION_LABEL,
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

def _provider_session_invocation_boundary_refs(
    *,
    provider_session_ref_packet: Mapping[str, Any],
    typed_task_ref: str,
    invocation_request_ref: str | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    validate_provider_subagent_ptc_provider_session_ref(provider_session_ref_packet)
    packet = dict(provider_session_ref_packet)
    refs = {
        "provider_session_ref": _safe_portable_ref(
            packet.get("provider_session_ref"),
            field_name="provider_session_ref",
        ),
        "typed_task_ref": _safe_portable_ref(
            typed_task_ref,
            field_name="typed_task_ref",
        ),
        "provider_session_id": _safe_identifier(
            packet.get("provider_session_id"),
            field_name="provider_session_id",
        ),
        "typed_task_id": _safe_identifier(
            packet.get("typed_task_id"),
            field_name="typed_task_id",
        ),
        "provider_session_ref_id": _safe_identifier(
            packet.get("provider_session_ref_id"),
            field_name="provider_session_ref_id",
        ),
    }
    token = _route_token(
        refs["provider_session_ref"],
        refs["typed_task_ref"],
        refs["provider_session_ref_id"],
    )
    refs["token"] = token
    refs["invocation_request_ref"] = _safe_portable_ref(
        invocation_request_ref
        or f"provider-session-invocation-request-ref://openyggdrasil/ptc/{token}",
        field_name="invocation_request_ref",
    )
    return packet, refs

def _provider_session_invocation_boundary_status_fields() -> dict[str, str]:
    return {
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

    packet, refs = _provider_session_invocation_boundary_refs(
        provider_session_ref_packet=provider_session_ref_packet,
        typed_task_ref=typed_task_ref,
        invocation_request_ref=invocation_request_ref,
    )
    active_hard_nonclaims = (
        _normalize_provider_session_invocation_boundary_hard_nonclaims(hard_nonclaims)
    )
    boundary = {
        "schema_version": (
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
        ),
        "boundary_id": f"provider-session-invocation-boundary-{refs['token']}",
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
        "provider_session_ref": refs["provider_session_ref"],
        "provider_session_ref_schema_version": packet.get(
            "provider_session_ref_schema_version"
        ),
        "provider_session_ref_status": packet.get("provider_session_ref_status"),
        "provider_session_ref_claim_scope": packet.get(
            "provider_session_ref_claim_scope"
        ),
        "provider_session_ref_validated": True,
        "provider_session_ref_id": refs["provider_session_ref_id"],
        "provider_session_id": refs["provider_session_id"],
        "typed_task_id": refs["typed_task_id"],
        "typed_task_ref": refs["typed_task_ref"],
        "typed_task_ref_status": "boundary_input_validated",
        "invocation_request_ref": refs["invocation_request_ref"],
        "required_provider_run_refs": list(
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
        ),
        **_provider_session_invocation_boundary_status_fields(),
        "boundary_surface_only": True,
        "safe_provider_session_invocation_boundary": True,
        "provider_runner_required": True,
        **_provider_absence_flags(),
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
    _require_expected_values(
        boundary,
        {
            "schema_version": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
            ),
            "boundary_status": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
            ),
            "claim_scope": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
            ),
            "boundary_kind": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_KIND
            ),
            "same_run_invocation_command": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
            ),
            "provider_session_ref_schema_version": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_SCHEMA_VERSION
            ),
            "provider_session_ref_status": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_STATUS,
            "provider_session_ref_claim_scope": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_REF_CLAIM_SCOPE
            ),
        },
        label="provider/session invocation boundary",
    )
    _validate_identifier_fields(
        boundary,
        (
            "boundary_id",
            "provider_session_ref_id",
            "provider_session_id",
            "typed_task_id",
        ),
    )
    _validate_portable_ref_fields(
        boundary,
        ("provider_session_ref", "typed_task_ref", "invocation_request_ref"),
    )
    if boundary.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    _require_expected_values(
        boundary,
        {
            "typed_task_ref_status": "boundary_input_validated",
            **_provider_session_invocation_boundary_status_fields(),
        },
        label="provider/session invocation boundary",
    )
    _require_boolean_values(
        boundary,
        (
            "provider_session_ref_validated",
            "boundary_surface_only",
            "safe_provider_session_invocation_boundary",
            "provider_runner_required",
            "hard_nonclaims_preserved",
            "additive_only_hard_nonclaims",
        ),
        expected=True,
        label="provider/session invocation boundary",
    )
    _validate_provider_material_absence(boundary)
    _require_boolean_values(
        boundary,
        ("provider_profile_or_state_accessed", "provider_cli_executed"),
        expected=False,
        label="provider/session invocation boundary",
    )
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
    _validate_required_reason_codes(
        boundary,
        label="provider/session invocation boundary",
    )

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
            ROW_8_LIVE_VERIFICATION_LABEL,
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

def _provider_session_runner_unavailable_refs(
    *,
    boundary: Mapping[str, Any],
    unavailable_reason_code: str,
    typed_unavailable_ref: str | None,
) -> tuple[str, dict[str, Any]]:
    active_reason = _safe_identifier(
        unavailable_reason_code,
        field_name="unavailable_reason_code",
    )
    token = _route_token(
        boundary["boundary_id"],
        boundary["typed_task_ref"],
        active_reason,
    )
    active_typed_unavailable_ref = _safe_portable_ref(
        typed_unavailable_ref
        or f"typed-unavailable-ref://openyggdrasil/provider-session-runner/{token}",
        field_name="typed_unavailable_ref",
    )
    refs = {
        "reason": active_reason,
        "typed_unavailable_ref": active_typed_unavailable_ref,
        "provider_or_subagent_invocation_typed_unavailable_ref": _safe_portable_ref(
            f"{active_typed_unavailable_ref}/provider-or-subagent-invocation",
            field_name="provider_or_subagent_invocation_typed_unavailable_ref",
        ),
        "before_context_typed_unavailable_ref": _safe_portable_ref(
            f"{active_typed_unavailable_ref}/before-context",
            field_name="before_context_typed_unavailable_ref",
        ),
        "after_context_typed_unavailable_ref": _safe_portable_ref(
            f"{active_typed_unavailable_ref}/after-context",
            field_name="after_context_typed_unavailable_ref",
        ),
        "role_execution_typed_unavailable_refs": _normalize_strict_role_map(
            {
                role: f"{active_typed_unavailable_ref}/role/{role}"
                for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES
            },
            field_name="role_execution_typed_unavailable_refs",
        ),
    }
    return token, refs

def _validate_provider_session_runner_unavailable_claims(
    result: Mapping[str, Any],
) -> None:
    forbidden_claims = (
        "provider_or_subagent_invocation_ref",
        "typed_result_ref",
        "before_context_ref",
        "after_context_ref",
        "role_execution_refs",
    )
    for field in forbidden_claims:
        if result.get(field) is not None:
            raise ValueError(
                f"provider/session runner typed-unavailable result must not claim {field}"
            )
    role_unavailable_refs = _normalize_strict_role_map(
        result.get("role_execution_typed_unavailable_refs") or {},
        field_name="role_execution_typed_unavailable_refs",
    )
    if result.get("role_execution_typed_unavailable_refs") != role_unavailable_refs:
        raise ValueError("role_execution_typed_unavailable_refs must be normalized")
    _validate_identifier_fields(
        result,
        (
            "before_context_unavailable",
            "after_context_unavailable",
            "role_execution_refs_unavailable",
        ),
    )

def _validate_provider_session_runner_result_footer(result: Mapping[str, Any]) -> None:
    if result.get("provider_runner_executor_available") is not False:
        raise ValueError(
            "provider/session runner result requires provider_runner_executor_available=False"
        )
    if result.get("row_8_live_status") != "RUNNER_TYPED_UNAVAILABLE_NOT_LIVE":
        raise ValueError("provider/session runner result must keep row_8 not live")
    _validate_provider_material_absence(result)
    _require_boolean_values(
        result,
        ("provider_profile_or_state_accessed", "provider_cli_executed"),
        expected=False,
        label="provider/session runner result",
    )
    _validate_provider_session_runner_hard_nonclaims(result.get("hard_nonclaims"))
    _validate_provider_session_runner_no_overclaim_flags(
        result.get("no_overclaim_flags")
    )
    _validate_provider_session_runner_llm_contract(result.get("llm_facing_contract"))
    if result.get("runtime_owner") != "runtime/ptc/engine.py":
        raise ValueError(
            "provider/session runner result runtime_owner must be runtime/ptc/engine.py"
        )
    _validate_required_reason_codes(result, label="provider/session runner result")

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
    token, refs = _provider_session_runner_unavailable_refs(
        boundary=boundary,
        unavailable_reason_code=unavailable_reason_code,
        typed_unavailable_ref=typed_unavailable_ref,
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
            refs["provider_or_subagent_invocation_typed_unavailable_ref"]
        ),
        "provider_or_subagent_invocation_unavailable": refs["reason"],
        "typed_result_ref": None,
        "typed_unavailable_ref": refs["typed_unavailable_ref"],
        "before_context_ref": None,
        "before_context_typed_unavailable_ref": refs["before_context_typed_unavailable_ref"],
        "before_context_unavailable": "before_context_ref_not_returned_without_provider_runner",
        "after_context_ref": None,
        "after_context_typed_unavailable_ref": refs["after_context_typed_unavailable_ref"],
        "after_context_unavailable": "after_context_ref_not_returned_without_provider_runner",
        "role_execution_refs": None,
        "role_execution_typed_unavailable_refs": refs["role_execution_typed_unavailable_refs"],
        "role_execution_refs_unavailable": (
            "role_execution_refs_not_returned_without_provider_runner"
        ),
        "required_provider_run_refs": boundary["required_provider_run_refs"],
        "runner_surface_only": True,
        "provider_runner_executor_available": False,
        "safe_typed_unavailable_refs_emitted": True,
        "row_8_live_status": "RUNNER_TYPED_UNAVAILABLE_NOT_LIVE",
        **_provider_absence_flags(),
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
            refs["reason"],
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
    _require_expected_values(
        result,
        {
            "schema_version": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_SCHEMA_VERSION
            ),
            "runner_result_status": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_STATUS
            ),
            "runner_result_kind": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_RESULT_KIND,
            "claim_scope": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_RUNNER_CLAIM_SCOPE,
            "same_run_invocation_command": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
            ),
            "boundary_schema_version": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_SCHEMA_VERSION
            ),
            "boundary_status": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
            ),
            "boundary_claim_scope": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
            ),
        },
        label="provider/session runner result",
    )
    _validate_identifier_fields(
        result,
        (
            "runner_result_id",
            "boundary_id",
            "typed_task_id",
            "provider_or_subagent_invocation_unavailable",
        ),
    )
    _validate_portable_ref_fields(
        result,
        (
            "provider_session_ref",
            "typed_task_ref",
            "invocation_request_ref",
            "provider_or_subagent_invocation_typed_unavailable_ref",
            "typed_unavailable_ref",
            "before_context_typed_unavailable_ref",
            "after_context_typed_unavailable_ref",
        ),
    )
    _validate_provider_session_runner_unavailable_claims(result)
    if result.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    _require_boolean_values(
        result,
        (
            "provider_session_ref_validated",
            "runner_surface_only",
            "safe_typed_unavailable_refs_emitted",
            "hard_nonclaims_preserved",
            "additive_only_hard_nonclaims",
        ),
        expected=True,
        label="provider/session runner result",
    )
    _validate_provider_session_runner_result_footer(result)

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
            ROW_8_LIVE_VERIFICATION_LABEL,
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

def _validate_provider_session_executor_packet_header(
    packet: Mapping[str, Any],
    boundary_input: Mapping[str, Any],
) -> str:
    _validate_provider_session_executor_boundary_payload_fields(packet)
    _validate_provider_material_absence(packet)
    _require_expected_values(
        packet,
        {
            "executor_boundary_kind": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND
            ),
            "executor_evidence_status": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS
            ),
            "fixture_refs_used": False,
            "non_fixture_refs_only": True,
            "same_run_invocation_command": boundary_input.get(
                "same_run_invocation_command"
            ),
            "provider_session_ref": boundary_input.get("provider_session_ref"),
            "typed_task_ref": boundary_input.get("typed_task_ref"),
            "invocation_request_ref": boundary_input.get("invocation_request_ref"),
        },
        label="provider/session executor boundary packet",
    )
    active_typed_task_id = _safe_identifier(
        packet.get("typed_task_id"),
        field_name="typed_task_id",
    )
    if active_typed_task_id != boundary_input.get("typed_task_id"):
        raise ValueError(
            "provider/session executor boundary typed_task_id must match R24 boundary"
        )
    return active_typed_task_id

def _provider_session_executor_refs(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    refs = {
        "executor_boundary_ref": _safe_portable_ref(
            packet.get("executor_boundary_ref"),
            field_name="executor_boundary_ref",
        ),
        "provider_session_ref": _safe_portable_ref(
            packet.get("provider_session_ref"),
            field_name="provider_session_ref",
        ),
        "typed_task_ref": _safe_portable_ref(
            packet.get("typed_task_ref"),
            field_name="typed_task_ref",
        ),
        "invocation_request_ref": _safe_portable_ref(
            packet.get("invocation_request_ref"),
            field_name="invocation_request_ref",
        ),
        "provider_or_subagent_invocation_ref": _require_safe_ref_prefix(
            packet.get("provider_or_subagent_invocation_ref"),
            field_name="provider_or_subagent_invocation_ref",
            prefixes=(
                "provider-session-invocation-ref://",
                "provider-subagent-invocation-ref://",
            ),
        ),
        "typed_result_ref": _require_safe_ref_prefix(
            packet.get("typed_result_ref"),
            field_name="typed_result_ref",
            prefixes=("typed-result-ref://",),
        ),
        "before_context_ref": _require_safe_ref_prefix(
            packet.get("before_context_ref"),
            field_name="before_context_ref",
            prefixes=("context-ref://",),
        ),
        "after_context_ref": _require_safe_ref_prefix(
            packet.get("after_context_ref"),
            field_name="after_context_ref",
            prefixes=("context-ref://",),
        ),
    }
    if packet.get("typed_unavailable_ref") is not None:
        raise ValueError(
            "provider/session executor boundary requires typed_result_ref, not typed_unavailable_ref"
        )
    active_role_execution_refs = _normalize_strict_role_map(
        packet.get("role_execution_refs") or {},
        field_name="role_execution_refs",
    )
    refs["role_execution_refs"] = {
        role: _require_safe_ref_prefix(
            ref,
            field_name=f"role_execution_refs.{role}",
            prefixes=("role-execution-ref://",),
        )
        for role, ref in active_role_execution_refs.items()
    }
    _reject_fixture_typed_ref_terms(*refs.values())
    return refs

def _provider_session_executor_boundary_token(
    boundary_input: Mapping[str, Any],
    refs: Mapping[str, Any],
) -> str:
    return _route_token(
        boundary_input["boundary_id"],
        refs["executor_boundary_ref"],
        refs["provider_session_ref"],
        refs["provider_or_subagent_invocation_ref"],
        refs["typed_result_ref"],
        refs["before_context_ref"],
        refs["after_context_ref"],
        tuple(refs["role_execution_refs"].items()),
    )

def _provider_session_executor_boundary_payload(
    *,
    boundary_input: Mapping[str, Any],
    refs: Mapping[str, Any],
    active_typed_task_id: str,
    active_boundary_ref: str,
    token: str,
    active_hard_nonclaims: Sequence[str],
    active_no_overclaim_flags: Mapping[str, Any],
    packet_reason_codes: Sequence[str],
    generated_at: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION,
        "boundary_id": f"provider-session-executor-boundary-{token}",
        "boundary_ref": active_boundary_ref,
        "executor_boundary_ref": refs["executor_boundary_ref"],
        "executor_boundary_status": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_STATUS,
        "claim_scope": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_CLAIM_SCOPE,
        "executor_boundary_kind": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_KIND,
        "executor_evidence_status": PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_EVIDENCE_STATUS,
        "same_run_invocation_command": boundary_input["same_run_invocation_command"],
        "provider_session_invocation_boundary_id": boundary_input["boundary_id"],
        "provider_session_invocation_boundary_status": boundary_input["boundary_status"],
        "provider_session_invocation_boundary_claim_scope": boundary_input["claim_scope"],
        "provider_session_ref": refs["provider_session_ref"],
        "provider_session_ref_validated": True,
        "typed_task_id": active_typed_task_id,
        "typed_task_ref": refs["typed_task_ref"],
        "invocation_request_ref": refs["invocation_request_ref"],
        "required_provider_run_refs": list(
            PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
        ),
        "provider_or_subagent_invocation_ref": refs["provider_or_subagent_invocation_ref"],
        "role_execution_refs": refs["role_execution_refs"],
        "typed_result_ref": refs["typed_result_ref"],
        "typed_unavailable_ref": None,
        "before_context_ref": refs["before_context_ref"],
        "after_context_ref": refs["after_context_ref"],
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
        "row_8_live_status": ROW_8_EXECUTOR_PENDING_STATUS,
        **_provider_absence_flags(),
        "hard_nonclaims_preserved": True,
        "additive_only_hard_nonclaims": True,
        "hard_nonclaims": list(active_hard_nonclaims),
        "no_overclaim_flags": dict(active_no_overclaim_flags),
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

def _validate_provider_session_executor_boundary_refs(
    boundary: Mapping[str, Any],
) -> dict[str, str]:
    _validate_identifier_fields(
        boundary,
        (
            "boundary_id",
            "provider_session_invocation_boundary_id",
            "typed_task_id",
        ),
    )
    _validate_portable_ref_fields(
        boundary,
        (
            "boundary_ref",
            "executor_boundary_ref",
            "provider_session_ref",
            "typed_task_ref",
            "invocation_request_ref",
        ),
    )
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
    for field in ("before_context_ref", "after_context_ref"):
        _require_safe_ref_prefix(
            boundary.get(field),
            field_name=field,
            prefixes=("context-ref://",),
        )
    return role_refs

def _validate_provider_session_executor_boundary_footer(
    boundary: Mapping[str, Any],
    role_refs: Mapping[str, str],
) -> None:
    _validate_provider_material_absence(boundary)
    _require_boolean_values(
        boundary,
        ("provider_profile_or_state_accessed", "provider_cli_executed"),
        expected=False,
        label="provider/session executor boundary",
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
    _validate_required_reason_codes(boundary, label="provider/session executor boundary")

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
    proof without later row 8 live verification.
    """

    validate_provider_subagent_ptc_provider_session_invocation_boundary(
        provider_session_invocation_boundary
    )
    boundary_input = dict(provider_session_invocation_boundary)
    if not isinstance(executor_result_packet, Mapping):
        raise ValueError("executor_result_packet must be an object")
    packet = dict(executor_result_packet)
    active_typed_task_id = _validate_provider_session_executor_packet_header(
        packet,
        boundary_input,
    )
    refs = _provider_session_executor_refs(packet)
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
    token = _provider_session_executor_boundary_token(boundary_input, refs)
    active_boundary_ref = _safe_portable_ref(
        boundary_ref
        or f"provider-session-executor-boundary-ref://openyggdrasil/ptc/{token}",
        field_name="boundary_ref",
    )
    executor_boundary = _provider_session_executor_boundary_payload(
        boundary_input=boundary_input,
        refs=refs,
        active_typed_task_id=active_typed_task_id,
        active_boundary_ref=active_boundary_ref,
        token=token,
        active_hard_nonclaims=active_hard_nonclaims,
        active_no_overclaim_flags=active_no_overclaim_flags,
        packet_reason_codes=packet_reason_codes,
        generated_at=generated_at,
    )
    validate_provider_subagent_ptc_provider_session_executor_boundary(
        executor_boundary
    )
    return executor_boundary

def validate_provider_subagent_ptc_provider_session_executor_boundary(
    payload: Mapping[str, Any],
) -> None:
    boundary = dict(payload)
    _validate_provider_session_executor_boundary_payload_fields(boundary)
    _require_expected_values(
        boundary,
        {
            "schema_version": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_EXECUTOR_BOUNDARY_SCHEMA_VERSION
            ),
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
            "same_run_invocation_command": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_COMMAND_NAME
            ),
            "provider_session_invocation_boundary_status": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_STATUS
            ),
            "provider_session_invocation_boundary_claim_scope": (
                PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_BOUNDARY_CLAIM_SCOPE
            ),
        },
        label="provider/session executor boundary",
    )
    role_refs = _validate_provider_session_executor_boundary_refs(boundary)
    if boundary.get("required_provider_run_refs") != list(
        PROVIDER_SUBAGENT_PTC_PROVIDER_SESSION_INVOCATION_REQUIRED_OUTPUT_REFS
    ):
        raise ValueError(
            "required_provider_run_refs must match provider/session invocation boundary contract"
        )
    _require_boolean_values(
        boundary,
        (
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
        ),
        expected=True,
        label="provider/session executor boundary",
    )
    _require_boolean_values(
        boundary,
        ("fixture_refs_used", "executor_executed_by_runtime"),
        expected=False,
        label="provider/session executor boundary",
    )
    if boundary.get("row_8_live_status") != ROW_8_EXECUTOR_PENDING_STATUS:
        raise ValueError("provider/session executor boundary must keep row 8 not live")
    _validate_provider_session_executor_boundary_footer(boundary, role_refs)


__all__ = [
    "_validate_provider_session_ref_payload_fields",
    "_normalize_provider_session_ref_hard_nonclaims",
    "_validate_provider_session_ref_hard_nonclaims",
    "_validate_provider_session_ref_no_overclaim_flags",
    "build_provider_subagent_ptc_provider_session_ref",
    "validate_provider_subagent_ptc_provider_session_ref",
    "_validate_provider_session_invocation_boundary_payload_fields",
    "_normalize_provider_session_invocation_boundary_hard_nonclaims",
    "_validate_provider_session_invocation_boundary_hard_nonclaims",
    "_validate_provider_session_invocation_boundary_no_overclaim_flags",
    "_default_provider_session_invocation_boundary_llm_contract",
    "_validate_provider_session_invocation_boundary_llm_contract",
    "build_provider_subagent_ptc_provider_session_invocation_boundary",
    "validate_provider_subagent_ptc_provider_session_invocation_boundary",
    "_validate_provider_session_runner_result_payload_fields",
    "_normalize_provider_session_runner_hard_nonclaims",
    "_validate_provider_session_runner_hard_nonclaims",
    "_validate_provider_session_runner_no_overclaim_flags",
    "_default_provider_session_runner_llm_contract",
    "_validate_provider_session_runner_llm_contract",
    "build_provider_subagent_ptc_provider_session_runner_typed_unavailable_result",
    "validate_provider_subagent_ptc_provider_session_runner_result",
    "_validate_provider_session_executor_boundary_payload_fields",
    "_normalize_provider_session_executor_boundary_hard_nonclaims",
    "_validate_provider_session_executor_boundary_hard_nonclaims",
    "_validate_provider_session_executor_boundary_no_overclaim_flags",
    "_default_provider_session_executor_boundary_llm_contract",
    "_validate_provider_session_executor_boundary_llm_contract",
    "materialize_provider_subagent_ptc_provider_session_executor_boundary",
    "validate_provider_subagent_ptc_provider_session_executor_boundary",
]
