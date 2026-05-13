from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from runtime.common.portable_ref import looks_like_local_path
from source_ref.hermes_session_json import resolve_hermes_session_json_source_ref


SCHEMA_VERSION = "recall_digest.v1"
CLAUDE_SMOKE_COMMANDS = (
    "claude --version",
    "claude doctor",
    "claude auth status",
    "/help",
    "/exit",
    "claude -p",
)
HARD_NONCLAIMS = {
    "raw_transcript_exposed": False,
    "chain_of_thought_exposed": False,
    "local_runtime_execution_proven": False,
    "full_docs_taxonomy_claimed": False,
    "full_ux_passed": False,
}


def _default_sessions_dir() -> Path:
    configured = os.environ.get("YGG_HERMES_SESSIONS_DIR") or os.environ.get("HERMES_SESSIONS_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".hermes" / "sessions"


def _clean_text(value: Any, *, max_length: int = 800) -> str:
    return " ".join(str(value or "").strip().split())[:max_length]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    if isinstance(content, Mapping):
        return "\n".join(str(value) for value in content.values() if isinstance(value, str))
    return ""


def _messages_text(messages: list[Mapping[str, Any]], *, role: str | None = None) -> str:
    parts: list[str] = []
    for message in messages:
        if role and str(message.get("role") or "") != role:
            continue
        text = _content_to_text(message.get("content"))
        if text:
            parts.append(text)
    return "\n".join(parts)


def _coerce_range(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        start = int(value.get("start"))
        end = int(value.get("end"))
    except (TypeError, ValueError):
        return None
    if start < 0 or end < start:
        return None
    return {"start": start, "end": end}


def _portable_source_paths(values: Any) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _clean_text(value, max_length=320).replace("\\", "/")
        if not text or looks_like_local_path(text) or text in seen:
            continue
        paths.append(text)
        seen.add(text)
        if len(paths) >= 12:
            break
    return paths


def _support_fact_text(values: Any) -> str:
    parts: list[str] = []
    for value in values or ():
        if isinstance(value, Mapping):
            parts.append(str(value.get("support_fact") or value.get("subject") or ""))
        else:
            parts.append(str(value or ""))
    return "\n".join(parts)


def _domain_profile(text: str) -> str:
    hay = text.lower()
    if "claude" in hay and any(token in hay for token in ("hook", "usermpromptsubmit", "userpromptsubmit", "posttooluse", "pretooluse", "sessionstart")):
        return "claude_code_hooks"
    if "claude" in hay and any(token in hay for token in ("subagent", "sub-agent", "isolated context", "task tool")):
        return "claude_code_subagents"
    if "claude" in hay and any(token in hay for token in ("claude.md", "auto memory", ".claude/rules", "memory")):
        return "claude_code_memory"
    if "claude" in hay and "mcp" in hay:
        return "claude_code_mcp"
    if "claude" in hay and any(token in hay for token in ("skill", "skills", "extension")):
        return "claude_code_extensions"
    if "claude" in hay and any(token in hay for token in ("smoke", "doctor", "quickstart", "install", "auth status")):
        return "claude_code_smoke"
    if "claude" in hay:
        return "claude_code_docs"
    return "general_recall"


def _domain_profile_from_topic_key(topic_key: str | None) -> str | None:
    key = str(topic_key or "").lower()
    if not key:
        return None
    if "smoke" in key or "first-run" in key or "quickstart" in key:
        return "claude_code_smoke"
    if "hooks" in key or "event-automation" in key:
        return "claude_code_hooks"
    if "subagent" in key or "isolated-context" in key or "isolated-worker" in key:
        return "claude_code_subagents"
    if "mcp" in key or "external-tool-transport" in key:
        return "claude_code_mcp"
    if "memory" in key or "context-window-safe-recall" in key or "safe-recall" in key:
        return "claude_code_memory"
    if "skill" in key or "reusable-guidance" in key:
        return "claude_code_extensions"
    if "claude-code" in key:
        return "claude_code_docs"
    return None


def _scope_profile(text: str, query_text: str) -> str:
    hay = f"{text}\n{query_text}".lower()
    if any(token in hay for token in ("hook", "usermpromptsubmit", "userpromptsubmit", "posttooluse", "pretooluse", "sessionstart")):
        return "event_automation"
    if any(token in hay for token in ("subagent", "sub-agent", "isolated context", "task tool")):
        return "isolated_worker"
    if any(token in hay for token in ("claude.md", "auto memory", ".claude/rules")):
        return "persistent_memory"
    if "mcp" in hay:
        return "external_tool_connection"
    if any(token in hay for token in ("skill", "skills", "extension")):
        return "extension_choice"
    if "first project" in hay or "new project" in hay:
        return "first_project_smoke"
    if "install" in hay or "doctor" in hay or "auth status" in hay:
        return "install_smoke"
    if "taxonomy" in hay or "docs tree" in hay:
        return "docs_taxonomy"
    return "bounded_recall"


def _command_hits(text: str) -> list[str]:
    hay = text.lower()
    return [command for command in CLAUDE_SMOKE_COMMANDS if command.lower() in hay]


def _unavailable_digest(
    *,
    reason_code: str,
    source_ref: str = "",
    message_index_range: dict[str, int] | None = None,
    source_line_range: Mapping[str, Any] | None = None,
    topic_key: str | None = None,
    ring_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "typed_unavailable",
        "reason_code": reason_code,
        "topic_key": topic_key,
        "ring_id": ring_id,
        "rehydration": {
            "status": "typed_unavailable",
            "reason_code": reason_code,
            "source_ref": source_ref,
            "message_index_range": message_index_range,
            "source_line_range": dict(source_line_range or {}),
            "raw_transcript_included": False,
            "digest_only": True,
        },
        "raw_transcript_included": False,
        "digest_only": True,
        "hard_nonclaims": dict(HARD_NONCLAIMS),
    }


def build_recall_digest(
    *,
    query_text: str,
    source_ref: str,
    message_index_range: Mapping[str, Any] | None,
    anchor_hash: str,
    source_line_range: Mapping[str, Any] | None = None,
    paragraph_intent_safety_belt: Mapping[str, Any] | None = None,
    support_facts: Any = None,
    source_paths: Any = None,
    topic_key: str | None = None,
    ring_id: str | None = None,
    provider_session_id: str | None = None,
    sessions_dir: str | Path | None = None,
) -> dict[str, Any]:
    bounded_range = _coerce_range(message_index_range)
    if not source_ref or not bounded_range or not anchor_hash:
        return _unavailable_digest(
            reason_code="source_ref_pointer_missing",
            source_ref=source_ref,
            message_index_range=bounded_range,
            source_line_range=source_line_range,
            topic_key=topic_key,
            ring_id=ring_id,
        )

    resolved = resolve_hermes_session_json_source_ref(
        source_ref=source_ref,
        message_index_range=bounded_range,
        sessions_dir=Path(sessions_dir) if sessions_dir else _default_sessions_dir(),
        anchor_hash=anchor_hash,
    )
    if resolved.get("status") != "resolved":
        reason = _clean_text(resolved.get("reason") or resolved.get("status") or "source_ref_unavailable", max_length=120)
        return _unavailable_digest(
            reason_code=f"source_ref_{reason}",
            source_ref=source_ref,
            message_index_range=bounded_range,
            source_line_range=source_line_range,
            topic_key=topic_key,
            ring_id=ring_id,
        )

    messages = [dict(row) for row in resolved.get("messages") or [] if isinstance(row, Mapping)]
    user_text = _messages_text(messages, role="user")
    all_text = "\n".join(
        [
            _messages_text(messages),
            _support_fact_text(support_facts),
            _support_fact_text((paragraph_intent_safety_belt or {}).values()),
            query_text,
        ]
    )
    domain = _domain_profile_from_topic_key(topic_key) or _domain_profile(all_text)
    scope = _scope_profile(all_text, query_text)
    commands = _command_hits(all_text)

    if domain == "claude_code_smoke":
        past_user_intent = (
            "Recover the prior Claude Code operational smoke-test rule: answer the smallest "
            "install or first-run checks before broad documentation mapping."
        )
        include = [
            "Claude Code install or first-run health checks",
            "official-docs route hints only when they improve the narrow answer",
            "minimal command-level smoke sequence",
        ]
        exclude = [
            "full documentation taxonomy",
            "unverified local execution claim",
            "raw transcript replay",
        ]
        decision = [
            "Reuse the stored smoke route before expanding the answer.",
            "Keep docs taxonomy out unless the user asks for a broad map.",
        ]
        if commands:
            decision.append("Recovered smoke commands: " + ", ".join(commands[:6]))
        reasons = [
            "The stored range preserved a reusable user-proxy rule, not a raw dialogue dump.",
            "The current answer should compare the new question against that stored boundary.",
        ]
    elif domain == "claude_code_hooks":
        past_user_intent = (
            "Recover the prior Claude Code hooks rule: use hooks for deterministic lifecycle "
            "automation that must fire on matching events, not for reasoning-heavy reference material."
        )
        include = [
            "lifecycle-event automation",
            "PreToolUse/PostToolUse/UserPromptSubmit/SessionStart style triggers",
            "hook-vs-skill boundary",
        ]
        exclude = [
            "turning hooks into a reasoning workflow",
            "claiming hooks validate semantic correctness by themselves",
            "raw transcript replay",
        ]
        decision = [
            "Use a hook when the behavior must run every time on an event.",
            "Use a skill when Claude should reason over reference material or a workflow.",
        ]
        reasons = [
            "The stored range distinguished deterministic event triggers from model-interpreted instructions.",
            "The current answer should recover that boundary before recommending an extension surface.",
        ]
    elif domain == "claude_code_subagents":
        past_user_intent = (
            "Recover the prior Claude Code subagent rule: use subagents for isolated context, "
            "specialized workers, and side work whose intermediate context should not pollute the main turn."
        )
        include = [
            "isolated worker context",
            "summary returned to the main conversation",
            "parallel or specialized task boundary",
        ]
        exclude = [
            "using subagents as always-on project memory",
            "confusing subagents with independent agent teams",
            "raw transcript replay",
        ]
        decision = [
            "Use a subagent when isolation or bounded side work matters.",
            "Keep main-session context clean by returning only the result summary.",
        ]
        reasons = [
            "The stored range preserved the context-isolation purpose of subagents.",
            "The current answer should not collapse subagents into hooks, MCP, or skills.",
        ]
    elif domain == "claude_code_memory":
        past_user_intent = (
            "Recover the prior Claude Code memory rule: CLAUDE.md is always-on instruction context, "
            "auto memory captures learned notes, and path-scoped rules reduce context noise."
        )
        include = [
            "CLAUDE.md as persistent instruction context",
            "auto memory as Claude-written learnings",
            ".claude/rules path scoping and context-cost boundary",
        ]
        exclude = [
            "treating memory files as enforced configuration",
            "placing large reference material in always-on memory",
            "raw transcript replay",
        ]
        decision = [
            "Put always-needed conventions in CLAUDE.md.",
            "Move optional reference material or repeated procedures to skills or scoped rules.",
        ]
        reasons = [
            "The stored range separated persistent context from enforcement and on-demand knowledge.",
            "The current answer should preserve context-cost and specificity boundaries.",
        ]
    elif domain == "claude_code_mcp":
        past_user_intent = (
            "Recover the prior Claude Code MCP rule: MCP connects Claude to external tools and data, "
            "while skills teach Claude how to use that capability well."
        )
        include = [
            "external service or tool connection",
            "MCP server capability boundary",
            "skill-plus-MCP pairing",
        ]
        exclude = [
            "treating MCP as a documentation memory surface",
            "using skills as actual external tool transport",
            "raw transcript replay",
        ]
        decision = [
            "Use MCP for external data/actions.",
            "Use skills to document how to use those MCP-backed tools effectively.",
        ]
        reasons = [
            "The stored range preserved the transport-vs-knowledge boundary.",
            "The current answer should avoid collapsing MCP into skills.",
        ]
    elif domain.startswith("claude_code"):
        past_user_intent = (
            "Recover the prior Claude Code extension-selection rule: choose CLAUDE.md, skills, MCP, "
            "subagents, hooks, and plugins by load timing, context cost, and determinism."
        )
        include = [
            "extension choice by job-to-be-done",
            "context loading and context-cost trade-off",
            "deterministic automation versus model-interpreted knowledge",
        ]
        exclude = [
            "one-extension-fits-all advice",
            "collapsing hooks, skills, MCP, and subagents into the same category",
            "raw transcript replay",
        ]
        decision = [
            "Choose CLAUDE.md for always-on conventions.",
            "Choose skills for on-demand knowledge/workflows.",
            "Choose MCP for external services, subagents for isolated workers, and hooks for deterministic event automation.",
        ]
        reasons = [
            "The stored range preserved extension boundaries instead of copying a docs table.",
            "The current answer should map the user need to the right extension surface.",
        ]
    else:
        past_user_intent = "Recover the prior bounded user intent before answering the current question."
        include = ["prior intent", "prior scope boundary", "prior decision and evidence pointers"]
        exclude = ["raw transcript replay", "unverified completion claim"]
        decision = ["Use the recovered boundary to answer with higher resolution."]
        reasons = ["The source_ref range was rehydrated and distilled into answer-facing memory."]

    query_lower = query_text.lower()
    same_domain = domain.startswith("claude_code") and "claude" in query_lower
    if same_domain and scope == "first_project_smoke":
        scope_delta = "same_domain_with_narrower_first_project_scope"
        alignment = (
            "The current question stays in the Claude Code smoke-test family but asks for first-project "
            "startup checks, so reuse the health-check rule and add project-entry checks only."
        )
    elif same_domain:
        scope_delta = "same_domain_same_smoke_family"
        alignment = "The current question matches the stored Claude Code smoke-test family."
    else:
        scope_delta = "requires_provider_judgment"
        alignment = "The digest gives prior memory, but the Provider still has to judge current-question fit."

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available",
        "topic_key": topic_key,
        "ring_id": ring_id,
        "rehydration": {
            "status": "resolved",
            "source_ref": source_ref,
            "origin_locator": resolved.get("origin_locator"),
            "provider_session_id": provider_session_id or resolved.get("provider_session_id"),
            "message_index_range": bounded_range,
            "source_line_range": dict(source_line_range or {}),
            "anchor_hash_verified": True,
            "raw_transcript_included": False,
            "digest_only": True,
        },
        "past_user_intent": past_user_intent,
        "past_scope_boundary": {
            "include": include,
            "exclude": exclude,
        },
        "past_decision": decision,
        "past_reasons": reasons,
        "current_question_alignment": {
            "same_domain": bool(same_domain),
            "scope_delta": scope_delta,
            "provider_action": "compare_current_question_to_recall_digest_before_final_answer",
            "summary": alignment,
        },
        "answer_resolution_upgrade": [
            "Start from the recovered intent and boundary before answering.",
            "Use source pointers as evidence, but do not print the raw transcript.",
            "If the current question asks for broader coverage than the stored range, state the gap.",
        ],
        "unresolved_gaps": [
            "This digest does not prove the commands were executed in the local runtime.",
            "This digest does not prove the full Claude Code documentation tree was ingested.",
        ],
        "evidence_refs": {
            "source_ref": source_ref,
            "origin_locator": resolved.get("origin_locator"),
            "message_index_range": bounded_range,
            "source_line_range": dict(source_line_range or {}),
            "anchor_hash_verified": True,
            "topic_key": topic_key,
            "ring_id": ring_id,
            "source_paths": _portable_source_paths(source_paths),
        },
        "quality_signals": {
            "domain_profile": domain,
            "scope_profile": scope,
            "rehydrated_message_count": len(messages),
            "rehydrated_user_message_count": sum(1 for row in messages if row.get("role") == "user"),
            "past_user_signal_present": bool(user_text.strip()),
            "support_fact_count": len(list(support_facts or ())),
            "raw_transcript_included": False,
            "digest_only": True,
        },
        "raw_transcript_included": False,
        "digest_only": True,
        "hard_nonclaims": dict(HARD_NONCLAIMS),
    }


def build_recall_digest_from_support_bundle(
    *,
    query_text: str,
    support_bundle: Mapping[str, Any],
    sessions_dir: str | Path | None = None,
) -> dict[str, Any]:
    return build_recall_digest(
        query_text=query_text,
        source_ref=str(support_bundle.get("source_ref") or ""),
        message_index_range=support_bundle.get("message_index_range") if isinstance(support_bundle.get("message_index_range"), Mapping) else None,
        source_line_range=support_bundle.get("source_line_range") if isinstance(support_bundle.get("source_line_range"), Mapping) else None,
        anchor_hash=str(support_bundle.get("anchor_hash") or ""),
        paragraph_intent_safety_belt=support_bundle.get("paragraph_intent_safety_belt")
        if isinstance(support_bundle.get("paragraph_intent_safety_belt"), Mapping)
        else None,
        support_facts=support_bundle.get("support_facts") or (),
        source_paths=support_bundle.get("source_paths") or (),
        topic_key=str(support_bundle.get("topic_key") or "") or None,
        ring_id=str(support_bundle.get("ring_id") or "") or None,
        provider_session_id=str(support_bundle.get("provider_session_id") or "") or None,
        sessions_dir=sessions_dir,
    )


__all__ = [
    "SCHEMA_VERSION",
    "build_recall_digest",
    "build_recall_digest_from_support_bundle",
]
