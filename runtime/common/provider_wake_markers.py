from __future__ import annotations


PROVIDER_REJUDGMENT_WAKE_SENTINEL = "\u2063oy-cpr-rejudge\u2063"


def is_provider_rejudgment_wakeup_text(text: object) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if PROVIDER_REJUDGMENT_WAKE_SENTINEL in normalized:
        return True
    return (
        "아까 답" in normalized
        and "뒤에서 확인된 기준" in normalized
        and ("필요한 밀도" in normalized or "바뀌는 부분" in normalized)
        and ("구조적으로 보강" in normalized or "바뀌는 부분" in normalized)
        and ("근거 이름" in normalized or "내부 번호" in normalized)
    )


__all__ = [
    "PROVIDER_REJUDGMENT_WAKE_SENTINEL",
    "is_provider_rejudgment_wakeup_text",
]
