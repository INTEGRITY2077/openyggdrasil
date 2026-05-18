from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SUPPORTED_SESSION_JSON_SCHEMES = ("hermes-session-json", "provider-session-json")


def _canonical_anchor_hash(messages: list[dict[str, Any]]) -> str:
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_session_json_source_ref(source_ref: str) -> tuple[str, str] | None:
    for scheme in SUPPORTED_SESSION_JSON_SCHEMES:
        prefix = f"{scheme}://"
        if source_ref.startswith(prefix):
            return scheme, source_ref[len(prefix) :]
    return None


def resolve_hermes_session_json_source_ref(
    *,
    source_ref: str,
    message_index_range: dict[str, int],
    sessions_dir: str | Path,
    anchor_hash: str,
) -> dict[str, Any]:
    """Hermes session_<id>.json source_ref를 message index 범위로 해석한다."""
    parsed = _parse_session_json_source_ref(source_ref)
    if not parsed:
        return {
            "status": "reject",
            "reason": "unsupported_source_ref",
            "source_ref": source_ref,
            "resolver_status": "reject",
            "redaction_status": "not_applicable",
        }

    scheme, session_id = parsed
    session_path = Path(sessions_dir) / f"session_{session_id}.json"
    if not session_path.exists():
        return {
            "status": "unavailable",
            "reason": "session_json_not_found",
            "source_ref": source_ref,
            "provider_session_id": session_id,
            "resolver_status": "unavailable",
            "redaction_status": "not_applicable",
        }

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    messages = payload.get("messages") or []
    start = int(message_index_range["start"])
    end = int(message_index_range["end"])
    selected = messages[start : end + 1]
    computed_anchor_hash = _canonical_anchor_hash(selected)

    if computed_anchor_hash != anchor_hash:
        return {
            "status": "unavailable",
            "reason": "anchor_hash_mismatch",
            "source_ref": source_ref,
            "provider_session_id": session_id,
            "message_index_range": {"start": start, "end": end},
            "anchor_hash": anchor_hash,
            "computed_anchor_hash": computed_anchor_hash,
            "resolver_status": "unavailable",
            "redaction_status": "not_applicable",
        }

    origin_locator = f"{source_ref}#message_index={start}..{end}"
    return {
        "status": "resolved",
        "source_ref_scheme": scheme,
        "provider_session_id": session_id,
        "source_ref": source_ref,
        "message_index_range": {"start": start, "end": end},
        "message_range": {"start": start, "end": end},
        "origin_locator": origin_locator,
        "commit_watermark": f"session:{session_id}:message_index:{end}",
        "anchor_hash": anchor_hash,
        "messages": selected,
        "resolver_status": "resolved",
        "redaction_status": "pointer_only",
    }


def resolve_hermes_session_json_registered(
    *,
    source_ref: str,
    range_hint: dict[str, Any] | None = None,
    anchor_hash: str = "",
    resolver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """registry가 호출하는 Hermes session JSON adapter wrapper."""
    range_hint = range_hint or {}
    resolver_options = resolver_options or {}
    sessions_dir = resolver_options.get("sessions_dir")
    if not sessions_dir:
        return {
            "status": "unavailable",
            "reason": "resolver_option_missing:sessions_dir",
            "source_ref": source_ref,
            "resolver_status": "unavailable",
            "redaction_status": "not_applicable",
        }
    return resolve_hermes_session_json_source_ref(
        source_ref=source_ref,
        message_index_range={"start": int(range_hint.get("start", 0)), "end": int(range_hint.get("end", 0))},
        sessions_dir=Path(sessions_dir),
        anchor_hash=anchor_hash,
    )


def register_hermes_session_json_resolver() -> None:
    """Hermes adapter boundary에서 hermes-session-json scheme을 명시 등록한다."""
    from .registry import register_source_ref_resolver

    register_source_ref_resolver("hermes-session-json", resolve_hermes_session_json_registered)
    register_source_ref_resolver("provider-session-json", resolve_hermes_session_json_registered)


__all__ = [
    "_canonical_anchor_hash",
    "SUPPORTED_SESSION_JSON_SCHEMES",
    "register_hermes_session_json_resolver",
    "resolve_hermes_session_json_registered",
    "resolve_hermes_session_json_source_ref",
]
