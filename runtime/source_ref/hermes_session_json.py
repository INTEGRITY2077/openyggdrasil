from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical_anchor_hash(messages: list[dict[str, Any]]) -> str:
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_hermes_session_json_source_ref(
    *,
    source_ref: str,
    message_index_range: dict[str, int],
    sessions_dir: str | Path,
    anchor_hash: str,
) -> dict[str, Any]:
    """Hermes session_<id>.json source_ref를 message index 범위로 해석한다."""
    prefix = "hermes-session-json://"
    if not source_ref.startswith(prefix):
        return {
            "status": "reject",
            "reason": "unsupported_source_ref",
            "source_ref": source_ref,
            "resolver_status": "reject",
            "redaction_status": "not_applicable",
        }

    session_id = source_ref[len(prefix) :]
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
