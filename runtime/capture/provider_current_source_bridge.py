from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from harness_common import utc_now_iso
from source_ref.hermes_session_json import _canonical_anchor_hash


SCHEMA_VERSION = "provider_current_source_bridge.v1"
MEMORY_TICKET_SCHEMA_VERSION = "memory_ticket.v1"
CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"
ALLOWED_MIN_SPLIT_UNITS = {"paragraph_intent", "topic_decision_cluster"}
ALLOWED_TRIGGER_KINDS = {
    "explicit_user_save_command",
    "strong_memory_stimulus",
    "topic_decision_completed",
    "boundary_correction",
    "reusable_operational_rule",
    "category_community_shift",
    "currentness_changed",
}
SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _hard_nonclaims() -> dict[str, bool]:
    return {
        "op1_storage_passed": False,
        "full_ux_passed": False,
        "readme_scorecard_promotion_allowed": False,
        "production_ready": False,
        "multi_provider_parity": False,
        "hermes_true_hot_reload_passed": False,
        "graphify_full_topology_passed": False,
        "postman_semantic_quality_owner": False,
    }


def _typed_unavailable(*, reason_code: str, provider_session_id: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "typed_unavailable",
        "current_source_ready": False,
        "provider_session_id": provider_session_id,
        "reason_code": reason_code,
        "typed_unavailable": {
            "schema_version": "typed_unavailable.v1",
            "reason_code": reason_code,
            "blocked_stage": "provider_current_source_bridge",
            "fabricated_answer": False,
            "raw_provider_material_included": False,
        },
        "hard_nonclaims": _hard_nonclaims(),
    }


def _clean_required_text(value: Any) -> str:
    return str(value or "").strip()


