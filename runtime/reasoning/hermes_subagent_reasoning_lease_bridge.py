from __future__ import annotations

import re
import uuid
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso


SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(r"(^[A-Za-z]:|\\\\|/Users/|/home/|/tmp/|file://)", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RAW_SKILL_BODY_RE = re.compile(r"(?s)^---\s*\n.*\bname\s*:")
UNSAFE_REF_FRAGMENTS = (
    ".skill.md",
    "credential",
    "profile",
    "transcript",
)
REF_FIELDS = (
    "provider_skill_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "reasoning_lease_ref",
    "lease_budget_ref",
    "ptc_or_subagent_boundary_ref",
    "provider_gateway_proof_ref",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)
REQUIRED_STATIC_READY_REFS = (
    "provider_skill_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "reasoning_lease_ref",
    "ptc_or_subagent_boundary_ref",
    "provider_gateway_proof_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)
UNSAFE_KEY_REASON_CODES = {
    "hermes_source_patch": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_hard_coupling": "hermes_source_hard_coupling_not_allowed",
    "patched_hermes_source": "hermes_source_hard_coupling_not_allowed",
    "foreground_env_injection": "foreground_env_injection_not_allowed",
    "private_env_injection": "foreground_env_injection_not_allowed",
    "env_exports": "foreground_env_injection_not_allowed",
    "stdin_injection": "stdin_injection_not_allowed",
    "raw_transcript": "raw_transcript_not_allowed",
    "raw_session_transcript": "raw_transcript_not_allowed",
    "transcript_text": "raw_transcript_not_allowed",
    "raw_prompt": "raw_prompt_not_allowed",
    "prompt_text": "raw_prompt_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "provider_material": "raw_provider_material_not_allowed",
    "provider_credential": "provider_credential_profile_not_allowed",
    "provider_profile": "provider_credential_profile_not_allowed",
    "credential_material": "provider_credential_profile_not_allowed",
    "profile_material": "provider_credential_profile_not_allowed",
    "provider_state_db": "provider_state_db_material_not_allowed",
    "state_db_result": "provider_state_db_material_not_allowed",
    "state_db_material": "provider_state_db_material_not_allowed",
    "skill_body": "skill_body_not_allowed",
    "raw_skill_body": "skill_body_not_allowed",
}
UNSAFE_TEXT_REASON_FRAGMENTS = (
    ("hermes source patch", "hermes_source_hard_coupling_not_allowed"),
    ("patched hermes source", "hermes_source_hard_coupling_not_allowed"),
    ("foreground .env injection", "foreground_env_injection_not_allowed"),
    (".env injection", "foreground_env_injection_not_allowed"),
    ("openyggdrasil-private-dev", "foreground_env_injection_not_allowed"),
    ("stdin injection", "stdin_injection_not_allowed"),
    ("raw transcript", "raw_transcript_not_allowed"),
    ("session transcript", "raw_transcript_not_allowed"),
    ("raw prompt", "raw_prompt_not_allowed"),
    ("provider credential", "provider_credential_profile_not_allowed"),
    ("provider profile", "provider_credential_profile_not_allowed"),
    ("credential:", "provider_credential_profile_not_allowed"),
    ("secret:", "provider_credential_profile_not_allowed"),
    ("api_key", "provider_credential_profile_not_allowed"),
    ("auth.json", "provider_credential_profile_not_allowed"),
    ("provider state db", "provider_state_db_material_not_allowed"),
    ("state db", "provider_state_db_material_not_allowed"),
)
UNSAFE_FLAG_REASON_CODES = {
    "hermes_source_hard_coupled": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_patch_used": "hermes_source_hard_coupling_not_allowed",
    "foreground_env_injection_used": "foreground_env_injection_not_allowed",
    "private_env_injection_used": "foreground_env_injection_not_allowed",
    "stdin_injection_used": "stdin_injection_not_allowed",
    "raw_transcript_included": "raw_transcript_not_allowed",
    "raw_prompt_included": "raw_prompt_not_allowed",
    "raw_provider_material_included": "raw_provider_material_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "provider_state_db_material_included": "provider_state_db_material_not_allowed",
    "skill_body_included": "skill_body_not_allowed",
    "safe_provider_owned_gateway_evidence_claimed": (
        "safe_provider_owned_gateway_evidence_claim_not_allowed"
    ),
    "hermes_subagent_live_bridge_complete_claimed": (
        "hermes_subagent_live_bridge_complete_claim_not_allowed"
    ),
    "r10_live_pass_claimed": "r10_live_pass_claim_not_allowed",
    "r9_real_session_pass_claimed": "r9_real_session_pass_claim_not_allowed",
    "reasoning_lease_solved_claimed": "reasoning_lease_solved_claim_not_allowed",
    "live_readiness_claimed": "live_readiness_claim_not_allowed",
    "production_readiness_claimed": "production_readiness_claim_not_allowed",
    "public_runtime_integration_complete_claimed": (
        "public_runtime_integration_complete_claim_not_allowed"
    ),
    "background_live_integration_claimed": "background_live_integration_claim_not_allowed",
    "p4_h6_closed_claimed": "p4_h6_closed_claim_not_allowed",
    "hermes_answer_quality_claimed": "hermes_answer_quality_claim_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    "hermes_source_hard_coupled": False,
    "hermes_source_patch_used": False,
    "foreground_env_injection_used": False,
    "private_env_injection_used": False,
    "stdin_injection_used": False,
    "raw_transcript_included": False,
    "raw_prompt_included": False,
    "raw_provider_material_included": False,
    "provider_credential_profile_included": False,
    "provider_state_db_material_included": False,
    "skill_body_included": False,
    "safe_provider_owned_gateway_evidence_claimed": False,
    "hermes_subagent_live_bridge_complete_claimed": False,
    "r10_live_pass_claimed": False,
    "r9_real_session_pass_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "background_live_integration_claimed": False,
    "p4_h6_closed_claimed": False,
    "hermes_answer_quality_claimed": False,
}
BRIDGE_STATUSES = {
    "static_bridge_contract_ready",
    "typed_unavailable",
    "reject",
}
DEFAULT_E12B_SURFACE_REFS = {
    "persona_or_prompt_ref": "persona-ref://openyggdrasil/pathfinder/v1",
    "schema_ref": (
        "contract-ref://openyggdrasil/contracts/"
        "hermes_subagent_reasoning_lease_bridge.v1.schema.json"
    ),
    "runtime_enforcement_ref": (
        "runtime-module-ref://openyggdrasil/runtime/reasoning/"
        "hermes_subagent_reasoning_lease_bridge.py"
    ),
    "global_hard_nonclaims_ref": "persona-ref://openyggdrasil/common/v1",
}


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
        return "portable_local_path_not_allowed"
    if RAW_SKILL_BODY_RE.search(value) or ".skill.md" in value.lower():
        return "skill_body_not_allowed"
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


def _unique_refs(values: Sequence[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            refs.append(value)
            seen.add(value)
    return refs


def _output_ref(status: str, safe_refs: Mapping[str, str], field: str) -> str | None:
    if status == "reject":
        return None
    return safe_refs.get(field)


def validate_hermes_subagent_reasoning_lease_bridge(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "hermes_subagent_reasoning_lease_bridge.v1":
        raise ValueError("invalid Hermes subagent Reasoning Lease bridge schema_version")
    if payload.get("bridge_status") not in BRIDGE_STATUSES:
        raise ValueError("invalid Hermes subagent Reasoning Lease bridge status")
    if payload.get("runtime_owner") != "runtime/reasoning/hermes_subagent_reasoning_lease_bridge.py":
        raise ValueError("invalid Hermes subagent Reasoning Lease bridge runtime owner")
    if payload.get("transition_prep_only") is not True:
        raise ValueError("Hermes subagent bridge must remain transition-prep only")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("Hermes subagent bridge must use typed refs only")
    if payload.get("ptc_callable") is not True:
        raise ValueError("Hermes subagent bridge must remain PTC-callable")

    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe Hermes subagent bridge flag: {flag_name}")

    for field in ("bridge_ref", *REF_FIELDS):
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

    bridge_status = payload.get("bridge_status")
    if bridge_status == "static_bridge_contract_ready":
        if payload.get("provider") != "hermes":
            raise ValueError("Hermes subagent bridge provider must be hermes")
        for field in REQUIRED_STATIC_READY_REFS:
            if not payload.get(field):
                raise ValueError(f"static bridge ready requires {field}")
        if not payload.get("typed_task_id"):
            raise ValueError("static bridge ready requires typed_task_id")
        if not (payload.get("typed_result_ref") or payload.get("typed_unavailable_ref")):
            raise ValueError("static bridge ready requires typed result or unavailable ref")
        if not (payload.get("lease_budget_ref") or payload.get("lease_unavailable_reason")):
            raise ValueError("static bridge ready requires lease budget ref or unavailable reason")
        if payload.get("static_bridge_contract_only") is not True:
            raise ValueError("static bridge ready must remain static only")
    elif bridge_status == "typed_unavailable":
        if not payload.get("unavailable_condition"):
            raise ValueError("typed unavailable bridge requires unavailable_condition")
    elif bridge_status == "reject":
        if not payload.get("reject_condition"):
            raise ValueError("rejected bridge requires reject_condition")
        if not payload.get("safety_reject_reasons"):
            raise ValueError("rejected bridge requires safety_reject_reasons")

    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")


def build_hermes_subagent_reasoning_lease_bridge(
    *,
    bridge_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a static Hermes provider-skill -> Reasoning Lease bridge contract.

    This owner does not call Hermes, patch Hermes source, read provider state,
    or execute a Reasoning Lease. It only validates typed refs for a later
    provider-owned bridge proof.
    """

    if not isinstance(bridge_request, Mapping):
        request: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        request = dict(bridge_request)
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

    bridge_id = uuid.uuid4().hex
    provider = str(request.get("provider") or "hermes").strip().lower()
    typed_task_id = _safe_identifier(request.get("typed_task_id"))
    lease_depth_or_effort = _safe_identifier(request.get("lease_depth_or_effort"))
    lease_unavailable_reason = _safe_identifier(request.get("lease_unavailable_reason"))
    typed_result_or_unavailable = bool(
        safe_refs.get("typed_result_ref") or safe_refs.get("typed_unavailable_ref")
    )

    unavailable_condition: str | None = None
    reject_condition: str | None = None
    safety_reject_reasons: list[str] = []

    if unsupported_input_shape:
        bridge_status = "typed_unavailable"
        unavailable_condition = "unsupported_input_shape"
        reason_codes = ["unsupported_input_shape"]
    elif provider != "hermes":
        bridge_status = "typed_unavailable"
        unavailable_condition = "provider_hermes_required"
        reason_codes = ["provider_hermes_required"]
    elif reason_codes:
        bridge_status = "reject"
        reject_condition = "unsafe_static_bridge_material"
        safety_reject_reasons = _unique_refs(reason_codes)
    elif "provider_skill_ref" not in safe_refs:
        bridge_status = "typed_unavailable"
        unavailable_condition = "provider_skill_ref_absent"
        reason_codes = ["provider_skill_ref_absent"]
    elif "reasoning_lease_ref" not in safe_refs:
        bridge_status = "typed_unavailable"
        unavailable_condition = "reasoning_lease_ref_absent"
        reason_codes = ["reasoning_lease_ref_absent"]
    elif "provider_gateway_proof_ref" not in safe_refs:
        bridge_status = "typed_unavailable"
        unavailable_condition = "safe_gateway_proof_ref_absent"
        reason_codes = ["safe_gateway_proof_ref_absent"]
    else:
        missing_refs = _missing_ref_fields(REQUIRED_STATIC_READY_REFS, safe_refs)
        if typed_task_id is None:
            bridge_status = "typed_unavailable"
            unavailable_condition = "typed_task_id_absent"
            reason_codes = ["typed_task_id_absent"]
        elif not typed_result_or_unavailable:
            bridge_status = "typed_unavailable"
            unavailable_condition = "typed_result_or_unavailable_ref_absent"
            reason_codes = ["typed_result_or_unavailable_ref_absent"]
        elif lease_depth_or_effort is None:
            bridge_status = "typed_unavailable"
            unavailable_condition = "lease_depth_or_effort_absent"
            reason_codes = ["lease_depth_or_effort_absent"]
        elif "lease_budget_ref" not in safe_refs and lease_unavailable_reason is None:
            bridge_status = "typed_unavailable"
            unavailable_condition = "lease_budget_or_unavailable_reason_absent"
            reason_codes = ["lease_budget_or_unavailable_reason_absent"]
        elif missing_refs:
            bridge_status = "typed_unavailable"
            unavailable_condition = "static_bridge_refs_incomplete"
            reason_codes = [f"missing_ref:{field}" for field in missing_refs]
        else:
            bridge_status = "static_bridge_contract_ready"
            reason_codes = [
                "static_bridge_contract_ready",
                "provider_skill_ref_present",
                "persona_or_prompt_ref_present",
                "schema_ref_present",
                "runtime_enforcement_ref_present",
                "global_hard_nonclaims_ref_present",
                "reasoning_lease_ref_present",
                "typed_task_or_unavailable_shape_present",
                "context_window_refs_present",
                "producer_consumer_usage_refs_present",
            ]

    bridge_ref = (
        f"hermes-subagent-reasoning-lease-bridge-ref://openyggdrasil/r10/{bridge_id}"
        if bridge_status != "reject"
        else None
    )
    ref_values = [
        bridge_ref,
        *[_output_ref(bridge_status, safe_refs, field) for field in REF_FIELDS],
    ]
    safe_portable_refs = _unique_refs([ref for ref in ref_values if ref])

    payload = {
        "schema_version": "hermes_subagent_reasoning_lease_bridge.v1",
        "bridge_id": bridge_id,
        "bridge_ref": bridge_ref,
        "provider": provider if provider == "hermes" else None,
        "bridge_status": bridge_status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": reason_codes,
        "safety_reject_reasons": safety_reject_reasons,
        "provider_skill_ref": _output_ref(bridge_status, safe_refs, "provider_skill_ref"),
        "provider_subagent_surface_ref": _output_ref(
            bridge_status, safe_refs, "provider_subagent_surface_ref"
        ),
        "persona_or_prompt_ref": _output_ref(
            bridge_status, safe_refs, "persona_or_prompt_ref"
        ),
        "schema_ref": _output_ref(bridge_status, safe_refs, "schema_ref"),
        "runtime_enforcement_ref": _output_ref(
            bridge_status, safe_refs, "runtime_enforcement_ref"
        ),
        "global_hard_nonclaims_ref": _output_ref(
            bridge_status, safe_refs, "global_hard_nonclaims_ref"
        ),
        "reasoning_lease_ref": _output_ref(bridge_status, safe_refs, "reasoning_lease_ref"),
        "lease_depth_or_effort": lease_depth_or_effort if bridge_status != "reject" else None,
        "lease_budget_ref": _output_ref(bridge_status, safe_refs, "lease_budget_ref"),
        "lease_unavailable_reason": (
            lease_unavailable_reason if bridge_status != "reject" else None
        ),
        "ptc_or_subagent_boundary_ref": _output_ref(
            bridge_status, safe_refs, "ptc_or_subagent_boundary_ref"
        ),
        "provider_gateway_proof_ref": _output_ref(
            bridge_status, safe_refs, "provider_gateway_proof_ref"
        ),
        "typed_task_id": typed_task_id if bridge_status != "reject" else None,
        "typed_result_ref": _output_ref(bridge_status, safe_refs, "typed_result_ref"),
        "typed_unavailable_ref": _output_ref(bridge_status, safe_refs, "typed_unavailable_ref"),
        "before_main_context_window_ref": _output_ref(
            bridge_status, safe_refs, "before_main_context_window_ref"
        ),
        "after_main_context_window_ref": _output_ref(
            bridge_status, safe_refs, "after_main_context_window_ref"
        ),
        "producer_receipt_ref": _output_ref(bridge_status, safe_refs, "producer_receipt_ref"),
        "consumer_usage_ref": _output_ref(bridge_status, safe_refs, "consumer_usage_ref"),
        "safe_portable_refs": safe_portable_refs,
        "input_schema_versions": _as_string_list(request.get("input_schema_versions")),
        "ptc_callable": True,
        "runtime_owner": "runtime/reasoning/hermes_subagent_reasoning_lease_bridge.py",
        "transition_prep_only": True,
        "static_bridge_contract_only": True,
        "typed_refs_only": True,
        "hermes_source_hard_coupled": False,
        "hermes_source_patch_used": False,
        "foreground_env_injection_used": False,
        "private_env_injection_used": False,
        "stdin_injection_used": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "raw_provider_material_included": False,
        "provider_credential_profile_included": False,
        "provider_state_db_material_included": False,
        "skill_body_included": False,
        "safe_provider_owned_gateway_evidence_claimed": False,
        "hermes_subagent_live_bridge_complete_claimed": False,
        "r10_live_pass_claimed": False,
        "r9_real_session_pass_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "background_live_integration_claimed": False,
        "p4_h6_closed_claimed": False,
        "hermes_answer_quality_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_hermes_subagent_reasoning_lease_bridge(payload)
    return payload
