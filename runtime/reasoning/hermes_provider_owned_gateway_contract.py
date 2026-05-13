from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
LOCAL_PATH_RE = re.compile(r"(^[A-Za-z]:|\\\\|/Users/|/home/|/tmp/|file://)", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UNSAFE_REF_FRAGMENTS = (
    ".env",
    ".skill.md",
    "auth.json",
    "credential",
    "local-private-workspace",
    "profile",
    "prompt",
    "state-db",
    "state_db",
    "transcript",
)
REF_FIELDS = (
    "gateway_owner_ref",
    "provider_gateway_surface_ref",
    "provider_gateway_capability_ref",
    "provider_gateway_contract_ref",
    "gateway_request_ref",
    "provider_gateway_evidence_ref",
    "provider_gateway_proof_ref",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "producer_request_ref",
    "producer_receipt_ref",
    "support_bundle_ref",
    "consumer_menu_ref",
    "consumer_usage_ref",
    "provider_skill_ref",
    "provider_subagent_surface_ref",
    "reasoning_lease_ref",
    "ptc_or_subagent_boundary_ref",
    "lease_budget_ref",
)
CORE_READY_REFS = (
    "gateway_owner_ref",
    "provider_gateway_surface_ref",
    "provider_gateway_capability_ref",
    "provider_gateway_contract_ref",
    "gateway_request_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
)
PRODUCER_READY_REFS = (
    "producer_request_ref",
    "producer_receipt_ref",
)
CONSUMER_READY_REFS = (
    "consumer_usage_ref",
)
SUBAGENT_READY_REFS = (
    "provider_skill_ref",
    "provider_subagent_surface_ref",
    "reasoning_lease_ref",
    "ptc_or_subagent_boundary_ref",
)
GATEWAY_OWNER_TYPES = {"app_assigned_gateway", "provider_owned_gateway"}
INVOCATION_SURFACES = {
    "app_assigned_command",
    "provider_command",
    "provider_subagent_delegate",
    "provider_skill_entrypoint",
}
GATEWAY_CAPABILITIES = {
    "command_gateway",
    "subagent_gateway",
    "provider_skill_gateway",
}
GATEWAY_STATUSES = {
    "static_contract_ready",
    "typed_unavailable",
    "reject",
}
UNSAFE_KEY_REASON_CODES = {
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
    "local_provider_path_material": "local_provider_path_material_not_allowed",
    "hermes_source_patch": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_hard_coupling": "hermes_source_hard_coupling_not_allowed",
    "patched_hermes_source": "hermes_source_hard_coupling_not_allowed",
    "mock_synthetic_proof": "mock_synthetic_live_relabel_not_allowed",
    "mock_synthetic_smoke": "mock_synthetic_live_relabel_not_allowed",
    "setup_report_as_typed_proof": "setup_report_as_typed_proof_not_allowed",
    "setup_report_treated_as_typed_proof": "setup_report_as_typed_proof_not_allowed",
    "raw_provider_task_output": "raw_provider_task_output_capture_not_allowed",
}
UNSAFE_TEXT_REASON_FRAGMENTS = (
    ("foreground .env injection", "foreground_env_injection_not_allowed"),
    (".env injection", "foreground_env_injection_not_allowed"),
    ("local-private-workspace", "local_provider_path_material_not_allowed"),
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
    ("state.db", "provider_state_db_material_not_allowed"),
    ("hermes source patch", "hermes_source_hard_coupling_not_allowed"),
    ("patched hermes source", "hermes_source_hard_coupling_not_allowed"),
    ("mock relabeled live", "mock_synthetic_live_relabel_not_allowed"),
    ("mock/synthetic", "mock_synthetic_live_relabel_not_allowed"),
    ("setup report", "setup_report_as_typed_proof_not_allowed"),
    ("raw provider task output", "raw_provider_task_output_capture_not_allowed"),
)
UNSAFE_FLAG_REASON_CODES = {
    "foreground_env_injection_used": "foreground_env_injection_not_allowed",
    "private_env_injection_used": "foreground_env_injection_not_allowed",
    "stdin_injection_used": "stdin_injection_not_allowed",
    "raw_transcript_included": "raw_transcript_not_allowed",
    "raw_prompt_included": "raw_prompt_not_allowed",
    "raw_provider_material_included": "raw_provider_material_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "provider_state_db_material_included": "provider_state_db_material_not_allowed",
    "local_provider_path_material_included": "local_provider_path_material_not_allowed",
    "hermes_source_hard_coupled": "hermes_source_hard_coupling_not_allowed",
    "hermes_source_patch_used": "hermes_source_hard_coupling_not_allowed",
    "mock_synthetic_proof_relabelled_live": "mock_synthetic_live_relabel_not_allowed",
    "setup_report_treated_as_typed_proof": "setup_report_as_typed_proof_not_allowed",
    "raw_provider_task_output_payload_captured": "raw_provider_task_output_capture_not_allowed",
    "safe_gateway_pass_claimed": "safe_gateway_pass_claim_not_allowed",
    "hermes_subagent_live_bridge_complete_claimed": (
        "hermes_subagent_live_bridge_complete_claim_not_allowed"
    ),
    "r9_real_session_pass_claimed": "r9_real_session_pass_claim_not_allowed",
    "r10_live_pass_claimed": "r10_live_pass_claim_not_allowed",
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
    flag_name: False for flag_name in UNSAFE_FLAG_REASON_CODES
}


@lru_cache(maxsize=1)
def load_p0_provider_owned_hermes_gateway_contract_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "p0_provider_owned_hermes_gateway_contract.v1.schema.json").read_text(
            encoding="utf-8"
        )
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
        return "local_provider_path_material_not_allowed"
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
    return {
        field: safe_ref
        for field in REF_FIELDS
        if (safe_ref := _safe_ref_from(request, field)) is not None
    }


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


