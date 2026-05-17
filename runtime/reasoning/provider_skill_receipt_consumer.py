from __future__ import annotations

import re
import uuid
from typing import Any, Mapping, Sequence

from runtime.common.contract_validation import validate_contract_payload
from runtime.common.portable_ref import looks_like_local_path
from harness_common import utc_now_iso


PROVIDER_SKILL_RECEIPT_CONSUMER_SCHEMA = "provider_skill_receipt_consumer.v1.schema.json"
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RAW_SKILL_BODY_RE = re.compile(r"(?s)^---\s*\n.*\bname\s*:")
UNSAFE_REF_FRAGMENTS = (
    ".skill.md",
    "credential",
    "transcript",
)
UNSAFE_KEY_REASON_CODES = {
    "raw_transcript": "raw_transcript_not_allowed",
    "raw_session_transcript": "raw_transcript_not_allowed",
    "transcript_text": "raw_transcript_not_allowed",
    "raw_provider_material": "raw_provider_material_not_allowed",
    "skill_body": "skill_body_not_allowed",
    "raw_skill_body": "raw_skill_body_not_allowed",
    "skill_source": "skill_body_not_allowed",
    "provider_credential": "provider_credential_profile_not_allowed",
    "provider_profile": "provider_credential_profile_not_allowed",
    "credential_material": "provider_credential_profile_not_allowed",
    "profile_material": "provider_credential_profile_not_allowed",
    "frontmatter": "plane_b_frontmatter_not_allowed",
    "frontmatter_source": "plane_b_frontmatter_not_allowed",
    "skill_frontmatter": "plane_b_frontmatter_not_allowed",
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
    "raw_skill_body_included": "raw_skill_body_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "portable_local_path_included": "portable_local_path_not_allowed",
    "plane_b_frontmatter_consumed": "plane_b_frontmatter_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_included": False,
    "raw_provider_material_included": False,
    "skill_body_included": False,
    "raw_skill_body_included": False,
    "provider_credential_profile_included": False,
    "portable_local_path_included": False,
    "plane_b_frontmatter_consumed": False,
}
ALLOWED_MENU_ITEM_KINDS = {
    "production_request",
    "production_receipt",
    "support_bundle",
    "routing_receipt",
    "answer_receipt",
    "approved_routing_fact",
    "recall_support_bundle",
}


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _is_safe_identifier(value: str) -> bool:
    return bool(IDENTIFIER_RE.match(str(value).strip()))


def _is_safe_label(value: str) -> bool:
    stripped = str(value).strip()
    if not stripped or len(stripped) > 180:
        return False
    if "```" in stripped or "<INSTRUCTIONS>" in stripped:
        return False
    return _unsafe_text_reason(stripped) is None


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
    string_value = str(value)
    return string_value if _is_safe_ref(string_value) else None


