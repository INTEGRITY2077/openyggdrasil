from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.hermes_subagent_reasoning_lease_bridge import (
    build_hermes_subagent_reasoning_lease_bridge,
    validate_hermes_subagent_reasoning_lease_bridge,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_VERSION = "hermes_provider_skill_bridge_entrypoint.v1"
P0_E6_TYPED_HANDOFF_TOLLGATE_SCHEMA_VERSION = "p0_e6_typed_handoff_tollgate.v1"

READY_STATIC_BRIDGE_ENTRYPOINT = "ready_static_bridge_entrypoint"
TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT = (
    "typed_unavailable_provider_skill_package_absent"
)
TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT = (
    "typed_unavailable_app_provider_binding_absent"
)
REJECT_UNSAFE_ENTRYPOINT_PAYLOAD = "reject_unsafe_entrypoint_payload"
ENTRYPOINT_STATUSES = {
    READY_STATIC_BRIDGE_ENTRYPOINT,
    TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT,
    TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT,
    REJECT_UNSAFE_ENTRYPOINT_PAYLOAD,
}
PASS_P0_E6_TYPED_HANDOFF_TOLLGATE = "pass_p0_e6_typed_handoff_tollgate"
TYPED_UNAVAILABLE_P0_E6_TYPED_HANDOFF_TOLLGATE = (
    "typed_unavailable_p0_e6_typed_handoff_tollgate"
)
REJECT_UNSAFE_P0_E6_TYPED_HANDOFF_TOLLGATE = (
    "reject_unsafe_p0_e6_typed_handoff_tollgate"
)
P0_E6_TYPED_HANDOFF_TOLLGATE_STATUSES = {
    PASS_P0_E6_TYPED_HANDOFF_TOLLGATE,
    TYPED_UNAVAILABLE_P0_E6_TYPED_HANDOFF_TOLLGATE,
    REJECT_UNSAFE_P0_E6_TYPED_HANDOFF_TOLLGATE,
}

SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(r"(^[A-Za-z]:|\\\\|/Users/|/home/|/tmp/|file://)", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UNSAFE_REF_FRAGMENTS = (
    ".env",
    ".skill.md",
    "auth.json",
    "credential",
    "openyggdrasil-private-dev",
    "private",
    "profile",
    "prompt",
    "state-db",
    "state_db",
    "state.db",
    "transcript",
)
REF_FIELDS = (
    "provider_skill_ref",
    "provider_skill_package_ref",
    "provider_skill_invocation_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "reasoning_lease_ref",
    "lease_budget_ref",
    "ptc_or_subagent_boundary_ref",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)
READY_REFS = (
    "provider_skill_ref",
    "provider_skill_package_ref",
    "provider_skill_invocation_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "reasoning_lease_ref",
    "ptc_or_subagent_boundary_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)
P0_E6_TYPED_HANDOFF_REFS = (
    "provider_skill_invocation_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
)
UNSAFE_KEY_REASON_CODES = {
    "agent_adapter": "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed",
    "agent_adapter_current_surface": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "command_gateway_current_surface": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "credential_material": "provider_credential_profile_not_allowed",
    "env_exports": "foreground_env_injection_not_allowed",
    "foreground_env_injection": "foreground_env_injection_not_allowed",
    "generic_gateway": "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed",
    "generic_gateway_current_surface": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "hermes_source_hard_coupling": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_patch": "hermes_source_hard_coupling_not_allowed",
    "local_provider_path_material": "local_private_file_ref_not_allowed",
    "mcp_current_surface": "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed",
    "mcp_gateway": "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed",
    "patched_hermes_source": "hermes_source_hard_coupling_not_allowed",
    "private_env_injection": "foreground_env_injection_not_allowed",
    "profile_material": "provider_credential_profile_not_allowed",
    "prompt_text": "raw_prompt_not_allowed",
    "provider_credential": "provider_credential_profile_not_allowed",
    "provider_material": "raw_provider_material_not_allowed",
    "provider_profile": "provider_credential_profile_not_allowed",
    "provider_state_db": "provider_state_db_material_not_allowed",
    "raw_prompt": "raw_prompt_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "raw_session_transcript": "raw_transcript_not_allowed",
    "raw_transcript": "raw_transcript_not_allowed",
    "session_injection": "stdin_or_session_injection_not_allowed",
    "state_db_material": "provider_state_db_material_not_allowed",
    "state_db_result": "provider_state_db_material_not_allowed",
    "stdin_injection": "stdin_or_session_injection_not_allowed",
    "transcript_text": "raw_transcript_not_allowed",
}
UNSAFE_TEXT_REASON_FRAGMENTS = (
    ("agent-adapter", "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"),
    ("agent adapter", "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"),
    ("api_key", "provider_credential_profile_not_allowed"),
    ("auth.json", "provider_credential_profile_not_allowed"),
    ("credential:", "provider_credential_profile_not_allowed"),
    (".env injection", "foreground_env_injection_not_allowed"),
    ("foreground .env injection", "foreground_env_injection_not_allowed"),
    ("generic gateway", "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"),
    ("hermes source patch", "hermes_source_hard_coupling_not_allowed"),
    ("mcp gateway", "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"),
    ("openyggdrasil-private-dev", "local_private_file_ref_not_allowed"),
    ("patched hermes source", "hermes_source_hard_coupling_not_allowed"),
    ("provider credential", "provider_credential_profile_not_allowed"),
    ("provider profile", "provider_credential_profile_not_allowed"),
    ("provider state db", "provider_state_db_material_not_allowed"),
    ("raw prompt", "raw_prompt_not_allowed"),
    ("raw provider material", "raw_provider_material_not_allowed"),
    ("raw transcript", "raw_transcript_not_allowed"),
    ("secret:", "provider_credential_profile_not_allowed"),
    ("session injection", "stdin_or_session_injection_not_allowed"),
    ("session transcript", "raw_transcript_not_allowed"),
    ("state db", "provider_state_db_material_not_allowed"),
    ("state.db", "provider_state_db_material_not_allowed"),
    ("stdin injection", "stdin_or_session_injection_not_allowed"),
)
UNSAFE_FLAG_REASON_CODES = {
    "agent_adapter_surface_claimed": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "background_live_integration_claimed": "background_live_integration_claim_not_allowed",
    "foreground_env_injection_used": "foreground_env_injection_not_allowed",
    "generic_gateway_surface_claimed": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "hermes_answer_quality_claimed": "hermes_answer_quality_claim_not_allowed",
    "hermes_source_hard_coupled": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_patch_used": "hermes_source_hard_coupling_not_allowed",
    "hermes_subagent_live_bridge_complete_claimed": (
        "hermes_subagent_live_bridge_complete_claim_not_allowed"
    ),
    "live_readiness_claimed": "live_readiness_claim_not_allowed",
    "local_private_file_ref_included": "local_private_file_ref_not_allowed",
    "mcp_gateway_surface_claimed": (
        "mcp_generic_gateway_or_agent_adapter_current_surface_not_allowed"
    ),
    "p4_h6_closed_claimed": "p4_h6_closed_claim_not_allowed",
    "private_env_injection_used": "foreground_env_injection_not_allowed",
    "production_readiness_claimed": "production_readiness_claim_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "provider_state_db_material_included": "provider_state_db_material_not_allowed",
    "public_runtime_integration_complete_claimed": (
        "public_runtime_integration_complete_claim_not_allowed"
    ),
    "r9_real_session_pass_claimed": "r9_real_session_pass_claim_not_allowed",
    "r10_live_pass_claimed": "r10_live_pass_claim_not_allowed",
    "raw_prompt_included": "raw_prompt_not_allowed",
    "raw_provider_material_included": "raw_provider_material_not_allowed",
    "raw_transcript_included": "raw_transcript_not_allowed",
    "reasoning_lease_solved_claimed": "reasoning_lease_solved_claim_not_allowed",
    "safe_live_gateway_pass_claimed": "safe_live_gateway_pass_claim_not_allowed",
    "session_injection_used": "stdin_or_session_injection_not_allowed",
    "stdin_injection_used": "stdin_or_session_injection_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    flag_name: False for flag_name in UNSAFE_FLAG_REASON_CODES
}
DEFAULT_E12B_SURFACE_REFS = {
    "persona_or_prompt_ref": "persona-ref://openyggdrasil/pathfinder/v1",
    "schema_ref": (
        "contract-ref://openyggdrasil/contracts/"
        "hermes_provider_skill_bridge_entrypoint.v1.schema.json"
    ),
    "runtime_enforcement_ref": (
        "runtime-module-ref://openyggdrasil/runtime/reasoning/"
        "hermes_provider_skill_bridge_entrypoint.py"
    ),
    "global_hard_nonclaims_ref": "persona-ref://openyggdrasil/common/v1",
}


@lru_cache(maxsize=1)
def load_hermes_provider_skill_bridge_entrypoint_schema() -> dict[str, Any]:
    return json.loads(
        (
            CONTRACTS_ROOT
            / "hermes_provider_skill_bridge_entrypoint.v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _is_safe_identifier(value: Any) -> bool:
    return bool(IDENTIFIER_RE.match(str(value or "").strip()))


def _safe_identifier(value: Any) -> str | None:
    string_value = str(value or "").strip()
    return string_value if _is_safe_identifier(string_value) else None


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if LOCAL_PATH_RE.search(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _unsafe_text_reason(value: str) -> str | None:
    if LOCAL_PATH_RE.search(value):
        return "local_private_file_ref_not_allowed"
    lowered = value.lower()
    for fragment, reason_code in UNSAFE_TEXT_REASON_FRAGMENTS:
        if fragment in lowered:
            return reason_code
    return None


def _unsafe_key_reason(key: str) -> str | None:
    lowered = str(key).lower()
    for unsafe_key, reason_code in UNSAFE_KEY_REASON_CODES.items():
        if unsafe_key == lowered or unsafe_key in lowered:
            return reason_code
    return None


def _unsafe_material_reason(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_reason = _unsafe_key_reason(str(key))
            if key_reason is not None:
                return key_reason
            nested_reason = _unsafe_material_reason(nested)
            if nested_reason is not None:
                return nested_reason
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            item_reason = _unsafe_material_reason(item)
            if item_reason is not None:
                return item_reason
        return None
    if isinstance(value, str):
        return _unsafe_text_reason(value)
    return None


def _unsafe_flag_reason_codes(flags: Mapping[str, Any]) -> list[str]:
    return [
        reason_code
        for flag_name, reason_code in UNSAFE_FLAG_REASON_CODES.items()
        if flags.get(flag_name) is True
    ]


def _safe_ref_from(request: Mapping[str, Any], field: str) -> str | None:
    value = request.get(field)
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value if _is_safe_ref(string_value) else None


def _safe_refs_from_request(request: Mapping[str, Any]) -> dict[str, str]:
    safe_refs = {
        field: safe_ref
        for field in REF_FIELDS
        if (safe_ref := _safe_ref_from(request, field)) is not None
    }
    for field, default_ref in DEFAULT_E12B_SURFACE_REFS.items():
        if request.get(field) is None:
            safe_refs[field] = default_ref
    return safe_refs


def _unsafe_ref_fields(request: Mapping[str, Any], safe_refs: Mapping[str, str]) -> list[str]:
    return [
        field
        for field in REF_FIELDS
        if request.get(field) is not None and field not in safe_refs
    ]


def _missing_ref_fields(fields: Sequence[str], safe_refs: Mapping[str, str]) -> list[str]:
    return [field for field in fields if field not in safe_refs]


def _unique_values(values: Sequence[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def _output_ref(status: str, safe_refs: Mapping[str, str], field: str) -> str | None:
    if status == REJECT_UNSAFE_ENTRYPOINT_PAYLOAD:
        return None
    return safe_refs.get(field)


def _typed_unavailable_ref(
    status: str,
    safe_refs: Mapping[str, str],
    entrypoint_id: str,
) -> str | None:
    if status == REJECT_UNSAFE_ENTRYPOINT_PAYLOAD:
        return None
    if safe_refs.get("typed_unavailable_ref"):
        return safe_refs["typed_unavailable_ref"]
    if status in {
        TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT,
        TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT,
    }:
        return f"typed-unavailable-ref://openyggdrasil/p0-e2/{entrypoint_id}"
    return None


def _p0_e6_generated_typed_unavailable_ref(tollgate_id: str) -> str:
    return f"typed-unavailable-ref://openyggdrasil/p0-e6/typed-handoff/{tollgate_id}"


def _bridge_request_from_entrypoint(
    request: Mapping[str, Any],
    safe_refs: Mapping[str, str],
    typed_task_id: str,
    lease_depth_or_effort: str,
    lease_unavailable_reason: str | None,
) -> dict[str, Any]:
    provider_gateway_proof_ref = safe_refs["provider_skill_invocation_ref"]
    bridge_request = {
        "provider": "hermes",
        "input_schema_versions": [
            SCHEMA_VERSION,
            "hermes_subagent_reasoning_lease_bridge.v1",
        ],
        "provider_skill_ref": safe_refs["provider_skill_ref"],
        "provider_subagent_surface_ref": safe_refs["provider_subagent_surface_ref"],
        "persona_or_prompt_ref": safe_refs["persona_or_prompt_ref"],
        "schema_ref": (
            "contract-ref://openyggdrasil/contracts/"
            "hermes_subagent_reasoning_lease_bridge.v1.schema.json"
        ),
        "runtime_enforcement_ref": (
            "runtime-module-ref://openyggdrasil/runtime/reasoning/"
            "hermes_subagent_reasoning_lease_bridge.py"
        ),
        "global_hard_nonclaims_ref": safe_refs["global_hard_nonclaims_ref"],
        "reasoning_lease_ref": safe_refs["reasoning_lease_ref"],
        "lease_depth_or_effort": lease_depth_or_effort,
        "ptc_or_subagent_boundary_ref": safe_refs["ptc_or_subagent_boundary_ref"],
        "provider_gateway_proof_ref": provider_gateway_proof_ref,
        "typed_task_id": typed_task_id,
        "before_main_context_window_ref": safe_refs["before_main_context_window_ref"],
        "after_main_context_window_ref": safe_refs["after_main_context_window_ref"],
        "producer_receipt_ref": safe_refs["producer_receipt_ref"],
        "consumer_usage_ref": safe_refs["consumer_usage_ref"],
    }
    if safe_refs.get("lease_budget_ref"):
        bridge_request["lease_budget_ref"] = safe_refs["lease_budget_ref"]
    if lease_unavailable_reason is not None:
        bridge_request["lease_unavailable_reason"] = lease_unavailable_reason
    if safe_refs.get("typed_result_ref"):
        bridge_request["typed_result_ref"] = safe_refs["typed_result_ref"]
    if safe_refs.get("typed_unavailable_ref"):
        bridge_request["typed_unavailable_ref"] = safe_refs["typed_unavailable_ref"]
    for flag_name in DEFAULT_SAFETY_FLAGS:
        if request.get(flag_name) is True:
            bridge_request[flag_name] = True
    return bridge_request


def validate_p0_e6_typed_handoff_tollgate(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != P0_E6_TYPED_HANDOFF_TOLLGATE_SCHEMA_VERSION:
        raise ValueError("invalid P0-E6 typed handoff tollgate schema_version")
    if payload.get("handoff_status") not in P0_E6_TYPED_HANDOFF_TOLLGATE_STATUSES:
        raise ValueError("invalid P0-E6 typed handoff tollgate status")
    if payload.get("runtime_owner") != (
        "runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py"
    ):
        raise ValueError("invalid P0-E6 typed handoff runtime owner")
    if payload.get("provider") != "hermes":
        raise ValueError("P0-E6 typed handoff tollgate requires provider hermes")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("P0-E6 typed handoff tollgate must use typed refs only")
    if payload.get("provider_skill_only") is not True:
        raise ValueError("P0-E6 typed handoff tollgate must stay provider-skill only")
    if payload.get("provider_gateway_called") is not False:
        raise ValueError("P0-E6 typed handoff tollgate must not call Hermes")
    if payload.get("provider_state_read") is not False:
        raise ValueError("P0-E6 typed handoff tollgate must not read provider state")
    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe P0-E6 typed handoff flag: {flag_name}")

    if not payload.get("reason_codes"):
        raise ValueError("P0-E6 typed handoff tollgate requires reason_codes")
    for reason_code in payload.get("reason_codes") or []:
        if not _is_safe_identifier(reason_code):
            raise ValueError("P0-E6 reason_codes must be safe identifiers")
    for reason_code in payload.get("safety_reject_reasons") or []:
        if not _is_safe_identifier(reason_code):
            raise ValueError("P0-E6 safety_reject_reasons must be safe identifiers")

    typed_task_id = payload.get("typed_task_id")
    if typed_task_id is not None and not _is_safe_identifier(typed_task_id):
        raise ValueError("P0-E6 typed_task_id must be a safe identifier")
    for field in (
        "typed_result_ref",
        "typed_unavailable_ref",
        *P0_E6_TYPED_HANDOFF_REFS,
    ):
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"P0-E6 {field} must be a safe portable ref")

    status = payload.get("handoff_status")
    if status == PASS_P0_E6_TYPED_HANDOFF_TOLLGATE:
        if typed_task_id is None:
            raise ValueError("P0-E6 pass requires typed_task_id")
        if not (payload.get("typed_result_ref") or payload.get("typed_unavailable_ref")):
            raise ValueError("P0-E6 pass requires typed result or unavailable ref")
        for field in P0_E6_TYPED_HANDOFF_REFS:
            if not payload.get(field):
                raise ValueError(f"P0-E6 pass requires {field}")
        if payload.get("unsafe_flags") is not False:
            raise ValueError("P0-E6 pass requires unsafe_flags false")
        if payload.get("safety_reject_reasons"):
            raise ValueError("P0-E6 pass must not include safety reject reasons")
    elif status == TYPED_UNAVAILABLE_P0_E6_TYPED_HANDOFF_TOLLGATE:
        if not payload.get("typed_unavailable_ref"):
            raise ValueError("P0-E6 typed unavailable requires typed_unavailable_ref")
        if not payload.get("unavailable_condition"):
            raise ValueError("P0-E6 typed unavailable requires unavailable_condition")
    elif status == REJECT_UNSAFE_P0_E6_TYPED_HANDOFF_TOLLGATE:
        if payload.get("reject_condition") != "unsafe_typed_handoff_payload":
            raise ValueError("P0-E6 reject requires exact reject condition")
        if not payload.get("safety_reject_reasons"):
            raise ValueError("P0-E6 reject requires safety_reject_reasons")


def build_p0_e6_typed_handoff_tollgate(
    *,
    handoff_response: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Classify one Hermes provider-skill handoff without echoing unsafe material."""

    if not isinstance(handoff_response, Mapping):
        response: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        response = dict(handoff_response)
        unsupported_input_shape = False

    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(response.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in response})

    reason_codes = _unsafe_flag_reason_codes(flags)
    unsafe_material_reason = _unsafe_material_reason(response)
    if unsafe_material_reason is not None:
        reason_codes.append(unsafe_material_reason)

    safe_refs = _safe_refs_from_request(response)
    unsafe_ref_fields = _unsafe_ref_fields(response, safe_refs)
    if unsafe_ref_fields:
        reason_codes.extend([f"unsafe_ref:{field}" for field in unsafe_ref_fields])

    tollgate_id = uuid.uuid4().hex
    typed_task_id = _safe_identifier(response.get("typed_task_id"))
    unsafe_flags_value = response.get("unsafe_flags")
    typed_result_or_unavailable_present = bool(
        safe_refs.get("typed_result_ref") or safe_refs.get("typed_unavailable_ref")
    )
    missing_refs = _missing_ref_fields(P0_E6_TYPED_HANDOFF_REFS, safe_refs)
    missing_fields: list[str] = []

    if unsupported_input_shape:
        missing_fields.append("handoff_response")
    if typed_task_id is None:
        missing_fields.append("typed_task_id")
    if not typed_result_or_unavailable_present:
        missing_fields.append("typed_result_ref_or_typed_unavailable_ref")
    if unsafe_flags_value is None:
        missing_fields.append("unsafe_flags")
    elif unsafe_flags_value is not False:
        reason_codes.append("unsafe_flags_not_false")
    missing_fields.extend(missing_refs)

    if reason_codes:
        status = REJECT_UNSAFE_P0_E6_TYPED_HANDOFF_TOLLGATE
        unavailable_condition = None
        reject_condition = "unsafe_typed_handoff_payload"
        safety_reject_reasons = _unique_values(reason_codes)
        output_refs: Mapping[str, str] = {}
        output_typed_task_id = None
        output_unsafe_flags = None
    elif missing_fields:
        status = TYPED_UNAVAILABLE_P0_E6_TYPED_HANDOFF_TOLLGATE
        unavailable_condition = "typed_handoff_refs_absent"
        reject_condition = None
        safety_reject_reasons = []
        reason_codes = [
            *[f"missing:{field}" for field in missing_fields],
            "typed_handoff_refs_absent",
        ]
        output_refs = safe_refs
        output_typed_task_id = typed_task_id
        output_unsafe_flags = unsafe_flags_value if unsafe_flags_value is False else None
    else:
        status = PASS_P0_E6_TYPED_HANDOFF_TOLLGATE
        unavailable_condition = None
        reject_condition = None
        safety_reject_reasons = []
        reason_codes = [
            "typed_handoff_tollgate_passed",
            "typed_task_id_present",
            "typed_result_or_unavailable_ref_present",
            "provider_skill_invocation_ref_present",
            "context_window_refs_present",
            "unsafe_flags_false",
        ]
        output_refs = safe_refs
        output_typed_task_id = typed_task_id
        output_unsafe_flags = False

    typed_unavailable_ref = output_refs.get("typed_unavailable_ref")
    if status == TYPED_UNAVAILABLE_P0_E6_TYPED_HANDOFF_TOLLGATE and not typed_unavailable_ref:
        typed_unavailable_ref = _p0_e6_generated_typed_unavailable_ref(tollgate_id)

    payload = {
        "schema_version": P0_E6_TYPED_HANDOFF_TOLLGATE_SCHEMA_VERSION,
        "tollgate_id": tollgate_id,
        "provider": "hermes",
        "handoff_status": status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": _unique_values(reason_codes),
        "safety_reject_reasons": safety_reject_reasons,
        "typed_task_id": output_typed_task_id,
        "typed_result_ref": output_refs.get("typed_result_ref"),
        "typed_unavailable_ref": typed_unavailable_ref,
        "provider_skill_invocation_ref": output_refs.get("provider_skill_invocation_ref"),
        "before_main_context_window_ref": output_refs.get(
            "before_main_context_window_ref"
        ),
        "after_main_context_window_ref": output_refs.get("after_main_context_window_ref"),
        "unsafe_flags": output_unsafe_flags,
        "runtime_owner": "runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py",
        "provider_skill_only": True,
        "typed_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        **{flag_name: False for flag_name in DEFAULT_SAFETY_FLAGS},
        "created_at": utc_now_iso(),
    }
    validate_p0_e6_typed_handoff_tollgate(payload)
    return payload


def validate_hermes_provider_skill_bridge_entrypoint(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_provider_skill_bridge_entrypoint_schema(),
    )

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Hermes provider skill bridge entrypoint schema_version")
    if payload.get("entrypoint_status") not in ENTRYPOINT_STATUSES:
        raise ValueError("invalid Hermes provider skill bridge entrypoint status")
    if payload.get("runtime_owner") != (
        "runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py"
    ):
        raise ValueError("invalid Hermes provider skill bridge entrypoint runtime owner")
    if payload.get("static_bridge_entrypoint_only") is not True:
        raise ValueError("Hermes provider skill bridge entrypoint must remain static only")
    if payload.get("provider_skill_only") is not True:
        raise ValueError("Hermes provider skill bridge entrypoint must remain provider-skill only")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("Hermes provider skill bridge entrypoint must use typed refs only")
    if payload.get("provider_gateway_called") is not False:
        raise ValueError("Hermes provider skill bridge entrypoint must not call Hermes")
    if payload.get("provider_state_read") is not False:
        raise ValueError("Hermes provider skill bridge entrypoint must not read provider state")
    if payload.get("unsafe_flags") is not False:
        raise ValueError("Hermes provider skill bridge entrypoint requires unsafe_flags false")

    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe Hermes provider skill entrypoint flag: {flag_name}")

    for field in ("entrypoint_ref", *REF_FIELDS):
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"{field} must be a safe portable ref")

    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe portable refs")

    for reason_code in payload.get("reason_codes") or []:
        if not _is_safe_identifier(reason_code):
            raise ValueError("reason_codes must be safe identifiers")
    for reason_code in payload.get("safety_reject_reasons") or []:
        if not _is_safe_identifier(reason_code):
            raise ValueError("safety_reject_reasons must be safe identifiers")

    status = payload.get("entrypoint_status")
    bridge_payload = payload.get("bridge_payload")
    if status == READY_STATIC_BRIDGE_ENTRYPOINT:
        if payload.get("provider") != "hermes":
            raise ValueError("ready entrypoint requires provider hermes")
        if payload.get("provider_skill_package_available") is not True:
            raise ValueError("ready entrypoint requires provider skill package")
        if payload.get("app_provider_binding_available") is not True:
            raise ValueError("ready entrypoint requires app provider binding")
        if not payload.get("typed_task_id"):
            raise ValueError("ready entrypoint requires typed_task_id")
        if not (payload.get("typed_result_ref") or payload.get("typed_unavailable_ref")):
            raise ValueError("ready entrypoint requires typed result or unavailable ref")
        if not (payload.get("lease_budget_ref") or payload.get("lease_unavailable_reason")):
            raise ValueError("ready entrypoint requires lease budget ref or unavailable reason")
        for field in READY_REFS:
            if not payload.get(field):
                raise ValueError(f"ready entrypoint requires {field}")
        if not isinstance(bridge_payload, Mapping):
            raise ValueError("ready entrypoint requires mapped R10 bridge payload")
        validate_hermes_subagent_reasoning_lease_bridge(bridge_payload)
        if bridge_payload.get("bridge_status") != "static_bridge_contract_ready":
            raise ValueError("ready entrypoint requires R10 static bridge contract ready")
        if bridge_payload.get("provider_gateway_proof_ref") != payload.get(
            "provider_skill_invocation_ref"
        ):
            raise ValueError("provider skill invocation must map to R10 proof ref")
    elif status == TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT:
        if payload.get("unavailable_condition") != "provider_skill_package_absent":
            raise ValueError("provider package absent status requires exact unavailable condition")
        if bridge_payload is not None:
            raise ValueError("provider package absent status must not include bridge payload")
    elif status == TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT:
        if payload.get("unavailable_condition") != "app_provider_binding_absent":
            raise ValueError("app binding absent status requires exact unavailable condition")
        if bridge_payload is not None:
            raise ValueError("app binding absent status must not include bridge payload")
    elif status == REJECT_UNSAFE_ENTRYPOINT_PAYLOAD:
        if payload.get("reject_condition") != "unsafe_entrypoint_payload":
            raise ValueError("rejected entrypoint requires exact reject condition")
        if not payload.get("safety_reject_reasons"):
            raise ValueError("rejected entrypoint requires safety_reject_reasons")
        if bridge_payload is not None:
            raise ValueError("rejected entrypoint must not include bridge payload")

    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")


def build_hermes_provider_skill_bridge_entrypoint(
    *,
    entrypoint_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a static Hermes provider-skill bridge entrypoint proof shape.

    This function does not call Hermes, inspect provider state, patch source, or
    treat a generic gateway as a valid P0 surface. The only ready path maps a
    safe provider-skill entrypoint package into the existing R10 bridge
    validator.
    """

    if not isinstance(entrypoint_request, Mapping):
        request: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        request = dict(entrypoint_request)
        unsupported_input_shape = False

    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(request.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in request})

    reason_codes = _unsafe_flag_reason_codes(flags)
    unsafe_material_reason = _unsafe_material_reason(request)
    if unsafe_material_reason is not None:
        reason_codes.append(unsafe_material_reason)

    safe_refs = _safe_refs_from_request(request)
    unsafe_ref_fields = _unsafe_ref_fields(request, safe_refs)
    if unsafe_ref_fields:
        reason_codes.extend([f"unsafe_ref:{field}" for field in unsafe_ref_fields])

    entrypoint_id = uuid.uuid4().hex
    provider = str(request.get("provider") or "hermes").strip().lower()
    typed_task_id = _safe_identifier(request.get("typed_task_id"))
    lease_depth_or_effort = _safe_identifier(request.get("lease_depth_or_effort"))
    lease_unavailable_reason = _safe_identifier(request.get("lease_unavailable_reason"))
    package_available = bool(request.get("provider_skill_package_available"))
    binding_available = bool(request.get("app_provider_binding_available"))

    unavailable_condition: str | None = None
    reject_condition: str | None = None
    safety_reject_reasons: list[str] = []
    bridge_payload: dict[str, Any] | None = None

    if unsupported_input_shape:
        status = TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT
        unavailable_condition = "provider_skill_package_absent"
        reason_codes = ["unsupported_input_shape", "provider_skill_package_absent"]
    elif provider != "hermes":
        status = TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT
        unavailable_condition = "provider_skill_package_absent"
        reason_codes = ["provider_hermes_required", "provider_skill_package_absent"]
    elif reason_codes:
        status = REJECT_UNSAFE_ENTRYPOINT_PAYLOAD
        reject_condition = "unsafe_entrypoint_payload"
        safety_reject_reasons = _unique_values(reason_codes)
    elif not package_available:
        status = TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT
        unavailable_condition = "provider_skill_package_absent"
        reason_codes = ["provider_skill_package_absent"]
    elif "provider_skill_package_ref" not in safe_refs:
        status = TYPED_UNAVAILABLE_PROVIDER_SKILL_PACKAGE_ABSENT
        unavailable_condition = "provider_skill_package_absent"
        reason_codes = ["provider_skill_package_ref_absent", "provider_skill_package_absent"]
    elif not binding_available:
        status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
        unavailable_condition = "app_provider_binding_absent"
        reason_codes = ["app_provider_binding_absent"]
    elif typed_task_id is None:
        status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
        unavailable_condition = "app_provider_binding_absent"
        reason_codes = ["typed_task_id_absent", "app_provider_binding_absent"]
    elif not (safe_refs.get("typed_result_ref") or safe_refs.get("typed_unavailable_ref")):
        status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
        unavailable_condition = "app_provider_binding_absent"
        reason_codes = ["typed_result_or_unavailable_ref_absent", "app_provider_binding_absent"]
    elif lease_depth_or_effort is None:
        status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
        unavailable_condition = "app_provider_binding_absent"
        reason_codes = ["lease_depth_or_effort_absent", "app_provider_binding_absent"]
    elif "lease_budget_ref" not in safe_refs and lease_unavailable_reason is None:
        status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
        unavailable_condition = "app_provider_binding_absent"
        reason_codes = [
            "lease_budget_or_unavailable_reason_absent",
            "app_provider_binding_absent",
        ]
    else:
        missing_refs = _missing_ref_fields(READY_REFS, safe_refs)
        if missing_refs:
            status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
            unavailable_condition = "app_provider_binding_absent"
            reason_codes = [
                *[f"missing_ref:{field}" for field in missing_refs],
                "app_provider_binding_absent",
            ]
        else:
            bridge_request = _bridge_request_from_entrypoint(
                request,
                safe_refs,
                typed_task_id,
                lease_depth_or_effort,
                lease_unavailable_reason,
            )
            bridge_payload = build_hermes_subagent_reasoning_lease_bridge(
                bridge_request=bridge_request
            )
            validate_hermes_subagent_reasoning_lease_bridge(bridge_payload)
            if bridge_payload.get("bridge_status") != "static_bridge_contract_ready":
                status = TYPED_UNAVAILABLE_APP_PROVIDER_BINDING_ABSENT
                unavailable_condition = "app_provider_binding_absent"
                reason_codes = [
                    "r10_bridge_static_contract_unavailable",
                    "app_provider_binding_absent",
                ]
                bridge_payload = None
            else:
                status = READY_STATIC_BRIDGE_ENTRYPOINT
                reason_codes = [
                    "ready_static_bridge_entrypoint",
                    "provider_skill_package_present",
                    "app_provider_binding_present",
                    "persona_or_prompt_ref_present",
                    "schema_ref_present",
                    "runtime_enforcement_ref_present",
                    "global_hard_nonclaims_ref_present",
                    "provider_skill_invocation_ref_mapped_to_r10_proof_ref",
                    "r10_static_bridge_contract_ready",
                ]

    entrypoint_ref = (
        f"hermes-provider-skill-bridge-entrypoint-ref://openyggdrasil/p0-e2/{entrypoint_id}"
        if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD
        else None
    )
    typed_unavailable_ref = _typed_unavailable_ref(status, safe_refs, entrypoint_id)
    ref_values = [
        entrypoint_ref,
        typed_unavailable_ref,
        *[_output_ref(status, safe_refs, field) for field in REF_FIELDS],
    ]
    safe_portable_refs = _unique_values([ref for ref in ref_values if ref])

    payload = {
        "schema_version": SCHEMA_VERSION,
        "entrypoint_id": entrypoint_id,
        "entrypoint_ref": entrypoint_ref,
        "provider": provider if provider == "hermes" else None,
        "entrypoint_status": status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": _unique_values(reason_codes),
        "safety_reject_reasons": safety_reject_reasons,
        "provider_skill_package_available": (
            package_available if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD else False
        ),
        "app_provider_binding_available": (
            binding_available if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD else False
        ),
        "provider_skill_ref": _output_ref(status, safe_refs, "provider_skill_ref"),
        "provider_skill_package_ref": _output_ref(
            status, safe_refs, "provider_skill_package_ref"
        ),
        "provider_skill_invocation_ref": _output_ref(
            status, safe_refs, "provider_skill_invocation_ref"
        ),
        "provider_subagent_surface_ref": _output_ref(
            status, safe_refs, "provider_subagent_surface_ref"
        ),
        "persona_or_prompt_ref": _output_ref(status, safe_refs, "persona_or_prompt_ref"),
        "schema_ref": _output_ref(status, safe_refs, "schema_ref"),
        "runtime_enforcement_ref": _output_ref(
            status, safe_refs, "runtime_enforcement_ref"
        ),
        "global_hard_nonclaims_ref": _output_ref(
            status, safe_refs, "global_hard_nonclaims_ref"
        ),
        "reasoning_lease_ref": _output_ref(status, safe_refs, "reasoning_lease_ref"),
        "lease_depth_or_effort": (
            lease_depth_or_effort
            if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD
            else None
        ),
        "lease_budget_ref": _output_ref(status, safe_refs, "lease_budget_ref"),
        "lease_unavailable_reason": (
            lease_unavailable_reason
            if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD
            else None
        ),
        "ptc_or_subagent_boundary_ref": _output_ref(
            status, safe_refs, "ptc_or_subagent_boundary_ref"
        ),
        "typed_task_id": (
            typed_task_id if status != REJECT_UNSAFE_ENTRYPOINT_PAYLOAD else None
        ),
        "typed_result_ref": _output_ref(status, safe_refs, "typed_result_ref"),
        "typed_unavailable_ref": typed_unavailable_ref,
        "before_main_context_window_ref": _output_ref(
            status, safe_refs, "before_main_context_window_ref"
        ),
        "after_main_context_window_ref": _output_ref(
            status, safe_refs, "after_main_context_window_ref"
        ),
        "producer_receipt_ref": _output_ref(status, safe_refs, "producer_receipt_ref"),
        "consumer_usage_ref": _output_ref(status, safe_refs, "consumer_usage_ref"),
        "bridge_payload": bridge_payload,
        "safe_portable_refs": safe_portable_refs,
        "input_schema_versions": _as_string_list(request.get("input_schema_versions")),
        "ptc_callable": True,
        "runtime_owner": "runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py",
        "static_bridge_entrypoint_only": True,
        "provider_skill_only": True,
        "typed_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "unsafe_flags": False,
        "generic_gateway_surface_claimed": False,
        "mcp_gateway_surface_claimed": False,
        "agent_adapter_surface_claimed": False,
        "hermes_source_hard_coupled": False,
        "hermes_source_patch_used": False,
        "foreground_env_injection_used": False,
        "private_env_injection_used": False,
        "stdin_injection_used": False,
        "session_injection_used": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "raw_provider_material_included": False,
        "provider_credential_profile_included": False,
        "provider_state_db_material_included": False,
        "local_private_file_ref_included": False,
        "safe_live_gateway_pass_claimed": False,
        "hermes_subagent_live_bridge_complete_claimed": False,
        "r9_real_session_pass_claimed": False,
        "r10_live_pass_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "background_live_integration_claimed": False,
        "p4_h6_closed_claimed": False,
        "hermes_answer_quality_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_hermes_provider_skill_bridge_entrypoint(payload)
    return payload
