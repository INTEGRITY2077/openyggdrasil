from __future__ import annotations

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from harness_common import utc_now_iso
from source_ref.hermes_session_json import _canonical_anchor_hash
from runtime.capture.provider_salience_trigger import detect_provider_memory_salience
from runtime.memory.domain_evidence import build_domain_evidence_request


SCHEMA_VERSION = "provider_current_source_bridge.v1"
MEMORY_TICKET_SCHEMA_VERSION = "memory_ticket.v1"
CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"
ALLOWED_SOURCE_REF_SCHEMES = {"hermes-session-json", "provider-session-json"}
ALLOWED_MIN_SPLIT_UNITS = {"paragraph_intent", "topic_decision_cluster"}
ALLOWED_TRIGGER_KINDS = {
    "explicit_user_save_command",
    "strong_memory_stimulus",
    "durable_reuse_signal",
    "topic_decision_completed",
    "boundary_correction",
    "reusable_operational_rule",
    "category_community_shift",
    "currentness_changed",
}
SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _hard_nonclaims() -> dict[str, bool]:
    return {
        "ms1_storage_passed": False,
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
    """Capture a Provider-authored final answer as a bounded source pointer."""

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
    messages.append(
        {
            "role": "assistant",
            "content": final_answer_text,
            "created_at": created_at,
            "source_surface": "provider_final_answer",
        }
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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "current_source_ready": True,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_visible_card": provider_visible_card,
        "memory_ticket_source_fields": {
            **provider_visible_card,
            "resolver_options": {"sessions_dir": str(sessions_dir.resolve())},
        },
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
    """Capture a bounded user/assistant exchange as a source pointer."""

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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "current_source_ready": True,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_visible_card": provider_visible_card,
        "memory_ticket_source_fields": {
            **provider_visible_card,
            "resolver_options": {"sessions_dir": str(sessions_dir.resolve())},
        },
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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "current_source_ready": True,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_visible_card": provider_visible_card,
        "memory_ticket_source_fields": {
            **provider_visible_card,
            "resolver_options": {"sessions_dir": str(sessions_dir.resolve())},
        },
        "local_source": {
            "session_path": str(session_path.resolve()),
            "local_path_not_for_provider_answer": True,
            "existing_provider_session_range": True,
            "observed_at": created_at,
        },
        "hard_nonclaims": _hard_nonclaims(),
    }


def _compact_for_decision(text: str, *, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _stable_signal_buckets(text: str) -> list[str]:
    """Return stable semantic buckets for episode grouping.

    This intentionally groups by durable decision axes instead of transient
    prompt wording, so a user can revisit the same idea over discontinuous
    turns without fragmenting the pending episode ledger.
    """

    lowered = text.lower()
    buckets = {
        "agent-taxonomy": (
            "agent",
            "agents",
            "main agent",
            "subagent",
            "agent team",
            "agent-team",
            "\uc5d0\uc774\uc804\ud2b8",
            "\uc11c\ube0c\uc5d0\uc774\uc804\ud2b8",
        ),
        "extension-placement": (
            "hook",
            "hooks",
            "skill",
            "skills",
            "mcp",
            "plugin",
            "plugins",
            "\ud6c5",
            "\uc2a4\ud0ac",
            "\ud50c\ub7ec\uadf8\uc778",
        ),
        "execution-distribution": (
            "runtime",
            "execution",
            "execute",
            "definition",
            "distribution",
            "supplied",
            "source path",
            "\uc2e4\ud589",
            "\uc2e4\ud589 \ub2e8\uc704",
            "\uc815\uc758",
            "\uacf5\uae09",
            "\uacf5\uae09 \uacbd\ub85c",
            "\ubc30\ud3ec",
        ),
        "role-boundary": (
            "boundary",
            "separate",
            "separates",
            "split",
            "distinction",
            "not mix",
            "\uacbd\uacc4",
            "\uad6c\ubd84",
            "\ubd84\ub9ac",
            "\uc11e\uc9c0",
            "\ub530\ub85c",
        ),
        "durable-reuse": (
            "reuse",
            "later",
            "stable",
            "next time",
            "keep",
            "criterion",
            "criteria",
            "rule",
            "\ub098\uc911",
            "\ub2e4\uc74c",
            "\uacc4\uc18d",
            "\uc720\uc9c0",
            "\uae30\uc900",
            "\uc6d0\uce59",
        ),
        "source-evidence": (
            "source",
            "evidence",
            "proof",
            "unsupported",
            "verify",
            "\uadfc\uac70",
            "\ucd9c\ucc98",
            "\uac80\uc99d",
            "\ud655\uc778",
            "\ub2e8\uc815\ud558\uc9c0",
        ),
        "automation-timing": (
            "automatic",
            "lifecycle",
            "event",
            "timing",
            "formatting",
            "\uc790\ub3d9",
            "\uc0dd\uba85\uc8fc\uae30",
            "\uc774\ubca4\ud2b8",
        ),
        "animal-ecology": (
            "dog",
            "dogs",
            "puppy",
            "canine",
            "walk",
            "walking",
            "smell",
            "odor",
            "routine",
            "breed",
            "husky",
            "chihuahua",
            "\uac15\uc544\uc9c0",
            "\ubc18\ub824\uacac",
            "\uc0b0\ucc45",
            "\ud6c4\uac01",
            "\ub0c4\uc0c8",
            "\ub8e8\ud2f4",
            "\ud488\uc885",
        ),
        "animal-welfare": (
            "welfare",
            "punishment",
            "training",
            "ethics",
            "stress",
            "behavior modification",
            "\ubcf5\uc9c0",
            "\uccb4\ubc8c",
            "\ud6c8\ub828",
            "\uc724\ub9ac",
            "\uc2a4\ud2b8\ub808\uc2a4",
            "\ud589\ub3d9 \uc218\uc815",
        ),
        "urban-ecology": (
            "urban",
            "park",
            "wildlife",
            "habitat",
            "disturbance",
            "leash",
            "public management",
            "\ub3c4\uc2dc",
            "\uacf5\uc6d0",
            "\uc57c\uc0dd\ub3d9\ubb3c",
            "\uc11c\uc2dd\uc9c0",
            "\uad50\ub780",
            "\ub9ac\ub4dc\uc904",
            "\uacf5\uacf5 \uad00\ub9ac",
        ),
    }
    active = [
        bucket
        for bucket, markers in buckets.items()
        if any(marker in lowered for marker in markers)
    ]
    return sorted(active)


def _wiki_rule_from_provider_answer(answer: str) -> str:
    text = _compact_for_decision(answer)
    text = re.sub(r"^(네,?\s*)?맞습니다\.\s*", "", text)
    text = re.sub(r"^네\s+.{1,24}\s+맞습니다\.\s*", "", text)
    text = re.sub(r"^정리하면[:：]?\s*", "", text)
    text = re.sub(r"^이렇게\s+바로잡으면\s+됩니다\.\s*", "", text)
    text = re.split(r"\s+더\s+짧게[:：]", text, maxsplit=1)[0].strip()
    text = re.split(r"\s+주의할\s+문장[:：]", text, maxsplit=1)[0].strip()
    quoted = re.search(r"[“\"]([^”\"]{20,500})[”\"]", text)
    if quoted:
        text = quoted.group(1).strip()
    return text or _compact_for_decision(answer)


def _looks_like_answer_scaffold(text: str) -> bool:
    compact = " ".join(str(text or "").split())
    if not compact:
        return True
    table_markers = ("|---|", " | ", "| 축 |", "| 기준 |")
    if any(marker in compact for marker in table_markers):
        return True
    if compact.endswith("..."):
        return True
    return len(compact) > 180


def _select_canonical_decision(*, answer_candidate: str, conclusion: str) -> str:
    """Keep the durable claim separate from Provider answer prose."""

    answer_candidate = str(answer_candidate or "").strip()
    conclusion = str(conclusion or "").strip()
    sentence_count = sum(answer_candidate.count(marker) for marker in (".", "?", "!", "。"))
    if conclusion and (
        _looks_like_answer_scaffold(answer_candidate)
        or sentence_count >= 2
        or len(answer_candidate) < 40
    ):
        return conclusion
    return answer_candidate or conclusion


_CLAUDE_CODE_PLACEMENT_CONCEPTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Hook",
        "automatic event handler",
        ("hook", "hooks", "\ud6c5"),
    ),
    (
        "Skill",
        "model-loaded procedure or rubric",
        ("skill", "skills", "\uc2a4\ud0ac"),
    ),
    (
        "slash command",
        "user-called entrypoint",
        ("slash command", "slash commands", "/name", "/review", "\uc2ac\ub798\uc2dc"),
    ),
    (
        "CLAUDE.md/rules",
        "always-on project guidance",
        ("claude.md", "claude md", "rules", "\ud56d\uc0c1 \uc801\uc6a9", "\ud300 \uaddc\uce59"),
    ),
    (
        "MCP",
        "external tool or data connector",
        ("mcp",),
    ),
    (
        "Plugin",
        "packaged distribution unit",
        ("plugin", "plugins", "\ud50c\ub7ec\uadf8\uc778"),
    ),
)