def _load_messages(session_path: Path) -> list[dict[str, Any]]:
    if not session_path.exists():
        return []
    try:
        payload = json.loads(session_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return [dict(row) for row in messages if isinstance(row, Mapping)]


def _session_path(*, sessions_dir: Path, provider_session_id: str) -> Path:
    return sessions_dir / f"session_{provider_session_id}.json"


def build_provider_current_source_bridge(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    final_answer_text: str,
    sessions_dir: str | Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Capture a Provider-authored final answer as a bounded current source.

    The bridge writes the answer to a Hermes-session-json-compatible local
    source file, then returns only source pointers, range, hash, and watermark.
    It does not write raw Provider text to Vault and does not claim OP1 storage.
    """

    provider_id = _clean_required_text(provider_id)
    provider_profile = _clean_required_text(provider_profile)
    provider_session_id = _clean_required_text(provider_session_id)
    final_answer_text = _clean_required_text(final_answer_text)
    if not provider_id:
        return _typed_unavailable(reason_code="provider_id_missing", provider_session_id=provider_session_id)
    if not provider_profile:
        return _typed_unavailable(reason_code="provider_profile_missing", provider_session_id=provider_session_id)
    if not provider_session_id:
        return _typed_unavailable(reason_code="provider_session_id_missing")
    if not SAFE_SESSION_ID_RE.fullmatch(provider_session_id):
        return _typed_unavailable(reason_code="provider_session_id_unsafe", provider_session_id=provider_session_id)
    if not final_answer_text:
        return _typed_unavailable(reason_code="final_answer_text_missing", provider_session_id=provider_session_id)

    created_at = created_at or utc_now_iso()
    sessions_dir = Path(sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = _session_path(sessions_dir=sessions_dir, provider_session_id=provider_session_id)
    messages = _load_messages(session_path)
    start = len(messages)
    message = {
        "role": "assistant",
        "content": final_answer_text,
        "created_at": created_at,
        "source_surface": "provider_final_answer",
    }
    messages.append(message)
    end = len(messages) - 1
    selected = messages[start : end + 1]
    anchor_hash = _canonical_anchor_hash(selected)
    source_ref = f"hermes-session-json://{provider_session_id}"
    message_index_range = {"start": start, "end": end}
    commit_watermark = f"session:{provider_session_id}:message_index:{end}"
    origin_locator = f"{source_ref}#message_index={start}..{end}"
    session_payload = {
        "schema_version": "hermes_session_json.v1",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "messages": messages,
        "updated_at": created_at,
    }
    session_path.write_text(json.dumps(session_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provider_visible_card = {
        "source_ref": source_ref,
        "message_index_range": message_index_range,
        "provider_session_id": provider_session_id,
        "anchor_hash": anchor_hash,
        "commit_watermark": commit_watermark,
        "origin_locator": origin_locator,
    }
    memory_ticket_source_fields = {
        **provider_visible_card,
        "resolver_options": {"sessions_dir": str(sessions_dir.resolve())},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "current_source_ready": True,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_visible_card": provider_visible_card,
        "memory_ticket_source_fields": memory_ticket_source_fields,
        "local_source": {
            "session_path": str(session_path.resolve()),
            "local_path_not_for_provider_answer": True,
        },
        "hard_nonclaims": _hard_nonclaims(),
    }


def _memory_ticket_unavailable(reason_code: str, current_source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": MEMORY_TICKET_SCHEMA_VERSION,
        "status": "typed_unavailable",
        "reason_code": reason_code,
        "current_source_status": (current_source or {}).get("status"),
        "typed_unavailable": {
            "schema_version": "typed_unavailable.v1",
            "reason_code": reason_code,
            "blocked_stage": "memory_ticket_payload_from_current_source",
            "fabricated_answer": False,
            "raw_provider_material_included": False,
        },
        "hard_nonclaims": _hard_nonclaims(),
    }


def build_memory_ticket_payload_from_current_source(
    *,
    current_source: Mapping[str, Any],
    surface_reason: str,
    intent_field: str,
    why_not_atomic: str,
    topic_hint: str,
    category_community_hint: str,
    decision: str,
    context: str = "",
    conclusion: str = "",
    trigger_kind: str = "reusable_operational_rule",
    min_split_unit: str = "paragraph_intent",
    breadcrumb: str = "",
    reuse_condition: str = "",
) -> dict[str, Any]:
    """Build a top-level MemoryTicket payload from a verified current source."""

    if current_source.get("status") != "ready" or current_source.get("current_source_ready") is not True:
        return _memory_ticket_unavailable("current_source_not_ready", current_source)
    fields = current_source.get("memory_ticket_source_fields")
    if not isinstance(fields, Mapping):
        return _memory_ticket_unavailable("memory_ticket_source_fields_missing", current_source)
    required_text = {
        "surface_reason": surface_reason,
        "intent_field": intent_field,
        "why_not_atomic": why_not_atomic,
        "topic_hint": topic_hint,
        "category_community_hint": category_community_hint,
        "decision": decision,
    }
    missing = [name for name, value in required_text.items() if not _clean_required_text(value)]
    if missing:
        return _memory_ticket_unavailable(f"missing_{missing[0]}", current_source)
    if min_split_unit not in ALLOWED_MIN_SPLIT_UNITS:
        return _memory_ticket_unavailable("invalid_min_split_unit", current_source)
    if trigger_kind not in ALLOWED_TRIGGER_KINDS:
        return _memory_ticket_unavailable("invalid_trigger_kind", current_source)

    payload = {
        "schema_version": MEMORY_TICKET_SCHEMA_VERSION,
        "source_ref": fields["source_ref"],
        "message_index_range": dict(fields["message_index_range"]),
        "provider_session_id": fields["provider_session_id"],
        "anchor_hash": fields["anchor_hash"],
        "commit_watermark": fields["commit_watermark"],
        "resolver_options": dict(fields.get("resolver_options") or {}),
        "surface_reason": _clean_required_text(surface_reason),
        "intent_field": _clean_required_text(intent_field),
        "decomposition_guard": CANONICAL_DECOMPOSITION_GUARD,
        "min_split_unit": min_split_unit,
        "why_not_atomic": _clean_required_text(why_not_atomic),
        "topic_hint": _clean_required_text(topic_hint),
        "category_community_hint": _clean_required_text(category_community_hint),
        "trigger_kind": trigger_kind,
        "breadcrumb": _clean_required_text(breadcrumb),
        "decision": _clean_required_text(decision),
        "context": _clean_required_text(context),
        "conclusion": _clean_required_text(conclusion),
        "reuse_condition": _clean_required_text(reuse_condition),
    }
    return payload


__all__ = [
    "build_memory_ticket_payload_from_current_source",
    "build_provider_current_source_bridge",
]
