from __future__ import annotations

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
import json
import re
from pathlib import Path
from typing import Any, Mapping

from harness_common import utc_now_iso
from source_ref.hermes_session_json import _canonical_anchor_hash
from runtime.capture.provider_salience_trigger import detect_provider_memory_salience


SCHEMA_VERSION = "provider_current_source_bridge.v1"
MEMORY_TICKET_SCHEMA_VERSION = "memory_ticket.v1"
CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"
BOUNDARY_CANONICAL_TOPIC_TITLE = "OpenYggdrasil과 Hermes 기본 기억의 책임 경계"
BOUNDARY_CANONICAL_TOPIC_KEY = "openyggdrasil-hermes-memory-boundary"
ALLOWED_SOURCE_REF_SCHEMES = {"hermes-session-json", "provider-session-json"}
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
    except RECOVERABLE_RUNTIME_ERRORS:
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
    It does not write raw Provider text to Vault and does not claim MS storage.
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


def build_provider_exchange_current_source_bridge(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    user_text: str,
    assistant_text: str,
    sessions_dir: str | Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Capture a bounded user/assistant exchange as a source_ref pointer."""

    provider_id = _clean_required_text(provider_id)
    provider_profile = _clean_required_text(provider_profile)
    provider_session_id = _clean_required_text(provider_session_id)
    user_text = _clean_required_text(user_text)
    assistant_text = _clean_required_text(assistant_text)
    if not user_text:
        return _typed_unavailable(reason_code="user_text_missing", provider_session_id=provider_session_id)
    if not assistant_text:
        return _typed_unavailable(reason_code="assistant_text_missing", provider_session_id=provider_session_id)
    if not provider_id:
        return _typed_unavailable(reason_code="provider_id_missing", provider_session_id=provider_session_id)
    if not provider_profile:
        return _typed_unavailable(reason_code="provider_profile_missing", provider_session_id=provider_session_id)
    if not provider_session_id:
        return _typed_unavailable(reason_code="provider_session_id_missing")
    if not SAFE_SESSION_ID_RE.fullmatch(provider_session_id):
        return _typed_unavailable(reason_code="provider_session_id_unsafe", provider_session_id=provider_session_id)

    created_at = created_at or utc_now_iso()
    sessions_dir = Path(sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = _session_path(sessions_dir=sessions_dir, provider_session_id=provider_session_id)
    messages = _load_messages(session_path)
    start = len(messages)
    messages.extend(
        [
            {
                "role": "user",
                "content": user_text,
                "created_at": created_at,
                "source_surface": "provider_user_message",
            },
            {
                "role": "assistant",
                "content": assistant_text,
                "created_at": created_at,
                "source_surface": "provider_assistant_response",
            },
        ]
    )
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


def build_existing_provider_exchange_current_source_bridge(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    message_index_range: Mapping[str, Any],
    anchor_hash: str,
    sessions_dir: str | Path,
    source_ref_scheme: str = "hermes-session-json",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Return source_ref fields for an already captured Provider session range."""

    provider_id = _clean_required_text(provider_id)
    provider_profile = _clean_required_text(provider_profile)
    provider_session_id = _clean_required_text(provider_session_id)
    anchor_hash = _clean_required_text(anchor_hash)
    source_ref_scheme = _clean_required_text(source_ref_scheme)
    if not provider_id:
        return _typed_unavailable(reason_code="provider_id_missing", provider_session_id=provider_session_id)
    if not provider_profile:
        return _typed_unavailable(reason_code="provider_profile_missing", provider_session_id=provider_session_id)
    if not provider_session_id:
        return _typed_unavailable(reason_code="provider_session_id_missing")
    if not SAFE_SESSION_ID_RE.fullmatch(provider_session_id):
        return _typed_unavailable(reason_code="provider_session_id_unsafe", provider_session_id=provider_session_id)
    if source_ref_scheme not in ALLOWED_SOURCE_REF_SCHEMES:
        return _typed_unavailable(reason_code="source_ref_scheme_unsupported", provider_session_id=provider_session_id)
    start = message_index_range.get("start") if isinstance(message_index_range, Mapping) else None
    end = message_index_range.get("end") if isinstance(message_index_range, Mapping) else None
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        return _typed_unavailable(reason_code="message_index_range_invalid", provider_session_id=provider_session_id)
    if not re.fullmatch(r"[0-9a-f]{64}", anchor_hash):
        return _typed_unavailable(reason_code="anchor_hash_invalid", provider_session_id=provider_session_id)

    sessions_dir = Path(sessions_dir)
    session_path = _session_path(sessions_dir=sessions_dir, provider_session_id=provider_session_id)
    if not session_path.exists():
        return _typed_unavailable(reason_code="provider_session_source_missing", provider_session_id=provider_session_id)
    created_at = created_at or utc_now_iso()
    source_ref = f"{source_ref_scheme}://{provider_session_id}"
    normalized_range = {"start": start, "end": end}
    commit_watermark = f"session:{provider_session_id}:message_index:{end}"
    origin_locator = f"{source_ref}#message_index={start}..{end}"
    provider_visible_card = {
        "source_ref": source_ref,
        "message_index_range": normalized_range,
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
            "existing_provider_session_range": True,
            "observed_at": created_at,
        },
        "hard_nonclaims": _hard_nonclaims(),
    }


