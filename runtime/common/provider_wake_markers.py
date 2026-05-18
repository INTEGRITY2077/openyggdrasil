from __future__ import annotations


PROVIDER_REJUDGMENT_WAKE_SENTINEL = "\u2063oy-cpr-rejudge\u2063"


def is_provider_rejudgment_wakeup_text(text: object) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if PROVIDER_REJUDGMENT_WAKE_SENTINEL in normalized:
        return True
    return (
        "OpenYggdrasil 보강 결과가 도착했습니다" in normalized
        and "아까 답을 뒤에서 확인된 기준과 비교" in normalized
        and "파일 경로" in normalized
        and ("노드 ID" in normalized or "receipt ID" in normalized)
    ) or (
        "아까 답을 뒤에서 확인된 기준과 비교" in normalized
        and "근거 이름이나 내부 번호" in normalized
        and "나열하지" in normalized
    )


__all__ = [
    "PROVIDER_REJUDGMENT_WAKE_SENTINEL",
    "is_provider_rejudgment_wakeup_text",
]
