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
REF_FIELD_ALIASES = {
    "provider_gateway_evidence_ref": ("provider_gateway_evidence_ref",),
    "before_main_context_window_ref": ("before_main_context_window_ref",),
    "after_main_context_window_ref": ("after_main_context_window_ref",),
    "producer_usage_evidence_ref": ("producer_usage_evidence_ref",),
    "producer_request_ref": ("producer_request_ref",),
    "producer_receipt_ref": ("producer_receipt_ref", "production_receipt_ref"),
    "support_bundle_ref": ("support_bundle_ref",),
    "consumer_menu_ref": ("consumer_menu_ref",),
    "consumer_usage_ref": ("consumer_usage_ref", "consumer_usage_evidence_ref"),
    "typed_result_ref": ("typed_result_ref",),
    "typed_unavailable_ref": ("typed_unavailable_ref",),
}
COMMON_REF_FIELDS = (
    "provider_gateway_evidence_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
)
PRODUCER_REF_FIELDS = (
    "producer_usage_evidence_ref",
    "producer_request_ref",
    "producer_receipt_ref",
    "support_bundle_ref",
)
CONSUMER_REF_FIELDS = (
    "consumer_menu_ref",
    "consumer_usage_ref",
    "support_bundle_ref",
)
UNSAFE_KEY_REASON_CODES = {
    "raw_transcript": "raw_transcript_not_allowed",
    "raw_session_transcript": "raw_transcript_not_allowed",
    "transcript_text": "raw_transcript_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "provider_material": "raw_provider_material_not_allowed",
    "skill_body": "skill_body_not_allowed",
    "raw_skill_body": "skill_body_not_allowed",
    "provider_credential": "provider_credential_profile_not_allowed",
    "provider_profile": "provider_credential_profile_not_allowed",
    "credential_material": "provider_credential_profile_not_allowed",
    "profile_material": "provider_credential_profile_not_allowed",
    "stdin_injection": "stdin_injection_gateway_not_allowed",
    "mock_synthetic_smoke": "mock_synthetic_smoke_relabel_not_allowed",
    "synthetic_smoke_relabel": "mock_synthetic_smoke_relabel_not_allowed",
}
UNSAFE_TEXT_REASON_FRAGMENTS = (
    ("raw transcript", "raw_transcript_not_allowed"),
    ("session transcript", "raw_transcript_not_allowed"),
    ("provider credential", "provider_credential_profile_not_allowed"),
    ("provider profile", "provider_credential_profile_not_allowed"),
    ("credential:", "provider_credential_profile_not_allowed"),
    ("secret:", "provider_credential_profile_not_allowed"),
    ("api_key", "provider_credential_profile_not_allowed"),
    ("stdin injection", "stdin_injection_gateway_not_allowed"),
    ("mock/synthetic smoke", "mock_synthetic_smoke_relabel_not_allowed"),
)
UNSAFE_FLAG_REASON_CODES = {
    "raw_transcript_included": "raw_transcript_not_allowed",
    "raw_provider_material_included": "raw_provider_material_not_allowed",
    "skill_body_included": "skill_body_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "portable_local_path_included": "portable_local_path_not_allowed",
    "stdin_injection_used": "stdin_injection_gateway_not_allowed",
    "mock_synthetic_smoke_relabelled": "mock_synthetic_smoke_relabel_not_allowed",
    "mock_synthetic_smoke_relabelled_as_real_session": (
        "mock_synthetic_smoke_relabel_not_allowed"
    ),
    "real_session_pass_claimed": "r9_real_session_pass_claim_not_allowed",
    "r9_real_session_pass_claimed": "r9_real_session_pass_claim_not_allowed",
    "live_readiness_claimed": "live_readiness_claim_not_allowed",
    "production_readiness_claimed": "production_readiness_claim_not_allowed",
    "public_runtime_integration_complete_claimed": (
        "public_runtime_integration_complete_claim_not_allowed"
    ),
    "background_live_integration_claimed": "background_live_integration_claim_not_allowed",
    "reasoning_lease_solved_claimed": "reasoning_lease_solved_claim_not_allowed",
    "p4_closure_claimed": "p4_closure_claim_not_allowed",
    "p4_h1_closed_claimed": "p4_closure_claim_not_allowed",
    "p4_h2_closed_claimed": "p4_closure_claim_not_allowed",
    "p4_h3_closed_claimed": "p4_closure_claim_not_allowed",
    "p4_h6_closed_claimed": "p4_closure_claim_not_allowed",
    "hermes_answer_quality_claimed": "hermes_answer_quality_claim_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_included": False,
    "raw_provider_material_included": False,
    "skill_body_included": False,
    "provider_credential_profile_included": False,
    "portable_local_path_included": False,
    "stdin_injection_used": False,
    "mock_synthetic_smoke_relabelled": False,
    "r9_real_session_pass_claimed": False,
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "background_live_integration_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "p4_closure_claimed": False,
    "p4_h1_closed_claimed": False,
    "p4_h2_closed_claimed": False,
    "p4_h3_closed_claimed": False,
    "p4_h6_closed_claimed": False,
    "hermes_answer_quality_claimed": False,
}
PROOF_PACKAGE_STATUSES = {
    "pass_candidate",
    "partial_producer_candidate",
    "partial_consumer_candidate",
    "typed_unavailable",
    "reject",
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


def _raw_ref_value(request: Mapping[str, Any], canonical_field: str) -> Any:
    for field in REF_FIELD_ALIASES[canonical_field]:
        if request.get(field) is not None:
            return request.get(field)
    return None


def _safe_ref_from(request: Mapping[str, Any], canonical_field: str) -> str | None:
    value = _raw_ref_value(request, canonical_field)
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value if _is_safe_ref(string_value) else None


def _safe_refs_from_request(request: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: safe_ref
        for field in REF_FIELD_ALIASES
        if (safe_ref := _safe_ref_from(request, field)) is not None
    }


def _unsafe_ref_fields(request: Mapping[str, Any], safe_refs: Mapping[str, str]) -> list[str]:
    return [
        field
        for field in REF_FIELD_ALIASES
        if _raw_ref_value(request, field) is not None and field not in safe_refs
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


def _output_ref(
    status: str,
    reject_condition: str | None,
    safe_refs: Mapping[str, str],
    field: str,
) -> str | None:
    if status == "reject" and reject_condition is not None:
        return None
    return safe_refs.get(field)


def validate_hermes_real_session_usage_probe(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "hermes_real_session_usage_probe.v1":
        raise ValueError("invalid Hermes real-session usage probe schema_version")
    if payload.get("proof_package_status") not in PROOF_PACKAGE_STATUSES:
        raise ValueError("invalid Hermes real-session usage proof_package_status")
    if payload.get("ptc_callable") is not True:
        raise ValueError("Hermes real-session usage probe must remain PTC-callable")
    if payload.get("runtime_owner") != "runtime/reasoning/hermes_real_session_usage_probe.py":
        raise ValueError("invalid Hermes real-session usage probe runtime owner")
    if payload.get("transition_prep_only") is not True:
        raise ValueError("Hermes real-session usage probe must remain transition-prep only")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("Hermes real-session usage probe must use typed refs only")

    for flag_name in DEFAULT_SAFETY_FLAGS:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe Hermes real-session usage probe flag: {flag_name}")

    for field in [
        "probe_result_ref",
        *REF_FIELD_ALIASES.keys(),
    ]:
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"{field} must be a safe portable ref")

    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe portable refs")

    for reason_code in payload.get("reason_codes") or []:
        if not _is_safe_identifier(reason_code):
            raise ValueError("reason_codes must be safe identifiers")

    status = payload.get("proof_package_status")
    if status == "typed_unavailable" and not payload.get("unavailable_condition"):
        raise ValueError("typed_unavailable requires unavailable_condition")
    if status == "reject" and not payload.get("reject_condition"):
        raise ValueError("reject requires reject_condition")
    if status == "pass_candidate":
        for field in [
            *COMMON_REF_FIELDS,
            *PRODUCER_REF_FIELDS,
            "consumer_menu_ref",
            "consumer_usage_ref",
        ]:
            if not payload.get(field):
                raise ValueError(f"pass_candidate requires {field}")
        if payload.get("producer_side_usage_evidenced") is not True:
            raise ValueError("pass_candidate requires producer side evidence")
        if payload.get("consumer_side_usage_evidenced") is not True:
            raise ValueError("pass_candidate requires consumer side evidence")
    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")


def build_hermes_real_session_usage_probe(
    *,
    proof_package: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Validate a typed R9 real-session usage proof package candidate.

    This owner does not perform a live session, call a provider gateway, or
    close product gates. It only classifies typed, safe proof refs.
    """

    if not isinstance(proof_package, Mapping):
        request: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        request = dict(proof_package)
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

    probe_id = uuid.uuid4().hex
    session_probe_id = _safe_identifier(request.get("session_probe_id"))
    typed_task_id = _safe_identifier(request.get("typed_task_id"))
    typed_result_or_unavailable = bool(
        safe_refs.get("typed_result_ref") or safe_refs.get("typed_unavailable_ref")
    )
    unavailable_condition: str | None = None
    reject_condition: str | None = None

    if unsupported_input_shape:
        proof_package_status = "typed_unavailable"
        unavailable_condition = "unsupported_input_shape"
        reason_codes = ["unsupported_input_shape"]
    elif reason_codes:
        proof_package_status = "reject"
        reject_condition = "blocked_unsafe_or_overclaiming_proof_material"
    elif session_probe_id is None:
        proof_package_status = "typed_unavailable"
        unavailable_condition = "session_probe_id_required"
        reason_codes = ["session_probe_id_required"]
    elif typed_task_id is None:
        proof_package_status = "typed_unavailable"
        unavailable_condition = "typed_task_id_required"
        reason_codes = ["typed_task_id_required"]
    elif "provider_gateway_evidence_ref" not in safe_refs:
        proof_package_status = "typed_unavailable"
        unavailable_condition = "provider_owned_gateway_evidence_absent"
        reason_codes = ["provider_owned_gateway_evidence_absent"]
    elif missing_common := _missing_ref_fields(COMMON_REF_FIELDS, safe_refs):
        proof_package_status = "typed_unavailable"
        unavailable_condition = "missing_context_window_refs"
        reason_codes = [f"missing_ref:{field}" for field in missing_common]
    elif not typed_result_or_unavailable:
        proof_package_status = "typed_unavailable"
        unavailable_condition = "typed_result_or_unavailable_ref_required"
        reason_codes = ["typed_result_or_unavailable_ref_required"]
    else:
        producer_missing = _missing_ref_fields(PRODUCER_REF_FIELDS, safe_refs)
        consumer_missing = _missing_ref_fields(CONSUMER_REF_FIELDS, safe_refs)
        if not producer_missing and not consumer_missing:
            proof_package_status = "pass_candidate"
            reason_codes = [
                "r9_proof_package_pass_candidate",
                "producer_usage_refs_present",
                "consumer_usage_refs_present",
                "provider_gateway_ref_present",
                "no_overclaim_flags",
            ]
        elif not producer_missing:
            proof_package_status = "partial_producer_candidate"
            reason_codes = [
                "partial_producer_usage_candidate",
                *[f"missing_ref:{field}" for field in consumer_missing],
            ]
        elif not consumer_missing:
            proof_package_status = "partial_consumer_candidate"
            reason_codes = [
                "partial_consumer_usage_candidate",
                *[f"missing_ref:{field}" for field in producer_missing],
            ]
        else:
            proof_package_status = "typed_unavailable"
            unavailable_condition = "producer_and_consumer_usage_refs_incomplete"
            reason_codes = [
                *[f"missing_ref:{field}" for field in producer_missing],
                *[f"missing_ref:{field}" for field in consumer_missing],
            ]

    producer_side_usage_evidenced = proof_package_status in {
        "pass_candidate",
        "partial_producer_candidate",
    }
    consumer_side_usage_evidenced = proof_package_status in {
        "pass_candidate",
        "partial_consumer_candidate",
    }
    probe_result_ref = (
        f"hermes-real-session-usage-probe-ref://openyggdrasil/r9/{probe_id}"
        if proof_package_status != "reject"
        else None
    )

    ref_values = [
        probe_result_ref,
        *[
            _output_ref(proof_package_status, reject_condition, safe_refs, field)
            for field in REF_FIELD_ALIASES
        ],
    ]
    safe_portable_refs = _unique_refs([ref for ref in ref_values if ref])

    payload = {
        "schema_version": "hermes_real_session_usage_probe.v1",
        "probe_id": probe_id,
        "session_probe_id": session_probe_id,
        "typed_task_id": typed_task_id,
        "proof_package_status": proof_package_status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": reason_codes,
        "provider_gateway_evidence_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "provider_gateway_evidence_ref"
        ),
        "before_main_context_window_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "before_main_context_window_ref"
        ),
        "after_main_context_window_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "after_main_context_window_ref"
        ),
        "producer_usage_evidence_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "producer_usage_evidence_ref"
        ),
        "producer_request_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "producer_request_ref"
        ),
        "producer_receipt_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "producer_receipt_ref"
        ),
        "support_bundle_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "support_bundle_ref"
        ),
        "consumer_menu_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "consumer_menu_ref"
        ),
        "consumer_usage_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "consumer_usage_ref"
        ),
        "typed_result_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "typed_result_ref"
        ),
        "typed_unavailable_ref": _output_ref(
            proof_package_status, reject_condition, safe_refs, "typed_unavailable_ref"
        ),
        "probe_result_ref": probe_result_ref,
        "safe_portable_refs": safe_portable_refs,
        "input_schema_versions": _as_string_list(request.get("input_schema_versions")),
        "ptc_callable": True,
        "runtime_owner": "runtime/reasoning/hermes_real_session_usage_probe.py",
        "transition_prep_only": True,
        "typed_refs_only": True,
        "provider_owned_gateway_evidence_present": (
            proof_package_status != "reject"
            and safe_refs.get("provider_gateway_evidence_ref") is not None
        ),
        "typed_task_id_returned": typed_task_id is not None,
        "typed_result_or_unavailable_returned": typed_result_or_unavailable,
        "producer_side_usage_evidenced": producer_side_usage_evidenced,
        "consumer_side_usage_evidenced": consumer_side_usage_evidenced,
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        "stdin_injection_used": False,
        "mock_synthetic_smoke_relabelled": False,
        "r9_real_session_pass_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "background_live_integration_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "p4_closure_claimed": False,
        "p4_h1_closed_claimed": False,
        "p4_h2_closed_claimed": False,
        "p4_h3_closed_claimed": False,
        "p4_h6_closed_claimed": False,
        "hermes_answer_quality_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_hermes_real_session_usage_probe(payload)
    return payload