def _mentioned_claude_code_placement_concepts(text: str) -> list[tuple[str, str]]:
    lowered = str(text or "").lower()
    concepts: list[tuple[str, str]] = []
    for name, role, markers in _CLAUDE_CODE_PLACEMENT_CONCEPTS:
        if name == "slash command":
            has_explicit_slash_command = any(marker.lower() in lowered for marker in markers)
            has_contextual_command = (
                ("command" in lowered or "\uba85\ub839" in lowered or "\ud638\ucd9c \uc785\uad6c" in lowered)
                and any(anchor in lowered for anchor in ("hook", "skill", "claude.md", "rules", "\ud6c5", "\uc2a4\ud0ac"))
            )
            if has_explicit_slash_command or has_contextual_command:
                concepts.append((name, role))
            continue
        if any(marker.lower() in lowered for marker in markers):
            concepts.append((name, role))
    return concepts


def _extension_topic_title(concepts: list[tuple[str, str]]) -> str:
    names = [name for name, _role in concepts]
    lowered = {name.lower() for name in names}
    if {"slash command", "skill", "hook", "claude.md/rules"}.issubset(lowered):
        return "Claude Code command, skill, hook, and project guidance placement boundary"
    if {"hook", "skill", "mcp", "plugin"}.issubset(lowered):
        return "Claude Code extension placement boundary"
    if names:
        joined = ", ".join(names[:-1]) + (f", and {names[-1]}" if len(names) > 1 else names[0])
        return f"Claude Code {joined} placement boundary"
    return "Claude Code extension placement boundary"