def _unique_refs(values: Sequence[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            refs.append(value)
            seen.add(value)
    return refs


def _normalise_menu_item(item: Mapping[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    item_ref = str(item.get("item_ref") or "").strip()
    source_ref = str(item.get("source_ref") or "").strip()
    item_kind = str(item.get("item_kind") or "").strip()
    label = str(item.get("label") or "").strip()
    reason_code = str(item.get("reason_code") or "").strip()

    if not item_ref or not _is_safe_ref(item_ref):
        return None, "unsafe_menu_item_ref"
    if not source_ref or not _is_safe_ref(source_ref):
        return None, "unsafe_menu_source_ref"
    if item_kind not in ALLOWED_MENU_ITEM_KINDS:
        return None, "unsupported_menu_item_kind"
    if not _is_safe_label(label):
        return None, "unsafe_menu_item_label"
    if not _is_safe_identifier(reason_code):
        return None, "unsafe_menu_item_reason_code"
    return {
        "item_ref": item_ref,
        "item_kind": item_kind,
        "label": label,
        "source_ref": source_ref,
        "reason_code": reason_code,
    }, None


def _normalise_menu_items(values: Any) -> tuple[list[dict[str, str]], str | None]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return [], "receipt_menu_items_required"
    if not values:
        return [], "receipt_menu_items_required"
    if len(values) > 16:
        return [], "receipt_menu_items_too_large"

    menu_items: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            return [], "malformed_receipt_menu_item"
        menu_item, error = _normalise_menu_item(value)
        if error is not None:
            return [], error
        if menu_item is not None:
            menu_items.append(menu_item)
    return menu_items, None


def validate_provider_skill_receipt_menu(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "provider_skill_receipt_consumer.v1":
        raise ValueError("invalid provider skill receipt consumer schema_version")
    if payload.get("consumption_status") not in {"menu_built", "typed_unavailable"}:
        raise ValueError("invalid provider skill receipt consumer status")
    if payload.get("ptc_callable") is not True:
        raise ValueError("provider skill receipt consumer must remain PTC-callable")
    if payload.get("plane") != "plane_a_receipt_consumer":
        raise ValueError("provider skill receipt consumer must retain Plane A boundary")
    if payload.get("runtime_owner") != "runtime/reasoning/provider_skill_receipt_consumer.py":
        raise ValueError("invalid provider skill receipt consumer runtime owner")

    expected_true_flags = {
        "plane_a_boundary_retained",
        "typed_receipt_inputs_only",
    }
    for flag_name in expected_true_flags:
        if payload.get(flag_name) is not True:
            raise ValueError(f"required provider skill receipt consumer flag: {flag_name}")

    for flag_name in [
        "plane_b_frontmatter_consumed",
        "raw_transcript_included",
        "raw_provider_material_included",
        "skill_body_included",
        "raw_skill_body_included",
        "provider_credential_profile_included",
        "portable_local_path_included",
        "live_readiness_claimed",
        "production_readiness_claimed",
        "reasoning_lease_solved_claimed",
        "public_runtime_integration_complete_claimed",
    ]:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe provider skill receipt consumer flag: {flag_name}")

    for field in ["production_request_ref", "production_receipt_ref", "support_bundle_ref", "menu_ref"]:
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"{field} must be a safe portable ref")

    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe portable refs")

    for item in payload.get("menu_items") or []:
        if not isinstance(item, Mapping):
            raise ValueError("menu_items must contain objects")
        _, error = _normalise_menu_item(item)
        if error is not None:
            raise ValueError(error)

    if payload.get("consumption_status") == "menu_built":
        if not payload.get("production_receipt_ref"):
            raise ValueError("menu_built requires production_receipt_ref")
        if not payload.get("support_bundle_ref"):
            raise ValueError("menu_built requires support_bundle_ref")
        if not payload.get("menu_items"):
            raise ValueError("menu_built requires menu_items")
    else:
        if not payload.get("unavailable_condition"):
            raise ValueError("typed_unavailable requires unavailable_condition")
    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")
    validate_contract_payload(payload, PROVIDER_SKILL_RECEIPT_CONSUMER_SCHEMA)


def build_provider_skill_receipt_menu(
    *,
    receipt_consumer_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a Plane A provider-safe receipt/support-bundle menu.

    This runtime owner consumes typed receipt and support-bundle menu artifacts.
    It does not read raw transcripts, raw skill bodies, provider credentials,
    provider profiles, or Plane B frontmatter.
    """

    request = dict(receipt_consumer_request)
    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(request.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in request})

    reason_codes = _unsafe_flag_reason_codes(flags)
    unavailable_condition: str | None = None

    unsafe_material_reason = _unsafe_material_reason(request)
    if unsafe_material_reason is not None:
        reason_codes.append(unsafe_material_reason)

    production_request_ref = _safe_ref_from(request, "production_request_ref")
    production_receipt_ref = _safe_ref_from(request, "production_receipt_ref")
    support_bundle_ref = _safe_ref_from(request, "support_bundle_ref")
    menu_items: list[dict[str, str]] = []

    if reason_codes:
        unavailable_condition = "blocked_unsafe_input"
    elif request.get("production_receipt_ref") and production_receipt_ref is None:
        unavailable_condition = "unsafe_production_receipt_ref"
        reason_codes = ["unsafe_production_receipt_ref_not_allowed"]
    elif request.get("support_bundle_ref") and support_bundle_ref is None:
        unavailable_condition = "unsafe_support_bundle_ref"
        reason_codes = ["unsafe_support_bundle_ref_not_allowed"]
    elif not production_receipt_ref:
        unavailable_condition = "production_receipt_ref_required"
        reason_codes = ["production_receipt_ref_required"]
    elif not support_bundle_ref:
        unavailable_condition = "support_bundle_ref_required"
        reason_codes = ["support_bundle_ref_required"]
    else:
        menu_items, menu_error = _normalise_menu_items(
            request.get("receipt_menu_items", request.get("menu_items"))
        )
        if menu_error is not None:
            unavailable_condition = menu_error
            reason_codes = [menu_error]

    consumption_status = "menu_built" if menu_items and unavailable_condition is None else "typed_unavailable"
    if consumption_status == "menu_built":
        reason_codes = [
            "plane_a_receipt_menu_built",
            "typed_receipt_support_bundle_inputs_only",
            "provider_safe_menu_refs_only",
        ]

    menu_ref = (
        f"provider-skill-menu-ref://openyggdrasil/plane-a/{uuid.uuid4().hex}"
        if consumption_status == "menu_built"
        else None
    )
    safe_refs = [
        ref
        for ref in [production_request_ref, production_receipt_ref, support_bundle_ref, menu_ref]
        if ref
    ]
    for item in menu_items:
        safe_refs.extend([item["item_ref"], item["source_ref"]])

    payload = {
        "schema_version": "provider_skill_receipt_consumer.v1",
        "consumption_id": uuid.uuid4().hex,
        "consumer_request_id": str(request.get("consumer_request_id") or uuid.uuid4().hex),
        "consumption_status": consumption_status,
        "unavailable_condition": unavailable_condition,
        "reason_codes": reason_codes,
        "production_request_ref": production_request_ref,
        "production_receipt_ref": production_receipt_ref,
        "support_bundle_ref": support_bundle_ref,
        "menu_ref": menu_ref,
        "menu_items": menu_items if consumption_status == "menu_built" else [],
        "safe_portable_refs": _unique_refs(safe_refs),
        "input_schema_versions": _as_string_list(request.get("input_schema_versions")),
        "ptc_callable": True,
        "plane": "plane_a_receipt_consumer",
        "runtime_owner": "runtime/reasoning/provider_skill_receipt_consumer.py",
        "plane_a_boundary_retained": True,
        "plane_b_frontmatter_consumed": False,
        "typed_receipt_inputs_only": True,
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "raw_skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_provider_skill_receipt_menu(payload)
    return payload
