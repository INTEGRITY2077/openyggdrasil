from __future__ import annotations

from typing import Any

CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _has_explicit_save_command(text: str, lowered: str) -> bool:
    return _contains_any(lowered, ("remember this", "save this", "store this")) or _contains_any(
        text,
        ("기억해", "기억해줘", "저장해", "저장해줘", "보존해", "보존해줘"),
    )


def _has_durable_reuse_signal(text: str, lowered: str) -> bool:
    return _contains_any(
        lowered,
        (
            "use this later",
            "reuse this later",
            "later reuse",
            "need this later",
            "stable boundary",
            "will need this",
        ),
    ) or _contains_any(
        text,
        (
            "계속 다시",
            "나중에",
            "다시 쓸",
            "재사용",
            "헷갈리지 않게",
            "바뀐 부분",
            "기준으로 구분",
        ),
    )


def _has_reusable_boundary_signal(text: str, lowered: str) -> bool:
    lower_signals = (
        "boundary",
        "criterion",
        "criteria",
        "policy",
        "rule",
        "placement",
        "distinction",
        "separate",
        "split",
        "where",
        "where to place",
        "belongs",
        "convention",
        "conventions",
        "role",
        "roles",
        "runtime",
        "execution",
        "definition",
        "distribution",
        "timing",
        "automatic",
        "lifecycle",
        "event",
        "formatting",
        "reuse",
        "later",
        "proof",
        "source",
        "evidence",
        "claim",
        "production ready",
        "unsupported",
    )
    text_signals = (
        "경계",
        "기준",
        "구분",
        "분리",
        "실행",
        "정의",
        "위치",
        "자동",
        "이벤트",
        "규칙",
        "정책",
        "어디",
        "배치",
        "근거",
        "출처",
        "검증",
        "증명",
        "주장",
        "헷갈",
        "위키",
        "나중",
    )
    hits = sum(1 for signal in lower_signals if signal in lowered)
    hits += sum(1 for signal in text_signals if signal in text)
    return hits >= 2


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
    """Detect whether a Provider exchange deserves MS admission review.

    This function does not decide storage and does not classify domain topics.
    It only detects reusable boundary, placement, evidence, and later-use
    signals so MS can judge maturity from source-backed context.
    """

    text = (paragraph or "").strip()
    if not text:
        return {"trigger_decision": "defer", "trigger_kind": "none", "reason": "empty_paragraph"}
    lowered = text.lower()

    if _contains_any(lowered, ("decision atom", "paragraph-level intent", "authoring bridge")) and _contains_any(
        lowered,
        ("category/community", "community"),
    ):
        return _base_emit(
            paragraph=text,
            trigger_kind="topic_decision_completed",
            intent_field="The exchange completes a paragraph-level topic decision for category/community authoring.",
            topic_hint="provider paragraph intent authoring bridge",
            category_community_hint="provider-authored durable knowledge candidate / authoring bridge",
            breadcrumb="Preserve paragraph-level intent before extracting decision atoms.",
            why_not_atomic="The authoring rule depends on paragraph scope, category/community placement, and anti-atomization.",
        )

    if _has_durable_reuse_signal(text, lowered) and not _has_explicit_save_command(text, lowered):
        return _base_emit(
            paragraph=text,
            trigger_kind="durable_reuse_signal",
            intent_field="The exchange contains a durable reuse signal but not an explicit save command.",
            topic_hint="durable reuse boundary candidate",
            category_community_hint="provider-authored durable knowledge candidate / durable reuse signal",
            breadcrumb=(
                "A later-use signal should enter episode-ledger admission instead of being "
                "treated as a direct save command."
            ),
            why_not_atomic="The reuse need, scope, and uncertainty must stay together until MS judges maturity.",
        )

    if _has_explicit_save_command(text, lowered):
        return _base_emit(
            paragraph=text,
            trigger_kind="explicit_user_save_command",
            intent_field="The user indicated this may be needed later.",
            topic_hint="explicit durable memory candidate",
            category_community_hint="provider-authored durable knowledge candidate / explicit request",
            breadcrumb="A later-use signal should enter source_ref-backed admission instead of being claimed as stored.",
            why_not_atomic="The reason, scope, and reuse condition matter together; a single preference atom would lose the boundary.",
        )

    if _has_reusable_boundary_signal(text, lowered):
        return _base_emit(
            paragraph=text,
            trigger_kind="category_community_shift",
            intent_field=(
                "The exchange contains a reusable boundary, placement, evidence, "
                "or claim-control signal that needs MS judgment before storage."
            ),
            topic_hint="provider reusable boundary candidate",
            category_community_hint="provider-authored durable knowledge candidate / MS-classified community",
            breadcrumb=(
                "Provider should preserve the bounded exchange and let MS classify the domain, "
                "community, maturity, and promotion path from evidence."
            ),
            why_not_atomic=(
                "The reusable rule, uncertainty, evidence threshold, and later-use condition "
                "must stay together until MS classifies the topic."
            ),
        )

    return {
        "trigger_decision": "defer",
        "trigger_kind": "none",
        "reason": "no_long_term_retrieval_salience",
        "source_ref_status": "placeholder",
    }


__all__ = ["CANONICAL_DECOMPOSITION_GUARD", "detect_provider_memory_salience"]