def _extension_boundary_context(concepts: list[tuple[str, str]]) -> str:
    if not concepts:
        return (
            "A Provider exchange separated Claude Code extension responsibilities "
            "by how each item is invoked, loaded, or applied."
        )
    concept_text = ", ".join(f"{name} as {role}" for name, role in concepts)
    return f"A Provider exchange separated {concept_text}."


def _extension_boundary_conclusion(concepts: list[tuple[str, str]]) -> str:
    if not concepts:
        return "Keep Claude Code extension concepts on separate placement axes unless source evidence supports merging them."
    clauses = [f"{name} = {role}" for name, role in concepts]
    return "Keep the mentioned Claude Code surfaces separate by placement role: " + "; ".join(clauses) + "."


def _generic_provider_exchange_memory_fields(*, user_text: str, assistant_text: str) -> dict[str, Any]:
    combined = f"{user_text}\n{assistant_text}"
    buckets = _stable_signal_buckets(combined)
    topic_buckets = [
        bucket
        for bucket in buckets
        if bucket not in {"durable-reuse", "role-boundary", "source-evidence"}
    ]
    digest_source = "|".join(topic_buckets or buckets) if buckets else " ".join(combined.lower().split())
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:10]
    answer_decision = _wiki_rule_from_provider_answer(assistant_text)
    if {"agent-taxonomy", "extension-placement"}.issubset(set(buckets)):
        canonical_topic_title = "Claude Code agent and extension placement boundary"
        topic_stem = "claude-code-agent-extension-placement-boundary"
        context = (
            "A Provider exchange separated execution-model choices, definition "
            "supply paths, automatic execution, model-readable procedures, external "
            "connections, and extension packaging."
        )
        conclusion = (
            "Keep agent execution models separate from agent definition supply paths, "
            "and keep Hook, Skill, MCP, and Plugin on their own placement axes."
        )
        reuse_condition = (
            "Use when team documentation needs to explain where agent, hook, skill, "
            "MCP, and plugin responsibilities belong without merging the axes."
        )
    elif "agent-taxonomy" in buckets:
        canonical_topic_title = "Claude Code agent execution and definition boundary"
        topic_stem = "claude-code-agent-boundary"
        context = (
            "A Provider exchange separated how agent work executes from where an "
            "agent definition is supplied."
        )
        conclusion = "Keep execution model and definition source as separate documentation axes."
        reuse_condition = "Use when a later question asks whether an agent concept is an execution model or a definition source."
    elif "extension-placement" in buckets:
        mentioned_concepts = _mentioned_claude_code_placement_concepts(combined)
        canonical_topic_title = _extension_topic_title(mentioned_concepts)
        topic_stem = "claude-code-extension-placement-boundary"
        context = _extension_boundary_context(mentioned_concepts)
        conclusion = _extension_boundary_conclusion(mentioned_concepts)
        reuse_condition = (
            "Use when team documentation revisits the same mentioned Claude Code surfaces "
            "and needs their placement roles kept separate."
        )
    elif "animal-ecology" in buckets:
        canonical_topic_title = "Domestic dog ecology and adjacent boundary map"
        topic_stem = "domestic-dog-ecology-boundary"
        context = (
            "A Provider exchange separated the ecological function of dog walking "
            "from adjacent breed-variation, welfare, and urban-ecology questions."
        )
        conclusion = (
            "Keep dog walking ecology, breed variation, training ethics, and urban wildlife impact "
            "as related but separate decision axes unless a later source explicitly bridges them."
        )
        reuse_condition = (
            "Use when a later question asks whether a dog-care detail belongs in domestic dog ecology, "
            "a breed-specific child topic, companion animal welfare, or urban animal ecology."
        )
    else:
        canonical_topic_title = "Provider durable reuse boundary"
        topic_stem = "provider-durable-reuse-boundary"
        context = (
            "A natural Provider exchange contained a reusable boundary or later-use signal. "
            "The Provider must keep the decision open and let MS1 classify the domain, "
            "community, maturity, and promotion path from source-backed evidence."
        )
        conclusion = (
            "Treat this as a source-ref-backed boundary candidate, not as native Provider memory "
            "and not as verified long-term storage."
        )
        reuse_condition = (
            "Use when a later question revisits the same bounded exchange and asks whether the "
            "criterion remained stable."
        )
    decision = _select_canonical_decision(
        answer_candidate=answer_decision,
        conclusion=conclusion,
    )
    return {
        "decision": decision,
        "context": context,
        "conclusion": conclusion,
        "reuse_condition": reuse_condition,
        "canonical_topic_title": canonical_topic_title,
        "canonical_topic_key": f"{topic_stem}-{digest}",
        "signal_buckets": buckets,
    }


