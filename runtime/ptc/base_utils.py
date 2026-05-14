from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.engine_contracts import (
    PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS,
    REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES,
    ROLE_POLYMORPHIC_EVIDENCE_CHAIN_STATUS,
    ROLE_POLYMORPHIC_SAME_RUN_SOURCE_KIND,
    _assert_additive_only_hard_nonclaims,
    _safe_portable_ref,
)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _route_token(*values: Any) -> str:
    encoded = "|".join(str(value) for value in values).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]

def _safe_identifier(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128 or not re.match(r"^[A-Za-z0-9._:-]+$", text):
        raise ValueError(f"{field_name} must be a safe identifier")
    return text

def _string_list(values: Sequence[str] | None, *, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a string list")
    return [str(value).strip() for value in values if str(value).strip()]

def _normalize_role_map(
    values: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a role ref map")
    normalized = {str(key).strip().lower().replace("-", "_"): value for key, value in values.items()}
    missing = [role for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES if role not in normalized]
    if missing:
        raise ValueError(f"{field_name} missing required roles: {', '.join(missing)}")
    return {
        role: _safe_portable_ref(normalized[role], field_name=f"{field_name}.{role}")
        for role in REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES
    }

def _normalize_strict_role_map(
    values: Mapping[str, Any],
    *,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a role ref map")
    normalized_keys = {str(key).strip().lower().replace("-", "_") for key in values}
    unknown = sorted(normalized_keys - set(REQUIRED_ROLE_POLYMORPHIC_PTC_ROLES))
    if unknown:
        raise ValueError(f"{field_name} has unsupported roles: {', '.join(unknown)}")
    return _normalize_role_map(values, field_name=field_name)

def _normalize_same_run_ptc_context(same_run_context: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(same_run_context, Mapping):
        raise ValueError("same_run_context must be an object")
    allowed = {
        "same_run_id",
        "same_run_witness_ref",
        "same_run_source_kind",
        "evidence_chain_status",
        "mailbox_delivery_ref",
        "hermes_consumption_ref",
        "ptc_trace_ref",
        "bubblewrap_trace_ref",
        "producer_receipt_ref",
        "consumer_usage_ref",
    }
    unknown = sorted(str(key) for key in set(same_run_context) - allowed)
    if unknown:
        raise ValueError(f"same_run_context has unsupported keys: {', '.join(unknown)}")
    normalized = {
        "same_run_id": _safe_identifier(
            same_run_context.get("same_run_id"),
            field_name="same_run_context.same_run_id",
        ),
        "same_run_witness_ref": _safe_portable_ref(
            same_run_context.get("same_run_witness_ref"),
            field_name="same_run_context.same_run_witness_ref",
        ),
        "same_run_source_kind": str(same_run_context.get("same_run_source_kind") or "").strip(),
        "evidence_chain_status": str(same_run_context.get("evidence_chain_status") or "").strip(),
    }
    if normalized["same_run_source_kind"] != ROLE_POLYMORPHIC_SAME_RUN_SOURCE_KIND:
        raise ValueError("same_run_context.same_run_source_kind must be physical_live_same_run")
    if normalized["evidence_chain_status"] != ROLE_POLYMORPHIC_EVIDENCE_CHAIN_STATUS:
        raise ValueError("same_run_context.evidence_chain_status must be upstream_verified")
    for key in sorted(allowed - set(normalized)):
        if key in same_run_context:
            normalized[key] = _safe_portable_ref(
                same_run_context[key],
                field_name=f"same_run_context.{key}",
            )
    return normalized

def _require_safe_ref_prefix(value: str, *, field_name: str, prefixes: Sequence[str]) -> str:
    active = _safe_portable_ref(value, field_name=field_name)
    if not any(active.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"{field_name} has invalid safe ref scheme")
    lowered = active.lower()
    if "typed-unavailable" in lowered or "unavailable" in lowered:
        raise ValueError(f"{field_name} must be non-unavailable")
    return active

def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))

def _query_terms(query_text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query_text)}

def _reject_fixture_typed_ref_terms(*refs: Any) -> None:
    flattened: list[str] = []
    for ref in refs:
        if isinstance(ref, Mapping):
            flattened.extend(str(value) for value in ref.values())
        elif isinstance(ref, Sequence) and not isinstance(ref, (str, bytes)):
            flattened.extend(str(value) for value in ref)
        elif ref is not None:
            flattened.append(str(ref))
    rendered = "\n".join(flattened).lower()
    if any(
        token in rendered
        for token in PROVIDER_SUBAGENT_PTC_SAME_RUN_TYPED_REF_SOURCE_FORBIDDEN_REF_TOKENS
    ):
        raise ValueError("same-run typed ref source must not use fixture refs")


__all__ = [
    "_utc_now_iso",
    "_route_token",
    "_safe_identifier",
    "_string_list",
    "_normalize_role_map",
    "_normalize_strict_role_map",
    "_normalize_same_run_ptc_context",
    "_require_safe_ref_prefix",
    "_clamp_int",
    "_query_terms",
    "_reject_fixture_typed_ref_terms",
]
