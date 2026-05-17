from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

from runtime.common.contract_validation import validate_contract_payload
from runtime.common.portable_ref import looks_like_local_path
from harness_common import utc_now_iso


TREE_RING_SNAPSHOT_SCHEMA = "tree_ring_snapshot.v1.schema.json"
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
RING_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{1,127}$")
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
    "historical_read_complete": "historical_ring_read_completion_not_allowed",
    "historical_ring_snapshot_read_capability_claimed": (
        "historical_ring_snapshot_read_claim_not_allowed"
    ),
    "live_readiness_claimed": "live_readiness_claim_not_allowed",
    "production_readiness_claimed": "production_readiness_claim_not_allowed",
    "public_runtime_integration_complete_claimed": (
        "public_runtime_integration_complete_claim_not_allowed"
    ),
}
DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_included": False,
    "raw_provider_material_included": False,
    "skill_body_included": False,
    "provider_credential_profile_included": False,
    "portable_local_path_included": False,
    "historical_read_complete": False,
    "historical_ring_snapshot_read_capability_claimed": False,
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "public_runtime_integration_complete_claimed": False,
}


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _is_safe_ring_id(value: str) -> bool:
    stripped = str(value).strip()
    if not RING_ID_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _as_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _safe_refs(values: Any) -> tuple[list[str], int]:
    refs = _as_string_list(values)
    safe_refs = [ref for ref in refs if _is_safe_ref(ref)]
    return safe_refs, len(refs) - len(safe_refs)


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


def _digest(*values: str) -> str:
    joined = "\n".join(values).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:16]


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


