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


def _has_explicit_save_command(text: str, lowered: str) -> bool:
    return _contains_any(lowered, ("remember this", "save this", "store this")) or _contains_any(
        text,
        (
            "\uae30\uc5b5\ud574",
            "\uae30\uc5b5\ud574\uc918",
            "\uc800\uc7a5\ud574",
            "\uc800\uc7a5\ud574\uc918",
            "\ubcf4\uc874\ud574",
            "\ubcf4\uc874\ud574\uc918",
        ),
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
            "next time",
        ),
    ) or _contains_any(
        text,
        (
            "\uacc4\uc18d \ub2e4\uc2dc",
            "\ub098\uc911\uc5d0",
            "\ub2e4\uc2dc",
            "\uc7ac\uc0ac\uc6a9",
            "\ud5f7\uac08\ub9ac\uc9c0 \uc54a\uac8c",
            "\ubc14\ub010 \ubd80\ubd84",
            "\uae30\uc900\uc73c\ub85c",
            "\uc720\uc9c0",
            "\ud754\ub4e4\ub9ac\uc9c0",
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
        "\uacbd\uacc4",
        "\uae30\uc900",
        "\uad6c\ubd84",
        "\ubd84\ub9ac",
        "\uc2e4\ud589",
        "\uc2e4\ud589 \ub2e8\uc704",
        "\uc815\uc758",
        "\uacf5\uae09",
        "\uacf5\uae09 \uacbd\ub85c",
        "\ubc30\uce58",
        "\ubc30\ud3ec",
        "\uc790\ub3d9",
        "\uc774\ubca4\ud2b8",
        "\uaddc\uce59",
        "\uc815\ucc45",
        "\uc5b4\ub514",
        "\uc704\uce58",
        "\uadfc\uac70",
        "\ucd9c\ucc98",
        "\uac80\uc99d",
        "\uc99d\uba85",
        "\uc8fc\uc7a5",
        "\ud5f7\uac08",
        "\uc704\ud0a4",
        "\ub098\uc911",
        "\uc12c\uc9c0",
        "\uc11e\uc9c0",
    )
    hits = sum(1 for signal in lower_signals if signal in lowered)
    hits += sum(1 for signal in text_signals if signal in text)
    return hits >= 2


def _has_instruction_boundary_correction_signal(text: str, lowered: str) -> bool:
    explicit_boundary_phrases = (
        "not the trigger",
        "not a command",
        "not an instruction",
        "not a prompt",
        "storage trigger",
        "save trigger",
        "memory trigger",
        "\uc800\uc7a5 \ud2b8\ub9ac\uac70",
        "\uae30\uc5b5 \ud2b8\ub9ac\uac70",
        "\uba85\ub839\uc774 \uc544\ub2c8",
        "\uc9c0\uc2dc\uac00 \uc544\ub2c8",
    )
    if _contains_any(lowered, explicit_boundary_phrases) or _contains_any(text, explicit_boundary_phrases):
        return True

    instruction_terms = ("command", "instruction", "trigger", "forced", "force")
    korean_terms = ("\uba85\ub839", "\uc9c0\uc2dc", "\ud2b8\ub9ac\uac70", "\ud2b8\ub9ac\uae45", "\uac15\uc81c")
    autonomy_terms = (
        "autonomous",
        "self-detect",
        "salience",
        "\uc2a4\uc2a4\ub85c",
        "\uc790\uc728",
        "\ud544\uc694\uc131",
        "\ubd84\ub9ac",
    )
    has_instruction = _contains_any(lowered, instruction_terms) or _contains_any(text, korean_terms)
    has_autonomy_boundary = _contains_any(lowered, autonomy_terms) or _contains_any(text, autonomy_terms)
    memory_surface_terms = (
        "memory",
        "storage",
        "save",
        "provider",
        "openyggdrasil",
        "\uae30\uc5b5",
        "\uc800\uc7a5",
        "\ubcf4\uc874",
    )
    has_memory_surface = _contains_any(lowered, memory_surface_terms) or _contains_any(text, memory_surface_terms)
    return has_instruction and has_autonomy_boundary and has_memory_surface


def _has_verification_gated_claim_signal(text: str, lowered: str) -> bool:
    claim_terms = (
        "production ready",
        "production-ready",
        "release ready",
        "ship",
        "shipping",
        "deploy",
        "deployment",
    )
    korean_claim_terms = (
        "\ud504\ub85c\ub355\uc158",
        "\ucd9c\uc2dc",
    )
    verification_terms = (
        "verify",
        "verified",
        "evidence",
        "proof",
        "gate",
        "claim",
    )
    korean_verification_terms = (
        "\uac80\uc99d",
        "\ud655\uc778",
        "\uadfc\uac70",
        "\uc99d\uac70",
        "\uc99d\uba85",
        "\uac8c\uc774\ud2b8",
    )
    has_claim = _contains_any(lowered, claim_terms) or _contains_any(text, korean_claim_terms)
    has_verification = _contains_any(lowered, verification_terms) or _contains_any(text, korean_verification_terms)
    return has_claim and has_verification


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
            category_community_hint="provider-authored durable knowledge candidate / category/community authoring bridge",
            breadcrumb="Preserve paragraph-level intent before extracting decision atoms.",
            why_not_atomic="The authoring rule depends on paragraph scope, category/community placement, and anti-atomization.",
        )

    if _has_instruction_boundary_correction_signal(text, lowered):
        return _base_emit(
            paragraph=text,
            trigger_kind="boundary_correction",
            intent_field=(
                "The exchange corrects that user instructions are not the storage trigger; "
                "the Provider autonomous salience trigger must detect its own need."
            ),
            topic_hint="Provider autonomous salience trigger",
            category_community_hint="OpenYggdrasil provider behavior contract / memory authoring bridge",
            breadcrumb="Provider autonomous salience trigger must stay separate from explicit user commands.",
            why_not_atomic="The command boundary, autonomous trigger, and provider responsibility must remain together.",
        )

    if _has_verification_gated_claim_signal(text, lowered):
        return _base_emit(
            paragraph=text,
            trigger_kind="strong_memory_stimulus",
            intent_field=(
                "Public/release readiness claims require verification before promotion; "
                "\uac80\uc99d\ub418\uc9c0 \uc54a\uc740 production claim is forbidden."
            ),
            topic_hint="production claim verification boundary",
            category_community_hint="OpenYggdrasil provider behavior contract / production claim control",
            breadcrumb="Public-facing claims must not outrank verifier evidence.",
            why_not_atomic="The public surface, verification gate, and production claim ban must remain together.",
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