def _missing_consumer_refs(safe_refs: Mapping[str, str]) -> list[str]:
    missing = _missing_ref_fields(CONSUMER_READY_REFS, safe_refs)
    if "support_bundle_ref" not in safe_refs and "consumer_menu_ref" not in safe_refs:
        missing.append("support_bundle_ref_or_consumer_menu_ref")
    return missing


def validate_p0_provider_owned_hermes_gateway_contract(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_p0_provider_owned_hermes_gateway_contract_schema(),
    )

    if payload.get("schema_version") != "p0_provider_owned_hermes_gateway_contract.v1":
        raise ValueError("invalid P0 provider-owned Hermes gateway contract schema_version")
    if payload.get("gateway_status") not in GATEWAY_STATUSES:
        raise ValueError("invalid P0 provider-owned Hermes gateway status")
    if payload.get("provider") not in {"hermes", None}:
        raise ValueError("P0 provider-owned gateway provider must be hermes")
    if payload.get("runtime_owner") != "runtime/reasoning/hermes_provider_owned_gateway_contract.py":
        raise ValueError("invalid P0 provider-owned gateway runtime owner")
    if payload.get("static_contract_only") is not True:
        raise ValueError("P0 provider-owned gateway contract must remain static only")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("P0 provider-owned gateway contract must use typed refs only")

    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe P0 provider-owned gateway flag: {flag_name}")

    for field in ("contract_ref", *REF_FIELDS):
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

    status = payload.get("gateway_status")
    if status == "static_contract_ready":
        if payload.get("provider") != "hermes":
            raise ValueError("static contract ready requires provider hermes")
        if payload.get("gateway_owner_type") not in GATEWAY_OWNER_TYPES:
            raise ValueError("static contract ready requires provider-owned gateway owner type")
        if payload.get("invocation_surface") not in INVOCATION_SURFACES:
            raise ValueError("static contract ready requires provider-declared invocation surface")
        if payload.get("gateway_capability") not in GATEWAY_CAPABILITIES:
            raise ValueError("static contract ready requires gateway capability")
        for field in CORE_READY_REFS:
            if not payload.get(field):
                raise ValueError(f"static contract ready requires {field}")
        if not payload.get("typed_task_id"):
            raise ValueError("static contract ready requires typed_task_id")
        if not (payload.get("typed_result_ref") or payload.get("typed_unavailable_ref")):
            raise ValueError("static contract ready requires typed result or unavailable ref")
        if not (payload.get("provider_gateway_evidence_ref") or payload.get("provider_gateway_proof_ref")):
            raise ValueError("static contract ready requires gateway evidence or proof ref")
        if payload.get("producer_usage_claimed") is True:
            for field in PRODUCER_READY_REFS:
                if not payload.get(field):
                    raise ValueError(f"producer usage claim requires {field}")
        if payload.get("consumer_usage_claimed") is True:
            for field in CONSUMER_READY_REFS:
                if not payload.get(field):
                    raise ValueError(f"consumer usage claim requires {field}")
            if not (payload.get("support_bundle_ref") or payload.get("consumer_menu_ref")):
                raise ValueError("consumer usage claim requires support bundle or menu ref")
        if payload.get("subagent_or_provider_skill_claimed") is True:
            for field in SUBAGENT_READY_REFS:
                if not payload.get(field):
                    raise ValueError(f"subagent/provider skill claim requires {field}")
            if not (payload.get("lease_budget_ref") or payload.get("lease_unavailable_reason")):
                raise ValueError("subagent/provider skill claim requires lease budget ref or unavailable reason")
    elif status == "typed_unavailable":
        if not payload.get("unavailable_condition"):
            raise ValueError("typed unavailable requires unavailable_condition")
        if not payload.get("typed_unavailable_ref"):
            raise ValueError("typed unavailable requires typed_unavailable_ref")
    elif status == "reject":
        if not payload.get("reject_condition"):
            raise ValueError("reject requires reject_condition")
        if not payload.get("safety_reject_reasons"):
            raise ValueError("reject requires safety_reject_reasons")

    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")


