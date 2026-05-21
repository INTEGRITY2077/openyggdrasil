from __future__ import annotations


PROVIDER_REJUDGMENT_WAKE_SENTINEL = "\u2063oy-cpr-rejudge\u2063"


def is_provider_rejudgment_wakeup_text(text: object) -> bool:
    """Detect retired Provider rejudgment wakeups so hooks ignore them as user text."""

    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if PROVIDER_REJUDGMENT_WAKE_SENTINEL in normalized:
        return True

    lowered = normalized.lower()
    answer_reference = (
        "아까 답" in normalized
        or "현재 답" in normalized
        or "기존 답" in normalized
        or "이전 답" in normalized
        or "current answer" in lowered
        or "previous answer" in lowered
        or "existing answer" in lowered
    )
    arrived_support = (
        "뒤에서 확인된" in normalized
        or "보강 후보" in normalized
        or "결과 도착" in normalized
        or "근거 도착" in normalized
        or "support arrived" in lowered
        or "result arrived" in lowered
        or "provider-bound" in lowered
    )
    recompare_action = (
        "비교" in normalized
        or "다시 봐" in normalized
        or "재비교" in normalized
        or "재판단" in normalized
        or "rejudge" in lowered
        or "recompare" in lowered
        or "compare" in lowered
    )
    internal_id_limit = (
        "내부 번호" in normalized
        or "파일 경로" in normalized
        or "노드 id" in lowered
        or "receipt" in lowered
        or "local path" in lowered
        or "file path" in lowered
    )
    if answer_reference and arrived_support and recompare_action:
        return True
    if arrived_support and recompare_action and internal_id_limit:
        return True

    return normalized.startswith("OpenYggdrasil 결과 도착 알림")


__all__ = [
    "PROVIDER_REJUDGMENT_WAKE_SENTINEL",
    "is_provider_rejudgment_wakeup_text",
]