def validate_tree_ring_snapshot(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "tree_ring_snapshot.v1":
        raise ValueError("invalid tree ring snapshot schema_version")
    if payload.get("snapshot_status") not in {"snapshot_stubbed", "typed_unavailable"}:
        raise ValueError("invalid tree ring snapshot status")
    if payload.get("ptc_callable") is not True:
        raise ValueError("tree ring snapshot must remain PTC-callable")
    if payload.get("runtime_owner") != "runtime/memory/tree_ring_snapshot.py":
        raise ValueError("invalid tree ring snapshot runtime owner")
    if payload.get("point_in_time_stub") is not True:
        raise ValueError("tree ring snapshot must remain a point-in-time stub")

    for flag_name in [
        "historical_read_complete",
        "historical_ring_snapshot_read_capability_claimed",
        "raw_transcript_included",
        "raw_provider_material_included",
        "skill_body_included",
        "provider_credential_profile_included",
        "portable_local_path_included",
        "live_readiness_claimed",
        "production_readiness_claimed",
        "public_runtime_integration_complete_claimed",
    ]:
        if payload.get(flag_name) is not False:
            raise ValueError(f"unsafe tree ring snapshot flag: {flag_name}")

    ring_id = payload.get("ring_id")
    if ring_id is not None and not _is_safe_ring_id(str(ring_id)):
        raise ValueError("ring_id must be safe when present")
    for field in ["ring_ref", "snapshot_ref", "point_in_time_ref"]:
        value = payload.get(field)
        if value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"{field} must be a safe portable ref")
    for ref in payload.get("basis_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("basis_refs must be safe portable refs")
    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe portable refs")
    if payload.get("snapshot_status") == "snapshot_stubbed":
        if not ring_id:
            raise ValueError("snapshot_stubbed requires ring_id")
        if not payload.get("ring_ref"):
            raise ValueError("snapshot_stubbed requires ring_ref")
        if not payload.get("snapshot_ref"):
            raise ValueError("snapshot_stubbed requires snapshot_ref")
    elif not payload.get("unavailable_condition"):
        raise ValueError("typed_unavailable requires unavailable_condition")
    if not payload.get("reason_codes"):
        raise ValueError("reason_codes are required")
    validate_contract_payload(payload, TREE_RING_SNAPSHOT_SCHEMA)


def build_tree_ring_snapshot(
    *,
    snapshot_request: Mapping[str, Any],
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a deterministic Tree Ring point-in-time stub.

    This owner only proves the typed boundary and safe refs for a requested
    ring_id. It does not read historical ring contents or claim historical read
    capability.
    """

    request = dict(snapshot_request)
    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    flags.update({key: bool(request.get(key)) for key in DEFAULT_SAFETY_FLAGS if key in request})

    reason_codes = _unsafe_flag_reason_codes(flags)
    unsafe_material_reason = _unsafe_material_reason(request)
    if unsafe_material_reason is not None:
        reason_codes.append(unsafe_material_reason)

    raw_ring_id = request.get("ring_id")
    ring_id = str(raw_ring_id).strip() if raw_ring_id is not None else None
    safe_ring_id = ring_id if ring_id and _is_safe_ring_id(ring_id) else None
    basis_refs, unsafe_basis_ref_count = _safe_refs(request.get("basis_refs", ()))
    point_in_time_ref = request.get("point_in_time_ref")
    safe_point_in_time_ref = (
        str(point_in_time_ref).strip()
        if point_in_time_ref and _is_safe_ref(str(point_in_time_ref))
        else None
    )

    unavailable_condition: str | None = None
    if reason_codes:
        unavailable_condition = "blocked_unsafe_input"
    elif raw_ring_id is None or not str(raw_ring_id).strip():
        unavailable_condition = "ring_id_required"
        reason_codes = ["ring_id_required"]
    elif safe_ring_id is None:
        unavailable_condition = "unsafe_ring_id"
        reason_codes = ["unsafe_ring_id_not_allowed"]
    elif unsafe_basis_ref_count:
        unavailable_condition = "unsafe_basis_refs"
        reason_codes = ["unsafe_basis_refs_not_allowed"]
    elif point_in_time_ref and safe_point_in_time_ref is None:
        unavailable_condition = "unsafe_point_in_time_ref"
        reason_codes = ["unsafe_point_in_time_ref_not_allowed"]

    snapshot_status = "snapshot_stubbed" if safe_ring_id and unavailable_condition is None else "typed_unavailable"
    request_id = _safe_identifier(
        request.get("snapshot_request_id"),
        f"tree-ring-request:{_digest(str(safe_ring_id or 'typed-unavailable'))}",
    )

    ring_ref = None
    snapshot_ref = None
    if snapshot_status == "snapshot_stubbed" and safe_ring_id:
        snapshot_token = _digest(request_id, safe_ring_id, str(safe_point_in_time_ref or "point-in-time-stub"))
        ring_ref = f"tree-ring-ref://openyggdrasil/{safe_ring_id}"
        snapshot_ref = f"tree-ring-snapshot-ref://openyggdrasil/{safe_ring_id}/{snapshot_token}"
        if safe_point_in_time_ref is None:
            safe_point_in_time_ref = f"point-in-time-ref://openyggdrasil/{safe_ring_id}/{snapshot_token}"
        reason_codes = [
            "tree_ring_point_in_time_stub_built",
            "safe_ring_id_present",
            "historical_read_not_claimed",
        ]

    safe_portable_refs = _unique_refs(
        [
            ref
            for ref in [ring_ref, snapshot_ref, safe_point_in_time_ref, *basis_refs]
            if ref
        ]
    )
    payload = {
        "schema_version": "tree_ring_snapshot.v1",
        "snapshot_id": _safe_identifier(
            f"tree-ring-snapshot:{_digest(request_id, str(safe_ring_id or 'typed-unavailable'))}",
            "tree-ring-snapshot:typed-unavailable",
        ),
        "snapshot_request_id": request_id,
        "snapshot_status": snapshot_status,
        "unavailable_condition": unavailable_condition,
        "ring_id": safe_ring_id if snapshot_status == "snapshot_stubbed" else None,
        "ring_ref": ring_ref,
        "snapshot_ref": snapshot_ref,
        "point_in_time_ref": safe_point_in_time_ref if snapshot_status == "snapshot_stubbed" else None,
        "basis_refs": basis_refs if snapshot_status == "snapshot_stubbed" else [],
        "unsafe_basis_ref_count": unsafe_basis_ref_count,
        "safe_portable_refs": safe_portable_refs,
        "reason_codes": reason_codes,
        "ptc_callable": True,
        "runtime_owner": "runtime/memory/tree_ring_snapshot.py",
        "point_in_time_stub": True,
        "historical_read_complete": False,
        "historical_ring_snapshot_read_capability_claimed": False,
        "raw_transcript_included": False,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "public_runtime_integration_complete_claimed": False,
        "created_at": utc_now_iso(),
    }
    validate_tree_ring_snapshot(payload)
    return payload