def _boundary_memory_fields(*, user_text: str, assistant_text: str) -> dict[str, str]:
    combined = f"{user_text}\n{assistant_text}"
    if (
        "OpenYggdrasil" in combined
        and "Hermes" in combined
        and any(marker in combined for marker in ("복사", "복제물", "복제"))
        and any(marker in combined for marker in ("장기 위키", "장기 지식", "출처"))
    ):
        return {
            "decision": "OpenYggdrasil은 Hermes 기본 기억의 복제물이 아니라 여러 제공자가 공유하는 근거 있는 장기 위키 계층이다.",
            "context": "Provider 자연 대화에서 사용자가 OpenYggdrasil과 Hermes 기본 기억의 책임 경계를 설명했다.",
            "conclusion": "Hermes 기본 기억은 말투, 짧은 선호, 현재 세션 습관 같은 즉시 행동 표면을 다루고, OpenYggdrasil 기억은 출처와 판단 흐름이 남는 장기 지식을 다룬다.",
            "reuse_condition": "사용자가 OpenYggdrasil과 Hermes 기본 기억의 차이, 장기 위키 계층, 제공자 공용 기억 경계를 물을 때 사용한다.",
            "canonical_topic_title": BOUNDARY_CANONICAL_TOPIC_TITLE,
            "canonical_topic_key": BOUNDARY_CANONICAL_TOPIC_KEY,
        }
    return {}


