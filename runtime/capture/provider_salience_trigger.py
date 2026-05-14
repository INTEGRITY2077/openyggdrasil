from __future__ import annotations

from typing import Any

CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _base_emit(
    *,
    paragraph: str,
    trigger_kind: str,
    intent_field: str,
    topic_hint: str,
    category_community_hint: str,
    breadcrumb: str,
    why_not_atomic: str,
    canonical_topic_key: str = "",
    canonical_topic_title: str = "",
) -> dict[str, Any]:
    return {
        "trigger_decision": "emit",
        "trigger_kind": trigger_kind,
        "intent_field": intent_field,
        "decomposition_guard": CANONICAL_DECOMPOSITION_GUARD,
        "min_split_unit": "paragraph_intent",
        "why_not_atomic": why_not_atomic,
        "topic_hint": topic_hint,
        "category_community_hint": category_community_hint,
        "breadcrumb": breadcrumb,
        "canonical_topic_key": canonical_topic_key,
        "canonical_topic_title": canonical_topic_title,
        "recency_anchor": "current_exchange",
        "why_this_topic_matters": (
            "The rule can change later Provider behavior, documentation placement, "
            "or recall entrypoint selection."
        ),
        "source_ref_status": "placeholder",
        "source_ref_required": True,
        "paragraph_intent_field": paragraph,
    }


def detect_provider_memory_salience(paragraph: str) -> dict[str, Any]:
    """Detect whether a Provider exchange deserves memory admission review.

    This function does not decide storage. It only flags durable, reusable,
    source-ref-worthy boundaries so the admission path can ask MS to judge them.
    Ordinary tone preference, one-off status, and unsupported self-claims stay
    out of OpenYggdrasil.
    """

    text = (paragraph or "").strip()
    if not text:
        return {"trigger_decision": "defer", "trigger_kind": "none", "reason": "empty_paragraph"}
    lowered = text.lower()

    if _contains_any(lowered, ("remember this", "save this", "store this")) or _contains_any(
        text,
        ("기억해", "기억해줘", "저장해", "저장해줘", "나중에 다시", "다음에 다시", "앞으로 다시"),
    ):
        return _base_emit(
            paragraph=text,
            trigger_kind="explicit_user_save_command",
            intent_field="The user indicated this may be needed later.",
            topic_hint="explicit durable memory candidate",
            category_community_hint="OpenYggdrasil provider behavior contract / memory authoring bridge",
            breadcrumb="A later-use signal should enter source_ref-backed admission instead of being claimed as stored.",
            why_not_atomic="The reason, scope, and reuse condition matter together; a single preference atom would lose the boundary.",
        )

    if _contains_any(text, ("OpenYggdrasil", "Hermes", "Provider")) and _contains_any(
        text,
        ("책임 경계", "역할 경계", "복제", "위키", "출처", "근거", "native memory", "기본 기억"),
    ):
        return _base_emit(
            paragraph=text,
            trigger_kind="boundary_correction",
            intent_field=(
                "The exchange defines the boundary between Provider native memory "
                "and OpenYggdrasil evidence-backed wiki memory."
            ),
            topic_hint="OpenYggdrasil and Provider/Hermes memory boundary",
            category_community_hint="OpenYggdrasil memory architecture community / provider memory boundary",
            breadcrumb="Provider/Hermes/OpenYggdrasil boundary corrections should stay reusable across provider lanes.",
            why_not_atomic="The roles, forbidden claims, evidence scope, and reuse condition must stay together.",
            canonical_topic_key="openyggdrasil-hermes-memory-boundary",
            canonical_topic_title="OpenYggdrasil and Hermes memory boundary",
        )

    if _contains_any(text, ("README", "공개 문서", "public doc", "공개 README")) and _contains_any(
        text,
        (
            "내부어",
            "내부 세션",
            "과거 명령",
            "호환명",
            "legacy",
            "proof",
            "run",
            "phase",
            "receipt",
            "mailbox",
            "tmux",
            "affordance",
            "공식 사용",
        ),
    ):
        return _base_emit(
            paragraph=text,
            trigger_kind="reusable_operational_rule",
            intent_field="The exchange defines a reusable public README surface rule.",
            topic_hint="public README affordance boundary",
            category_community_hint="OpenYggdrasil public documentation governance / README affordance boundary",
            breadcrumb=(
                "Public-facing docs should not expose internal lane names, legacy aliases, "
                "proof/run labels, or mailbox mechanics as product API."
            ),
            why_not_atomic="The rule combines audience, exposed surface, hidden internals, exceptions, and failure cases.",
            canonical_topic_key="public-readme-affordance-boundary",
            canonical_topic_title="Public README affordance boundary",
        )

    if _contains_any(text, ("CLAUDE.md", "auto memory", "Hook", "Skill", "MCP", "Plugin")) and _contains_any(
        text,
        ("기준", "갈라", "어디에 둬야", "선택", "팀 문서", "오해", "placement", "boundary"),
    ):
        return _base_emit(
            paragraph=text,
            trigger_kind="category_community_shift",
            intent_field="The exchange forms reusable Claude Code documentation placement criteria.",
            topic_hint="Claude Code extension placement criteria",
            category_community_hint="Claude Code documentation boundary / extension placement criteria",
            breadcrumb=(
                "The user prefers placement criteria over definitions when distinguishing "
                "CLAUDE.md, auto memory, Hook, Skill, MCP, and Plugin."
            ),
            why_not_atomic="The distinctions work as a comparative matrix; splitting them into isolated terms loses the placement rule.",
            canonical_topic_key="claude-code-extension-placement-criteria",
            canonical_topic_title="Claude Code extension placement criteria",
        )

    if _contains_any(text, ("README", "PRODUCTION READY", "100%", "검증", "mock", "demo", "과장")):
        return _base_emit(
            paragraph=text,
            trigger_kind="strong_memory_stimulus",
            intent_field="Unverified README, Production Ready, or 100% claims are prohibited.",
            topic_hint="README claim gating and proof discipline",
            category_community_hint="OpenYggdrasil verification governance / provider behavior contract",
            breadcrumb="Facing claims may be promoted only after code and live workflow evidence agree.",
            why_not_atomic="The claim, evidence threshold, and prohibited wording must stay together.",
            canonical_topic_key="readme-claim-gating-proof-discipline",
            canonical_topic_title="README claim gating and proof discipline",
        )

    return {
        "trigger_decision": "defer",
        "trigger_kind": "none",
        "reason": "no_long_term_retrieval_salience",
        "source_ref_status": "placeholder",
    }


__all__ = ["CANONICAL_DECOMPOSITION_GUARD", "detect_provider_memory_salience"]
