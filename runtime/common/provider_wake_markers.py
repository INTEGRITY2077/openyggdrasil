from __future__ import annotations


PROVIDER_REJUDGMENT_WAKE_SENTINEL = "\u2063oy-cpr-rejudge\u2063"


def is_provider_rejudgment_wakeup_text(text: object) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if PROVIDER_REJUDGMENT_WAKE_SENTINEL in normalized:
        return True
    return (
        "OpenYggdrasil 결과 도착 알림입니다" in normalized
        and "원 질문과 현재 답을 다시 비교" in normalized
        and "파일 경로, 노드 ID, receipt ID" in normalized
    ) or (
        "뒤에서 확인한 기준과 비교" in normalized
        and "원 질문과 현재 답을 다시 비교" in normalized
        and "경로, 노드 ID, receipt ID" in normalized
    )


__all__ = [
    "PROVIDER_REJUDGMENT_WAKE_SENTINEL",
    "is_provider_rejudgment_wakeup_text",
]
