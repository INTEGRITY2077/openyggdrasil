from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.base_utils import (
    _normalize_same_run_ptc_context,
    _normalize_strict_role_map,
    _route_token,
    _string_list,
    _utc_now_iso,
)
from runtime.ptc.engine_contracts import (
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_CLAIM_SCOPE,
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_HARD_NONCLAIMS,
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_NO_OVERCLAIM_FLAGS,
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_SCHEMA_VERSION,
    PROVIDER_SUBAGENT_PTC_EXECUTION_TRACE_PACKET_STATUS,
    REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES,
    _assert_additive_only_hard_nonclaims,
    _safe_portable_ref,
)
from runtime.ptc.telemetry_trace import _role_execution_refs_from_ptc_telemetry

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


__all__ = [
    "_normalize_execution_trace_hard_nonclaims",
    "_validate_execution_trace_hard_nonclaims",
    "_validate_no_overclaim_flags",
    "build_provider_subagent_ptc_execution_trace_packet",
    "validate_provider_subagent_ptc_execution_trace_packet",
]
