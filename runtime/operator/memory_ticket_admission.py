from __future__ import annotations

import re
from typing import Any, Mapping


CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_index_range(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, int) and isinstance(end, int) and start >= 0 and end >= start


def _valid_source_line_range(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, Mapping):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, int) and isinstance(end, int) and start >= 1 and end >= start


def _valid_id_range(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    start = value.get("start")
    end = value.get("end")
    return isinstance(start, (int, str)) and isinstance(end, (int, str)) and str(start) != "" and str(end) != ""


def _is_atom_tag_hint(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip())
    if not normalized:
        return True
    if len(normalized) <= 5:
        return True
    if " " not in normalized and "/" not in normalized and "community" not in normalized.lower() and "category" not in normalized.lower():
        return True
    return False


def admit_memory_ticket_payload(payload: Mapping[str, Any]) -> tuple[bool, str]:
    if payload.get("schema_version") != "memory_ticket.v1":
        return False, "invalid_schema_version"
    for key in ("source_ref", "provider_session_id", "surface_reason", "commit_watermark"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    has_index_range = "message_index_range" in payload
    has_id_range = "message_id_range" in payload
    if has_index_range == has_id_range:
        return False, "invalid_message_range_choice"
    if has_index_range and not _valid_index_range(payload.get("message_index_range")):
        return False, "invalid_message_index_range"
    if has_id_range and not _valid_id_range(payload.get("message_id_range")):
        return False, "invalid_message_id_range"
    if not _valid_source_line_range(payload.get("source_line_range")):
        return False, "invalid_source_line_range"
    if not _is_nonempty_string(payload.get("anchor_hash")):
        return False, "missing_anchor_hash"
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("anchor_hash"))):
        return False, "invalid_anchor_hash"
    for key in ("intent_field", "decomposition_guard", "min_split_unit", "why_not_atomic", "topic_hint", "category_community_hint"):
        if not _is_nonempty_string(payload.get(key)):
            return False, f"missing_{key}"
    if str(payload.get("decomposition_guard")) != CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD:
        return False, "invalid_decomposition_guard"
    if str(payload.get("min_split_unit")) not in {"paragraph_intent", "topic_decision_cluster"}:
        return False, "invalid_min_split_unit"
    if _is_atom_tag_hint(str(payload.get("category_community_hint") or "")):
        return False, "category_community_hint_too_atomic"
    for key in ("decision", "context", "conclusion", "reuse_condition"):
        if not _is_nonempty_string(payload.get(key)):
            return False, "missing_decision_capsule"
    return True, "admitted"


__all__ = [
    "CANONICAL_MEMORY_TICKET_DECOMPOSITION_GUARD",
    "admit_memory_ticket_payload",
]
