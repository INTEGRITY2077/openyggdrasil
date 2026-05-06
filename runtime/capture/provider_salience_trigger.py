from __future__ import annotations

from typing import Any

CANONICAL_DECOMPOSITION_GUARD = "preserve_paragraph_intent_before_decision_atoms"


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _base_emit(*, paragraph: str, trigger_kind: str, intent_field: str, topic_hint: str, category_community_hint: str, breadcrumb: str, why_not_atomic: str) -> dict[str, Any]:
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
        "recency_anchor": "current_exchange",
        "why_this_topic_matters": "향후 Provider 행동과 retrieval entrypoint 선택을 바꾸는 반복 적용 계약이다.",
        "source_ref_status": "placeholder",
        "source_ref_required": True,
        "paragraph_intent_field": paragraph,
    }


def detect_provider_memory_salience(paragraph: str) -> dict[str, Any]:
    """Provider 대화 문단이 Topic Breadcrumb MemoryTicket 초안으로 승격될지 판정한다.

    이 함수는 저장기가 아니다. 사용자 explicit save command 여부가 아니라 장기 회상과
    Provider 행동양식 교정에 필요한 salience를 감지하고, 문단 단위 의도장을 보존한
    authoring request skeleton을 만든다. 실제 저장은 SourceRef/range/anchor_hash가 붙은
    MemoryTicket schema/admission gate에서 별도로 판정해야 한다.
    """
    text = (paragraph or "").strip()
    if not text:
        return {"trigger_decision": "defer", "trigger_kind": "none", "reason": "empty_paragraph"}

    if _contains_any(text, ("문제가", "문제는", "아니라")) and _contains_any(text, ("트리깅", "trigger", "필요성", "명령")):
        return _base_emit(
            paragraph=text,
            trigger_kind="boundary_correction",
            intent_field="Provider 기억 보존은 사용자 explicit 명령 처리에서 시작하는 것이 아니라 autonomous salience trigger detection에서 시작해야 한다.",
            topic_hint="Provider autonomous salience trigger",
            category_community_hint="OpenYggdrasil provider behavior contract / memory authoring bridge",
            breadcrumb="Provider는 사용자 저장 명령뿐 아니라 강한 기억 자극과 주제 currentness 변화를 스스로 감지해야 한다.",
            why_not_atomic="이 문단을 '명령 아님' 또는 'trigger point' 같은 원자 태그로 쪼개면 Provider 행동양식의 시작점을 교정하는 핵심 의도장이 사라진다.",
        )

    if _contains_any(text, ("결정은 이렇게 닫", "결정 완료", "닫자", "완료")) and _contains_any(text, ("주제", "topic", "P1-B", "authoring bridge")):
        return _base_emit(
            paragraph=text,
            trigger_kind="topic_decision_completed",
            intent_field="P1-B는 decision atom extraction이 아니라 paragraph-level intent field를 보존한 뒤 넓은 category/community에 편입시키는 authoring bridge다.",
            topic_hint="Topic Breadcrumb MemoryTicket Authoring Bridge",
            category_community_hint="OpenYggdrasil provider behavior contract / broad category/community memory authoring",
            breadcrumb="주제 의사결정이 닫히면 좁은 topic fragment가 아니라 넓은 category/community retrieval entrypoint로 편입한다.",
            why_not_atomic="P1-B나 decision atom 같은 단어별 원자 태그로 분해하면 문단이 정한 저장 순서와 넓은 배치 원칙이 손실된다.",
        )

    if _contains_any(text, ("금지", "안 된다", "하지 말", "용납", "극혐")) and _contains_any(text, ("README", "PRODUCTION READY", "100%", "검증", "mock", "demo")):
        return _base_emit(
            paragraph=text,
            trigger_kind="strong_memory_stimulus",
            intent_field="검증되지 않은 README/PRODUCTION READY/100% 주장은 금지이며, 코드와 실제 워크플로우 증명 뒤에만 사용자-facing claim을 올려야 한다.",
            topic_hint="README claim gating and proof discipline",
            category_community_hint="OpenYggdrasil verification governance / provider behavior contract",
            breadcrumb="README claim은 코드 변경과 실제 검증 관찰 이후에만 승격한다.",
            why_not_atomic="README, 100%, PRODUCTION READY를 별도 atom tag로 쪼개면 검증 전 claim 승격 금지라는 운영 의도가 약해진다.",
        )

    if _contains_any(text, ("기억해", "저장해", "remember")):
        return _base_emit(
            paragraph=text,
            trigger_kind="explicit_user_save_command",
            intent_field="사용자가 명시적으로 장기 기억 보존을 요청했다.",
            topic_hint="Explicit memory save request",
            category_community_hint="OpenYggdrasil provider behavior contract / memory authoring bridge",
            breadcrumb="명시 저장 요청은 trigger_kind 중 하나일 뿐이며 source_ref 기반 admission을 거쳐야 한다.",
            why_not_atomic="명시 명령 자체만 저장하면 문단이 속한 주제/community 배치가 손실된다.",
        )

    return {
        "trigger_decision": "defer",
        "trigger_kind": "none",
        "reason": "no_long_term_retrieval_salience",
        "source_ref_status": "placeholder",
    }


__all__ = ["CANONICAL_DECOMPOSITION_GUARD", "detect_provider_memory_salience"]