def _should_request_domain_evidence(signal_buckets: list[str]) -> bool:
    domain_buckets = {
        "agent-taxonomy",
        "extension-placement",
        "automation-timing",
    }
    return bool(domain_buckets.intersection(signal_buckets))


def _attach_domain_evidence_request(
    payload: dict[str, Any],
    *,
    user_text: str,
    assistant_text: str,
    signal_buckets: list[str],
) -> None:
    if not _should_request_domain_evidence(signal_buckets):
        return
    payload["domain_evidence_request"] = build_domain_evidence_request(
        query_text=f"{user_text}\n{assistant_text}",
        signal_buckets=signal_buckets,
        minimum_external_sources=2,
        minimum_related_pages=1,
    )


def build_memory_ticket_payload_from_provider_exchange(
    *,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    user_text: str,
    assistant_text: str,
    sessions_dir: str | Path,
    category_community_hint: str = "provider-authored durable knowledge candidate / MS-classified community",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MemoryTicket from a natural Provider exchange when salience is sufficient."""

    salience = detect_provider_memory_salience(f"{user_text}\n{assistant_text}")
    if salience.get("trigger_decision") != "emit":
        return _memory_ticket_unavailable("provider_exchange_not_salient")
    fields = _generic_provider_exchange_memory_fields(user_text=user_text, assistant_text=assistant_text)
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
        surface_reason=str(salience.get("intent_field") or "Provider exchange contains a reusable boundary candidate."),
        intent_field=str(salience.get("intent_field") or "Provider exchange contains a reusable boundary candidate."),
        why_not_atomic=str(salience.get("why_not_atomic") or "The bounded exchange must stay intact until MS classifies it."),
        topic_hint=str(salience.get("topic_hint") or "provider reusable boundary candidate"),
        category_community_hint=str(salience.get("category_community_hint") or category_community_hint),
        decision=fields["decision"],
        context=fields["context"],
        conclusion=fields["conclusion"],
        trigger_kind=str(salience.get("trigger_kind") or "category_community_shift"),
        min_split_unit="topic_decision_cluster",
        breadcrumb=str(salience.get("breadcrumb") or ""),
        reuse_condition=fields["reuse_condition"],
        canonical_topic_title=fields["canonical_topic_title"],
        canonical_topic_key=fields["canonical_topic_key"],
    )
    payload["admission_bridge"] = {
        "schema_version": "provider_exchange_admission_bridge.v1",
        "salience_trigger_kind": salience.get("trigger_kind"),
        "distillation_status": "generic_evidence_bound_boundary_candidate",
        "topic_specific_runtime_branch": False,
        "raw_provider_material_included": False,
        "postman_semantic_quality_owner": False,
    }
    _attach_domain_evidence_request(
        payload,
        user_text=user_text,
        assistant_text=assistant_text,
        signal_buckets=list(fields.get("signal_buckets") or []),
    )
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
    category_community_hint: str = "provider-authored durable knowledge candidate / MS-classified community",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MemoryTicket from a salient Provider range without copying the session."""

    salience = detect_provider_memory_salience(f"{user_text}\n{assistant_text}")
    if salience.get("trigger_decision") != "emit":
        return _memory_ticket_unavailable("provider_exchange_not_salient")
    fields = _generic_provider_exchange_memory_fields(user_text=user_text, assistant_text=assistant_text)
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
        surface_reason=str(salience.get("intent_field") or "Provider exchange contains a reusable boundary candidate."),
        intent_field=str(salience.get("intent_field") or "Provider exchange contains a reusable boundary candidate."),
        why_not_atomic=str(salience.get("why_not_atomic") or "The bounded exchange must stay intact until MS classifies it."),
        topic_hint=str(salience.get("topic_hint") or "provider reusable boundary candidate"),
        category_community_hint=str(salience.get("category_community_hint") or category_community_hint),
        decision=fields["decision"],
        context=fields["context"],
        conclusion=fields["conclusion"],
        trigger_kind=str(salience.get("trigger_kind") or "category_community_shift"),
        min_split_unit="topic_decision_cluster",
        breadcrumb=str(salience.get("breadcrumb") or ""),
        reuse_condition=fields["reuse_condition"],
        canonical_topic_title=fields["canonical_topic_title"],
        canonical_topic_key=fields["canonical_topic_key"],
    )
    payload["admission_bridge"] = {
        "schema_version": "provider_exchange_admission_bridge.v1",
        "salience_trigger_kind": salience.get("trigger_kind"),
        "distillation_status": "generic_evidence_bound_boundary_candidate",
        "topic_specific_runtime_branch": False,
        "raw_provider_material_included": False,
        "postman_semantic_quality_owner": False,
        "existing_provider_session_range": True,
    }
    _attach_domain_evidence_request(
        payload,
        user_text=user_text,
        assistant_text=assistant_text,
        signal_buckets=list(fields.get("signal_buckets") or []),
    )
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
    trigger_kind: str = "explicit_user_save_command",
    min_split_unit: str = "paragraph_intent",
    breadcrumb: str = "",
    context: str = "",
    conclusion: str = "",
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
    "ALLOWED_SOURCE_REF_SCHEMES",
    "build_existing_provider_exchange_current_source_bridge",
    "build_memory_ticket_payload_from_existing_provider_exchange",
    "build_memory_ticket_payload_from_provider_exchange",
    "build_memory_ticket_payload_from_current_source",
    "build_provider_exchange_current_source_bridge",
    "build_provider_current_source_bridge",
]
