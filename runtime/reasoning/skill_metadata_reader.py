from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any, Mapping

from runtime.common.portable_ref import looks_like_local_path
from harness_common import utc_now_iso


SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\\\s]+$")
METADATA_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
UNSAFE_KEY_FRAGMENTS = (
    "body",
    "transcript",
    "credential",
    "provider_profile",
    "secret",
    "token",
)
UNSAFE_VALUE_FRAGMENTS = (
    "raw transcript",
    "provider credential",
    "provider profile",
    "secret",
)
UNSAFE_FLAG_REASON_CODES = {
    "raw_transcript_included": "raw_transcript_not_allowed",
    "skill_body_included": "skill_body_not_allowed",
    "provider_credential_profile_included": "provider_credential_profile_not_allowed",
    "portable_local_path_included": "portable_local_path_not_allowed",
}
DEFAULT_SAFETY_FLAGS = {
    "raw_transcript_included": False,
    "skill_body_included": False,
    "provider_credential_profile_included": False,
    "portable_local_path_included": False,
}
UNSAFE_SKILL_REF_FALLBACK = (
    "typed-unavailable-ref://openyggdrasil/skill-metadata-reader/unsafe-skill-ref"
)


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    if ".skill.md" in stripped.lower():
        return False
    if "transcript" in stripped.lower() or "credential" in stripped.lower():
        return False
    return True


def _line_iterator(skill_source: str | Iterable[str]) -> Iterable[str]:
    if isinstance(skill_source, str):
        return iter(skill_source.splitlines())
    return iter(skill_source)


def _read_frontmatter_lines(skill_source: str | Iterable[str]) -> tuple[list[str], str | None, int]:
    """Read only the delimited frontmatter block.

    The function stops immediately after the closing delimiter, which lets tests
    prove that body lines are not consumed by using a guarded iterator.
    """

    iterator = _line_iterator(skill_source)
    try:
        first_line = next(iterator)
    except StopIteration:
        return [], "frontmatter_header_missing", 0

    line_count = 1
    if str(first_line).strip() != "---":
        return [], "frontmatter_header_missing", line_count

    lines: list[str] = []
    for raw_line in iterator:
        line_count += 1
        stripped = str(raw_line).rstrip("\r\n")
        if stripped.strip() == "---":
            return lines, None, line_count
        if len(lines) >= 128:
            return lines, "frontmatter_too_large", line_count
        lines.append(stripped)
    return lines, "frontmatter_closing_marker_missing", line_count


def _has_unsafe_material(value: str) -> bool:
    lowered = value.lower()
    if looks_like_local_path(value):
        return True
    return any(fragment in lowered for fragment in UNSAFE_VALUE_FRAGMENTS)