def build_p0_provider_owned_hermes_gateway_contract(
    *,
    gateway_proof: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build and validate the static P0 provider-owned Hermes gateway proof shape.

    This does not call Hermes, patch Hermes source, read provider state, or
    prove a live gateway. It only classifies a future gateway proof package
    candidate using safe refs and fail-closed rules.
    """

    if not isinstance(gateway_proof, Mapping):
        request: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        request = dict(gateway_proof)
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

    contract_id = uuid.uuid4().hex
    provider = str(request.get("provider") or "hermes").strip().lower()
    gateway_owner_type = request.get("gateway_owner_type")
    invocation_surface = str(request.get("invocation_surface") or "none").strip()
    gateway_capability = request.get("gateway_capability")
    typed_task_id = _safe_identifier(request.get("typed_task_id"))
    session_probe_id = _safe_identifier(request.get("session_probe_id"))
    lease_unavailable_reason = _safe_identifier(request.get("lease_unavailable_reason"))
    producer_usage_claimed = bool(request.get("producer_usage_claimed"))
    consumer_usage_claimed = bool(request.get("consumer_usage_claimed"))
    subagent_or_provider_skill_claimed = bool(request.get("subagent_or_provider_skill_claimed"))

    unavailable_condition: str | None = None
    reject_condition: str | None = None
    safety_reject_reasons: list[str] = []

    if unsupported_input_shape:
        gateway_status = "typed_unavailable"
        unavailable_condition = "unsupported_input_shape"
        reason_codes = ["unsupported_input_shape"]
    elif provider != "hermes":
        gateway_status = "typed_unavailable"
        unavailable_condition = "provider_hermes_required"
        reason_codes = ["provider_hermes_required"]
    elif reason_codes:
        gateway_status = "reject"
        reject_condition = "unsafe_gateway_contract_material"
        safety_reject_reasons = _unique_refs(reason_codes)
    elif gateway_owner_type not in GATEWAY_OWNER_TYPES:
        gateway_status = "typed_unavailable"
        unavailable_condition = "provider_gateway_owner_type_absent"
        reason_codes = ["provider_gateway_owner_type_absent"]
    elif invocation_surface not in INVOCATION_SURFACES:
        gateway_status = "typed_unavailable"
        unavailable_condition = "provider_invocation_surface_absent"
        reason_codes = ["provider_invocation_surface_absent"]
    elif gateway_capability not in GATEWAY_CAPABILITIES:
        gateway_status = "typed_unavailable"
        unavailable_condition = "gateway_capability_absent"
        reason_codes = ["gateway_capability_absent"]
    elif typed_task_id is None:
        gateway_status = "typed_unavailable"
        unavailable_condition = "typed_task_id_absent"
        reason_codes = ["typed_task_id_absent"]
    elif not (safe_refs.get("typed_result_ref") or safe_refs.get("typed_unavailable_ref")):
        gateway_status = "typed_unavailable"
        unavailable_condition = "typed_result_or_unavailable_ref_absent"
        reason_codes = ["typed_result_or_unavailable_ref_absent"]
    elif not (safe_refs.get("provider_gateway_evidence_ref") or safe_refs.get("provider_gateway_proof_ref")):
        gateway_status = "typed_unavailable"
        unavailable_condition = "gateway_evidence_or_proof_ref_absent"
        reason_codes = ["gateway_evidence_or_proof_ref_absent"]
    else:
        missing_refs = _missing_ref_fields(CORE_READY_REFS, safe_refs)
        if missing_refs:
            gateway_status = "typed_unavailable"
            unavailable_condition = "core_gateway_refs_incomplete"
            reason_codes = [f"missing_ref:{field}" for field in missing_refs]
        elif producer_usage_claimed and (
            missing_producer_refs := _missing_ref_fields(PRODUCER_READY_REFS, safe_refs)
        ):
            gateway_status = "typed_unavailable"
            unavailable_condition = "producer_usage_refs_incomplete"
            reason_codes = [f"missing_ref:{field}" for field in missing_producer_refs]
        elif consumer_usage_claimed and (missing_consumer_refs := _missing_consumer_refs(safe_refs)):
            gateway_status = "typed_unavailable"
            unavailable_condition = "consumer_usage_refs_incomplete"
            reason_codes = [f"missing_ref:{field}" for field in missing_consumer_refs]
        elif subagent_or_provider_skill_claimed and (
            missing_subagent_refs := _missing_ref_fields(SUBAGENT_READY_REFS, safe_refs)
        ):
            gateway_status = "typed_unavailable"
            unavailable_condition = "subagent_provider_skill_refs_incomplete"
            reason_codes = [f"missing_ref:{field}" for field in missing_subagent_refs]
        elif subagent_or_provider_skill_claimed and not (
            safe_refs.get("lease_budget_ref") or lease_unavailable_reason
        ):
            gateway_status = "typed_unavailable"
            unavailable_condition = "lease_budget_or_unavailable_reason_absent"
            reason_codes = ["lease_budget_or_unavailable_reason_absent"]
        else:
            gateway_status = "static_contract_ready"
            reason_codes = [
                "static_contract_ready",
                "provider_gateway_owner_boundary_present",
                "provider_declared_invocation_surface_present",
                "typed_task_or_unavailable_shape_present",
                "context_window_refs_present",
            ]
            if producer_usage_claimed:
                reason_codes.append("producer_usage_refs_present")
            if consumer_usage_claimed:
                reason_codes.append("consumer_usage_refs_present")
            if subagent_or_provider_skill_claimed:
                reason_codes.append("provider_skill_or_subagent_refs_present")

    contract_ref = (
        f"p0-provider-owned-hermes-gateway-contract-ref://openyggdrasil/p0-g2/{contract_id}"
        if gateway_status != "reject"
        else None
    )
    typed_unavailable_ref = _output_ref(gateway_status, safe_refs, "typed_unavailable_ref")
    if gateway_status == "typed_unavailable" and typed_unavailable_ref is None:
        typed_unavailable_ref = (
            f"typed-unavailable-ref://openyggdrasil/p0-g2/{contract_id}"
        )

    ref_values = [
        contract_ref,
        *[_output_ref(gateway_status, safe_refs, field) for field in REF_FIELDS],
        typed_unavailable_ref,
    ]
    safe_portable_refs = _unique_refs([ref for ref in ref_values if ref])

    payload = {
        "schema_version": "p0_provider_owned_hermes_gateway_contract.v1",
        "contract_id": contract_id,
        "contract_ref": contract_ref,
        "provider": provider if provider == "hermes" else None,
        "gateway_status": gateway_status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": _unique_refs(reason_codes),
        "safety_reject_reasons": safety_reject_reasons,
        "gateway_owner_type": gateway_owner_type if gateway_owner_type in GATEWAY_OWNER_TYPES else None,
        "gateway_owner_ref": _output_ref(gateway_status, safe_refs, "gateway_owner_ref"),
        "invocation_surface": invocation_surface if invocation_surface in INVOCATION_SURFACES else "none",
        "gateway_capability": gateway_capability if gateway_capability in GATEWAY_CAPABILITIES else None,
        "provider_gateway_surface_ref": _output_ref(
            gateway_status, safe_refs, "provider_gateway_surface_ref"
        ),
        "provider_gateway_capability_ref": _output_ref(
            gateway_status, safe_refs, "provider_gateway_capability_ref"
        ),
        "provider_gateway_contract_ref": _output_ref(
            gateway_status, safe_refs, "provider_gateway_contract_ref"
        ),
        "gateway_request_ref": _output_ref(gateway_status, safe_refs, "gateway_request_ref"),
        "session_probe_id": session_probe_id if gateway_status != "reject" else None,
        "typed_task_id": typed_task_id if gateway_status != "reject" else None,
        "typed_result_ref": _output_ref(gateway_status, safe_refs, "typed_result_ref"),
        "typed_unavailable_ref": typed_unavailable_ref,
        "before_main_context_window_ref": _output_ref(
            gateway_status, safe_refs, "before_main_context_window_ref"
        ),
        "after_main_context_window_ref": _output_ref(
            gateway_status, safe_refs, "after_main_context_window_ref"
        ),
        "provider_gateway_evidence_ref": _output_ref(
            gateway_status, safe_refs, "provider_gateway_evidence_ref"
        ),
        "provider_gateway_proof_ref": _output_ref(
            gateway_status, safe_refs, "provider_gateway_proof_ref"
        ),
        "producer_usage_claimed": producer_usage_claimed if gateway_status != "reject" else False,
        "producer_request_ref": _output_ref(gateway_status, safe_refs, "producer_request_ref"),
        "producer_receipt_ref": _output_ref(gateway_status, safe_refs, "producer_receipt_ref"),
        "consumer_usage_claimed": consumer_usage_claimed if gateway_status != "reject" else False,
        "support_bundle_ref": _output_ref(gateway_status, safe_refs, "support_bundle_ref"),
        "consumer_menu_ref": _output_ref(gateway_status, safe_refs, "consumer_menu_ref"),
        "consumer_usage_ref": _output_ref(gateway_status, safe_refs, "consumer_usage_ref"),
        "subagent_or_provider_skill_claimed": (
            subagent_or_provider_skill_claimed if gateway_status != "reject" else False
        ),
        "provider_skill_ref": _output_ref(gateway_status, safe_refs, "provider_skill_ref"),
        "provider_subagent_surface_ref": _output_ref(
            gateway_status, safe_refs, "provider_subagent_surface_ref"
        ),
        "reasoning_lease_ref": _output_ref(gateway_status, safe_refs, "reasoning_lease_ref"),
        "ptc_or_subagent_boundary_ref": _output_ref(
            gateway_status, safe_refs, "ptc_or_subagent_boundary_ref"
        ),
        "lease_budget_ref": _output_ref(gateway_status, safe_refs, "lease_budget_ref"),
        "lease_unavailable_reason": lease_unavailable_reason if gateway_status != "reject" else None,
        "safe_portable_refs": safe_portable_refs,
        "input_schema_versions": _as_string_list(request.get("input_schema_versions")),
        "ptc_callable": True,
        "runtime_owner": "runtime/reasoning/hermes_provider_owned_gateway_contract.py",
        "static_contract_only": True,
        "typed_refs_only": True,
        "foreground_env_injection_used": False,
        "private_env_injection_used": False,
        "stdin_injection_used": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "raw_provider_material_included": False,
        "provider_credential_profile_included": False,
        "provider_state_db_material_included": False,
        "local_provider_path_material_included": False,
        "hermes_source_hard_coupled": False,
        "hermes_source_patch_used": False,
        "mock_synthetic_proof_relabelled_live": False,
        "setup_report_treated_as_typed_proof": False,
        "raw_provider_task_output_payload_captured": False,
        "safe_gateway_pass_claimed": False,
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
    validate_p0_provider_owned_hermes_gateway_contract(payload)
    return payload