def _provider_exchange_memory_fields(*, user_text: str, assistant_text: str) -> dict[str, str]:
    combined = f"{user_text}\n{assistant_text}"
    if "OpenYggdrasil" in combined and "Hermes" in combined:
        return {
            "decision": (
                "OpenYggdrasil is not a mirror of Hermes native memory; it is an "
                "evidence-backed long-term wiki layer. Hermes native memory remains "
                "the Provider behavior surface for tone, short preferences, and current-session habits."
            ),
            "context": "A natural Provider exchange discussed the boundary between Hermes native memory and OpenYggdrasil memory.",
            "conclusion": "Use Hermes native memory for immediate behavior shaping and OpenYggdrasil for sourced, reusable, long-term knowledge.",
            "reuse_condition": "Use when a later question asks how Hermes native memory, Provider behavior, and OpenYggdrasil wiki memory differ.",
            "canonical_topic_title": BOUNDARY_CANONICAL_TOPIC_TITLE,
            "canonical_topic_key": BOUNDARY_CANONICAL_TOPIC_KEY,
        }
    if "README" in combined or "공개 문서" in combined or "공개 README" in combined:
        return {
            "decision": (
                "Public README surfaces should show the current user-facing affordance and keep "
                "internal lane names, legacy aliases, proof/run/phase labels, mailbox, receipt, "
                "and tmux details out of the first-contact product surface."
            ),
            "context": "The user and Provider refined a public documentation boundary through failure cases.",
            "conclusion": (
                "Put current install/use concepts in README; move migration, debug, status, and historical "
                "compatibility details to separate documents."
            ),
            "reuse_condition": "Use when editing or reviewing public-facing README and first-contact documentation.",
            "canonical_topic_title": "Public README affordance boundary",
            "canonical_topic_key": "public-readme-affordance-boundary",
        }
    if any(marker in combined for marker in ("CLAUDE.md", "auto memory", "Hook", "Skill", "MCP", "Plugin")):
        return {
            "decision": (
                "Claude Code documentation should prefer placement criteria over definitions: "
                "CLAUDE.md for explicit managed team/project rules, auto memory for learned project context, "
                "Hook for automatic event actions, Skill for model-read procedures, MCP for external system "
                "connections, and Plugin for packaged extension sets."
            ),
            "context": "The user asked for short placement boundaries across Claude Code documentation concepts.",
            "conclusion": "Answer with where-to-place criteria first, then give definitions only when needed.",
            "reuse_condition": "Use when the user asks to distinguish Claude Code concepts for team documentation.",
            "canonical_topic_title": "Claude Code extension placement criteria",
            "canonical_topic_key": "claude-code-extension-placement-criteria",
        }
    return {}