def _clean_scalar(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        stripped = stripped[1:-1]
    return stripped.strip()


def _parse_scalar_or_list(value: str) -> str | list[str] | None:
    stripped = value.strip()
    if stripped.startswith(("|", ">")):
        return None
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [_clean_scalar(part) for part in inner.split(",") if _clean_scalar(part)]
    return _clean_scalar(stripped)


def _parse_frontmatter_metadata(lines: list[str]) -> tuple[dict[str, str | list[str]], str | None]:
    metadata: dict[str, str | list[str]] = {}
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line.startswith((" ", "\t", "-")):
            return {}, "nested_or_multiline_frontmatter_not_supported"
        if ":" not in raw_line:
            return {}, "malformed_frontmatter_line"
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not METADATA_KEY_RE.match(key):
            return {}, "unsafe_frontmatter_key"
        lowered_key = key.lower()
        if any(fragment in lowered_key for fragment in UNSAFE_KEY_FRAGMENTS):
            return {}, "unsafe_frontmatter_key"
        parsed_value = _parse_scalar_or_list(raw_value)
        if parsed_value is None:
            return {}, "nested_or_multiline_frontmatter_not_supported"
        values = parsed_value if isinstance(parsed_value, list) else [parsed_value]
        if any(_has_unsafe_material(value) for value in values):
            return {}, "unsafe_frontmatter_value"
        metadata[key] = parsed_value
    if not metadata:
        return {}, "frontmatter_metadata_missing"
    return metadata, None


def _unsafe_flag_reason_codes(flags: Mapping[str, Any]) -> list[str]:
    return [
        reason_code
        for flag_name, reason_code in UNSAFE_FLAG_REASON_CODES.items()
        if flags.get(flag_name) is True
    ]


def validate_skill_metadata_read(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "skill_metadata_reader.v1":
        raise ValueError("invalid skill metadata reader schema_version")
    if payload.get("read_status") not in {"metadata_read", "typed_unavailable"}:
        raise ValueError("invalid skill metadata reader status")
    if payload.get("ptc_callable") is not True:
        raise ValueError("skill metadata reader must remain PTC-callable")
    if payload.get("plane") != "plane_b_frontmatter_only":
        raise ValueError("skill metadata reader must remain Plane B frontmatter-only")
    for flag_name in [
        "frontmatter_only",
        "skill_body_included",
        "raw_transcript_included",
        "provider_credential_profile_included",
        "portable_local_path_included",
        "plane_a_consumed",
    ]:
        expected = flag_name == "frontmatter_only"
        if payload.get(flag_name) is not expected:
            raise ValueError(f"unsafe skill metadata reader flag: {flag_name}")
    if payload.get("body_line_count_read") != 0:
        raise ValueError("skill metadata reader must not read skill body lines")
    if not _is_safe_ref(str(payload.get("skill_ref", ""))):
        raise ValueError("skill_ref must be a safe portable ref")
    for ref in payload.get("safe_portable_refs") or []:
        if not _is_safe_ref(str(ref)):
            raise ValueError("safe_portable_refs must be safe refs")
    if payload.get("read_status") == "metadata_read" and not payload.get("metadata"):
        raise ValueError("metadata_read status requires metadata")


def build_skill_metadata_read(
    *,
    skill_ref: str,
    skill_source: str | Iterable[str],
    frontmatter_ref: str | None = None,
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build Plane B frontmatter-only skill metadata.

    This runtime owner consumes only a delimited metadata header. It does not
    read skill body lines, provider transcripts, provider credentials, or Plane A
    receipts.
    """

    flags = dict(DEFAULT_SAFETY_FLAGS)
    flags.update(dict(safety_flags or {}))
    unsafe_flag_reasons = _unsafe_flag_reason_codes(flags)

    input_skill_ref = str(skill_ref)
    safe_skill_ref = input_skill_ref if _is_safe_ref(input_skill_ref) else UNSAFE_SKILL_REF_FALLBACK
    safe_frontmatter_ref = frontmatter_ref if frontmatter_ref and _is_safe_ref(frontmatter_ref) else None

    reason_codes: list[str] = []
    unavailable_condition: str | None = None
    metadata: dict[str, str | list[str]] = {}
    frontmatter_line_count = 0

    if safe_skill_ref == UNSAFE_SKILL_REF_FALLBACK:
        unavailable_condition = "unsafe_skill_ref"
        reason_codes = ["unsafe_skill_ref_not_allowed"]
    elif frontmatter_ref and safe_frontmatter_ref is None:
        unavailable_condition = "unsafe_frontmatter_ref"
        reason_codes = ["unsafe_frontmatter_ref_not_allowed"]
    elif unsafe_flag_reasons:
        unavailable_condition = "blocked_unsafe_input"
        reason_codes = unsafe_flag_reasons
    else:
        frontmatter_lines, read_error, frontmatter_line_count = _read_frontmatter_lines(skill_source)
        if read_error is not None:
            unavailable_condition = read_error
            reason_codes = [read_error]
        else:
            metadata, parse_error = _parse_frontmatter_metadata(frontmatter_lines)
            if parse_error is not None:
                unavailable_condition = parse_error
                reason_codes = [parse_error]

    read_status = "metadata_read" if metadata and unavailable_condition is None else "typed_unavailable"
    if read_status == "metadata_read":
        reason_codes = [
            "skill_frontmatter_metadata_read",
            "plane_b_frontmatter_only_boundary_retained",
        ]

    safe_portable_refs = [safe_skill_ref]
    if safe_frontmatter_ref:
        safe_portable_refs.append(safe_frontmatter_ref)

    payload = {
        "schema_version": "skill_metadata_reader.v1",
        "metadata_read_id": uuid.uuid4().hex,
        "skill_ref": safe_skill_ref,
        "read_status": read_status,
        "frontmatter_ref": safe_frontmatter_ref,
        "metadata": metadata if read_status == "metadata_read" else {},
        "metadata_keys": sorted(metadata.keys()) if read_status == "metadata_read" else [],
        "safe_portable_refs": safe_portable_refs,
        "unavailable_condition": unavailable_condition,
        "reason_codes": reason_codes,
        "frontmatter_line_count": frontmatter_line_count,
        "body_line_count_read": 0,
        "ptc_callable": True,
        "plane": "plane_b_frontmatter_only",
        "runtime_owner": "runtime/reasoning/skill_metadata_reader.py",
        "frontmatter_only": True,
        "skill_body_included": False,
        "raw_transcript_included": False,
        "provider_credential_profile_included": False,
        "portable_local_path_included": False,
        "plane_a_consumed": False,
        "created_at": utc_now_iso(),
    }
    validate_skill_metadata_read(payload)
    return payload
