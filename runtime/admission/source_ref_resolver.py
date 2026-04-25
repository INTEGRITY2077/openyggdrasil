from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

from admission.decision_contracts import validate_source_ref_resolution_result
from harness_common import utc_now_iso


RANGE_HINT_RE = re.compile(r"^turns:([1-9][0-9]*)(?:-([1-9][0-9]*))?$")


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _clean_source_ref(source_ref: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(source_ref.get("kind") or "provider_session").strip(),
        "path_hint": str(source_ref.get("path_hint") or "").strip(),
        "range_hint": str(source_ref.get("range_hint") or "").strip(),
        "symlink_hint": source_ref.get("symlink_hint"),
    }


def _source_ref_token(source_ref: Mapping[str, Any]) -> str:
    path_hint = str(source_ref["path_hint"]).strip()
    range_hint = str(source_ref["range_hint"]).strip()
    return f"provider_session:{path_hint}#{range_hint}"


def _range_hint_is_valid(range_hint: str) -> bool:
    match = RANGE_HINT_RE.fullmatch(range_hint)
    if match is None:
        return False
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    return start <= end


def _result(
    *,
    signal: Mapping[str, Any],
    status: str,
    reason_codes: list[str],
    source_ref: Mapping[str, Any] | None,
    next_action: str,
) -> dict[str, Any]:
    clean_ref = _clean_source_ref(source_ref) if isinstance(source_ref, Mapping) else None
    payload = {
        "schema_version": "source_ref_resolution_result.v1",
        "resolution_id": uuid.uuid4().hex,
        "signal_id": _string_field(signal, "signal_id", "invalid-signal"),
        "status": status,
        "reason_codes": _unique(reason_codes),
        "source_ref": clean_ref,
        "source_ref_token": _source_ref_token(clean_ref) if status == "resolved" and clean_ref else None,
        "next_action": next_action,
        "created_at": utc_now_iso(),
    }
    validate_source_ref_resolution_result(payload)
    return payload


def resolve_signal_source_ref(
    signal: Mapping[str, Any],
    *,
    source_ref_exists: bool = True,
    source_ref_unavailable: bool = False,
) -> dict[str, Any]:
    """Resolve a provider source ref into a typed admission input.

    The resolver does not read provider raw sessions. It validates only the
    reference shape and the caller-provided availability state.
    """

    source_ref = signal.get("source_ref")
    if not isinstance(source_ref, Mapping):
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_missing"],
            source_ref=None,
            next_action="reject_signal",
        )

    clean_ref = _clean_source_ref(source_ref)
    kind = str(clean_ref["kind"])
    path_hint = str(clean_ref["path_hint"])
    range_hint = str(clean_ref["range_hint"])

    if kind != "provider_session":
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_kind_unsupported"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    if not path_hint or path_hint == "missing-source-ref":
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_missing"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    if "\n" in path_hint or "\r" in path_hint or "://" in path_hint:
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_path_malformed"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    if not range_hint:
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_range_missing"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    if not _range_hint_is_valid(range_hint):
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_range_malformed"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    if source_ref_unavailable:
        return _result(
            signal=signal,
            status="unavailable",
            reason_codes=["source_ref_unavailable"],
            source_ref=clean_ref,
            next_action="defer_until_source_available",
        )
    if not source_ref_exists:
        return _result(
            signal=signal,
            status="reject",
            reason_codes=["source_ref_unresolved"],
            source_ref=clean_ref,
            next_action="reject_signal",
        )
    return _result(
        signal=signal,
        status="resolved",
        reason_codes=["source_ref_resolved"],
        source_ref=clean_ref,
        next_action="continue_admission",
    )