def build_memory_ticket_payload_from_provider_exchange(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    user_text: str,
    assistant_text: str,
    sessions_dir: str | Path,
    category_community_hint: str = "OpenYggdrasil memory architecture community / provider memory boundary",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MemoryTicket from a natural Provider exchange when salience is sufficient."""

    salience = detect_provider_memory_salience(f"{user_text}\n{assistant_text}")
    if salience.get("trigger_decision") != "emit":
        return _memory_ticket_unavailable("provider_exchange_not_salient")
    fields = _provider_exchange_memory_fields(user_text=user_text, assistant_text=assistant_text)
    if not fields:
        return _memory_ticket_unavailable("provider_exchange_requires_bounded_distillation")
    current_source = build_provider_exchange_current_source_bridge(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        user_text=user_text,
        assistant_text=assistant_text,
        sessions_dir=sessions_dir,
        created_at=created_at,
    )
    if current_source.get("status") != "ready":
        return _memory_ticket_unavailable("provider_exchange_source_unavailable", current_source)
    payload = build_memory_ticket_payload_from_current_source(
        current_source=current_source,
        surface_reason=str(salience.get("intent_field") or "Provider 자연 대화에서 나온 장기 기억 후보"),
        intent_field=str(salience.get("intent_field") or "장기 기억 후보"),
        why_not_atomic=str(salience.get("why_not_atomic") or "문단 의도를 보존해야 한다."),
        topic_hint=str(salience.get("topic_hint") or "OpenYggdrasil 기억 책임 경계"),
        category_community_hint=str(salience.get("category_community_hint") or category_community_hint),
        decision=fields["decision"],
        context=fields["context"],
        conclusion=fields["conclusion"],
        trigger_kind=str(salience.get("trigger_kind") or "explicit_user_save_command"),
        min_split_unit="topic_decision_cluster",
        breadcrumb=str(salience.get("breadcrumb") or ""),
        reuse_condition=fields["reuse_condition"],
        canonical_topic_title=fields.get("canonical_topic_title") or str(salience.get("canonical_topic_title") or ""),
        canonical_topic_key=fields.get("canonical_topic_key") or str(salience.get("canonical_topic_key") or ""),
    )
    payload["admission_bridge"] = {
        "schema_version": "provider_exchange_admission_bridge.v1",
        "salience_trigger_kind": salience.get("trigger_kind"),
        "distillation_status": "bounded_heuristic_boundary_contract",
        "raw_provider_material_included": False,
        "postman_semantic_quality_owner": False,
    }
    return payload


def build_memory_ticket_payload_from_existing_provider_exchange(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    user_text: str,
    assistant_text: str,
    message_index_range: Mapping[str, Any],
    anchor_hash: str,
    sessions_dir: str | Path,
    source_ref_scheme: str = "hermes-session-json",
    category_community_hint: str = "OpenYggdrasil memory architecture community / provider memory boundary",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MemoryTicket from a salient Provider range without copying the session."""

    salience = detect_provider_memory_salience(f"{user_text}\n{assistant_text}")
    if salience.get("trigger_decision") != "emit":
        return _memory_ticket_unavailable("provider_exchange_not_salient")
    fields = _provider_exchange_memory_fields(user_text=user_text, assistant_text=assistant_text)
    if not fields:
        return _memory_ticket_unavailable("provider_exchange_requires_bounded_distillation")
    current_source = build_existing_provider_exchange_current_source_bridge(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        message_index_range=message_index_range,
        anchor_hash=anchor_hash,
        sessions_dir=sessions_dir,
        source_ref_scheme=source_ref_scheme,
        created_at=created_at,
    )
    if current_source.get("status") != "ready":
        return _memory_ticket_unavailable("provider_exchange_source_unavailable", current_source)
    payload = build_memory_ticket_payload_from_current_source(
        current_source=current_source,
        surface_reason=str(salience.get("intent_field") or "Provider 자연 대화에서 나온 장기 기억 후보"),
        intent_field=str(salience.get("intent_field") or "장기 기억 후보"),
        why_not_atomic=str(salience.get("why_not_atomic") or "문단 의도를 보존해야 한다."),
        topic_hint=str(salience.get("topic_hint") or "OpenYggdrasil 기억 책임 경계"),
        category_community_hint=str(salience.get("category_community_hint") or category_community_hint),
        decision=fields["decision"],
        context=fields["context"],
        conclusion=fields["conclusion"],
        trigger_kind=str(salience.get("trigger_kind") or "explicit_user_save_command"),
        min_split_unit="topic_decision_cluster",
        breadcrumb=str(salience.get("breadcrumb") or ""),
        reuse_condition=fields["reuse_condition"],
        canonical_topic_title=fields.get("canonical_topic_title") or str(salience.get("canonical_topic_title") or ""),
        canonical_topic_key=fields.get("canonical_topic_key") or str(salience.get("canonical_topic_key") or ""),
    )
    payload["admission_bridge"] = {
        "schema_version": "provider_exchange_admission_bridge.v1",
        "salience_trigger_kind": salience.get("trigger_kind"),
        "distillation_status": "bounded_heuristic_boundary_contract",
        "raw_provider_material_included": False,
        "postman_semantic_quality_owner": False,
        "existing_provider_session_range": True,
    }
    return payload


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
    canonical_topic_title: str = "",
    canonical_topic_key: str = "",
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
        "decision_capsule": {
            "decision": _clean_required_text(decision),
            "context": _clean_required_text(context),
            "conclusion": _clean_required_text(conclusion),
            "evidence": [fields["source_ref"]],
            "reuse_condition": _clean_required_text(reuse_condition),
        },
    }
    if isinstance(fields.get("source_line_range"), Mapping):
        payload["source_line_range"] = dict(fields["source_line_range"])
    if _clean_required_text(canonical_topic_title):
        payload["canonical_topic_title"] = _clean_required_text(canonical_topic_title)
    if _clean_required_text(canonical_topic_key):
        payload["canonical_topic_key"] = _clean_required_text(canonical_topic_key)
    return payload


__all__ = [
    "BOUNDARY_CANONICAL_TOPIC_KEY",
    "BOUNDARY_CANONICAL_TOPIC_TITLE",
    "ALLOWED_SOURCE_REF_SCHEMES",
    "build_existing_provider_exchange_current_source_bridge",
    "build_memory_ticket_payload_from_existing_provider_exchange",
    "build_memory_ticket_payload_from_provider_exchange",
    "build_memory_ticket_payload_from_current_source",
    "build_provider_exchange_current_source_bridge",
    "build_provider_current_source_bridge",
]
