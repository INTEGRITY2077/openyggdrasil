from __future__ import annotations

import re
import uuid
from typing import Any, Mapping, Sequence

from runtime.common.portable_ref import looks_like_local_path
from harness_common import utc_now_iso


SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RAW_SKILL_BODY_RE = re.compile(r"(?s)^---\s*\n.*\bname\s*:")
UNSAFE_REF_FRAGMENTS = (
    ".skill.md",
    "credential",
    "transcript",
)
REQUIRED_REF_FIELDS = (
    "producer_request_ref",
    "production_receipt_ref",
    "support_bundle_ref",
    "consumer_menu_ref",
)
OPTIONAL_REF_FIELDS = (
    "tree_ring_snapshot_ref",
    "skill_metadata_ref",
    "provider_receipt_consumer_ref",
)
UNSAFE_KEY_REASON_CODES = {
    "raw_transcript": "raw_transcript_not_allowed",
    "raw_session_transcript": "raw_transcript_not_allowed",
    "transcript_text": "raw_transcript_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "provider_material": "raw_provider_material_not_allowed",
    "skill_body": "skill_body_not_allowed",
    "raw_skill_body": "raw_skill_body_not_allowed",
    "provider_credential": "provider_credential_profile_not_allowed",
    "provider_profile": "provider_credential_profile_not_allowed",
    "credential_material": "provider_credential_profile_not_allowed",
    "profile_material": "provider_credential_profile_not_allowed",
}
UNSAFE_TEXT_REASON_FRAGMENTS = (
    ("raw transcript", "raw_transcript_not_allowed"),
    ("session transcript", "raw_transcript_not_allowed"),
    ("provider credential", "provider_credential_profile_not_allowed"),
    ("provider profile", "provider_credential_profile_not_allowed"),
    ("credential:", "provider_credential_profile_not_allowed"),
    ("secret:", "provider_credential_profile_not_allowed"),
    ("api_key", "provider_credential_profile_not_allowed"),
)
UNSAFE_FLAG_REASON_CODES = {
    "raw_transcript_included": "raw_transcript_not_allowed",
    "raw_provider_material_included": "raw_provider_material_not_allowed",
    "skill_body_included": "skill_body_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "portable_local_path_included": "portable_local_path_not_allowed",
    "consumer_ux_completion_claimed": "consumer_ux_completion_claim_not_allowed",
    "public_runtime_integration_complete_claimed": (
        "public_runtime_integration_complete_claim_not_allowed"
    ),
    "production_readiness_claimed": "production_readiness_claim_not_allowed",
    "live_readiness_claimed": "live_readiness_claim_not_allowed",
    "reasoning_lease_solved_claimed": "reasoning_lease_solved_claim_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_included": False,
    "raw_provider_material_included": False,
    "skill_body_included": False,
    "provider_credential_profile_included": False,
    "portable_local_path_included": False,
    "consumer_ux_completion_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "production_readiness_claimed": False,
    "live_readiness_claimed": False,
    "reasoning_lease_solved_claimed": False,
}
EDGE_KINDS = (
    "producer_request_to_receipt",
    "receipt_to_support_bundle",
    "support_bundle_to_consumer_menu",
)


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _unique_refs(values: Sequence[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            refs.append(value)
            seen.add(value)
    return refs


def _safe_identifier(value: Any, fallback: str) -> str:
    string_value = str(value or "").strip()
    if IDENTIFIER_RE.match(string_value):
        return string_value
    return fallback


def _unsafe_text_reason(value: str) -> str | None:
    if looks_like_local_path(value):
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


def _safe_ref_from(request: Mapping[str, Any], key: str) -> str | None:
    value = request.get(key)
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value if _is_safe_ref(string_value) else None


def _safe_refs_from_request(request: Mapping[str, Any], fields: Sequence[str]) -> dict[str, str]:
    return {
        field: safe_ref
        for field in fields
        if (safe_ref := _safe_ref_from(request, field)) is not None
    }


def _missing_ref_fields(safe_refs: Mapping[str, str]) -> list[str]:
    return [field for field in REQUIRED_REF_FIELDS if field not in safe_refs]


def _unsafe_ref_fields(request: Mapping[str, Any], safe_refs: Mapping[str, str]) -> list[str]:
    ref_fields = (*REQUIRED_REF_FIELDS, *OPTIONAL_REF_FIELDS)
    return [
        field
        for field in ref_fields
        if request.get(field) is not None and field not in safe_refs
    ]


def _build_edges(refs: Mapping[str, str]) -> list[dict[str, str]]:
    return [
        {
            "edge_kind": EDGE_KINDS[0],
            "from_ref": refs["producer_request_ref"],
            "to_ref": refs["production_receipt_ref"],
            "reason_code": "producer_request_has_receipt",
        },
        {
            "edge_kind": EDGE_KINDS[1],
            "from_ref": refs["production_receipt_ref"],
            "to_ref": refs["support_bundle_ref"],
            "reason_code": "receipt_has_support_bundle",
        },
        {
            "edge_kind": EDGE_KINDS[2],
            "from_ref": refs["support_bundle_ref"],
            "to_ref": refs["consumer_menu_ref"],
            "reason_code": "support_bundle_has_consumer_menu",
        },
    ]


def validate_producer_consumer_smoke(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "producer_consumer_smoke.v1":
        raise ValueError("invalid producer consumer smoke schema_version")
    if payload.get("smoke_status") not in {"smoke_built", "typed_unavailable"}:
        raise ValueError("invalid producer consumer smoke status")
    if payload.get("ptc_callable") is not True:
        raise ValueError("producer consumer smoke must remain PTC-callable")
    if payload.get("runtime_owner") != "runtime/pipeline/producer_consumer_smoke.py":
        raise ValueError("invalid producer consumer smoke runtime owner")
    if payload.get("transition_prep_only") is not True:
        raise ValueError("producer consumer smoke must remain transition-prep only")
    if payload.get("typed_refs_only") is not True:
        raise ValueError("producer consumer smoke must use typed refs only")

    for flag_name in [
        "raw_transcript_included",
        "raw_provider_material_included",
        "skill_body_included",
        "provider_credential_profile_included",
        "portable_local_path_included",
        "consumer_ux_completion_claimed",
        "public_runtime_integration_complete_claimed",
        "production_readiness_claimed",
        "live_readiness_claimed",
        "reasoning_lease_solved_claimed",
    ]:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe producer consumer smoke flag: {flag_name}")

    for field in (*REQUIRED_REF_FIELDS, *OPTIONAL_REF_FIELDS, "smoke_ref"):
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"{field} must be a safe portable ref")
    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe portable refs")
    for edge in payload.get("smoke_edges") or []:
        if not isinstance(edge, Mapping):
            raise ValueError("smoke_edges must contain objects")
        if edge.get("edge_kind") not in EDGE_KINDS:
            raise ValueError("unsupported smoke edge kind")
        for field in ["from_ref", "to_ref"]:
            if not _is_safe_ref(str(edge.get(field) or "")):
                raise ValueError("smoke edge refs must be safe portable refs")
        if not IDENTIFIER_RE.match(str(edge.get("reason_code") or "")):
            raise ValueError("smoke edge reason_code must be a safe identifier")

    if payload.get("smoke_status") == "smoke_built":
        for field in REQUIRED_REF_FIELDS:
            if not payload.get(field):
                raise ValueError(f"smoke_built requires {field}")
        if len(payload.get("smoke_edges") or []) != 3:
            raise ValueError("smoke_built requires producer receipt consumer edges")
    elif not payload.get("unavailable_condition"):
        raise ValueError("typed_unavailable requires unavailable_condition")
    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")


def build_producer_consumer_smoke(
    *,
    smoke_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a transition-prep producer -> receipt -> consumer smoke payload.

    The owner composes typed refs only. It does not read provider state, call a
    live provider, load memory, or claim consumer UX / production readiness.
    """

    if not isinstance(smoke_request, Mapping):
        request: Mapping[str, Any] = {}
        unsupported_input_shape = True
    else:
        request = dict(smoke_request)
        unsupported_input_shape = False

    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(request.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in request})

    reason_codes = _unsafe_flag_reason_codes(flags)
    unavailable_condition: str | None = None

    unsafe_material_reason = _unsafe_material_reason(request)
    if unsafe_material_reason is not None:
        reason_codes.append(unsafe_material_reason)

    ref_fields = (*REQUIRED_REF_FIELDS, *OPTIONAL_REF_FIELDS)
    safe_refs = _safe_refs_from_request(request, ref_fields)
    missing_ref_fields = _missing_ref_fields(safe_refs)
    unsafe_ref_fields = _unsafe_ref_fields(request, safe_refs)

    if unsupported_input_shape:
        unavailable_condition = "unsupported_input_shape"
        reason_codes = ["unsupported_input_shape"]
    elif reason_codes:
        unavailable_condition = "blocked_unsafe_input"
    elif unsafe_ref_fields:
        unavailable_condition = "unsafe_refs"
        reason_codes = [f"unsafe_ref:{field}" for field in unsafe_ref_fields]
    elif missing_ref_fields:
        unavailable_condition = "missing_required_refs"
        reason_codes = [f"missing_ref:{field}" for field in missing_ref_fields]

    smoke_status = "smoke_built" if unavailable_condition is None else "typed_unavailable"
    smoke_id = uuid.uuid4().hex
    smoke_ref = (
        f"producer-consumer-smoke-ref://openyggdrasil/track5/{smoke_id}"
        if smoke_status == "smoke_built"
        else None
    )
    smoke_edges = _build_edges(safe_refs) if smoke_status == "smoke_built" else []

    if smoke_status == "smoke_built":
        reason_codes = [
            "producer_consumer_smoke_built",
            "typed_transition_prep_refs_only",
            "safe_refs_only",
        ]

    safe_portable_refs = _unique_refs(
        [
            ref
            for ref in [
                smoke_ref,
                *[safe_refs[field] for field in ref_fields if field in safe_refs],
                *[edge["from_ref"] for edge in smoke_edges],
                *[edge["to_ref"] for edge in smoke_edges],
            ]
            if ref
        ]
    )

    payload = {
        "schema_version": "producer_consumer_smoke.v1",
        "smoke_id": smoke_id,
        "smoke_request_id": _safe_identifier(
            request.get("smoke_request_id"),
            f"producer-consumer-smoke-request:{smoke_id[:16]}",
        ),
        "smoke_status": smoke_status,
        "unavailable_condition": unavailable_condition,
        "producer_request_ref": safe_refs.get("producer_request_ref")
        if smoke_status == "smoke_built"
        else None,
        "production_receipt_ref": safe_refs.get("production_receipt_ref")
        if smoke_status == "smoke_built"
        else None,
        "support_bundle_ref": safe_refs.get("support_bundle_ref")
        if smoke_status == "smoke_built"
        else None,
        "consumer_menu_ref": safe_refs.get("consumer_menu_ref")
        if smoke_status == "smoke_built"
        else None,
        "tree_ring_snapshot_ref": safe_refs.get("tree_ring_snapshot_ref")
        if smoke_status == "smoke_built"
        else None,
        "skill_metadata_ref": safe_refs.get("skill_metadata_ref")
        if smoke_status == "smoke_built"
        else None,
        "provider_receipt_consumer_ref": safe_refs.get("provider_receipt_consumer_ref")
        if smoke_status == "smoke_built"
        else None,
        "smoke_ref": smoke_ref,
        "smoke_edges": smoke_edges,
        "safe_portable_refs": safe_portable_refs,
        "reason_codes": reason_codes,
        "ptc_callable": True,
        "runtime_owner": "runtime/pipeline/producer_consumer_smoke.py",
        "transition_prep_only": True,
        "typed_refs_only": True,
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        "consumer_ux_completion_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "production_readiness_claimed": False,
        "live_readiness_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_producer_consumer_smoke(payload)
    return payload
