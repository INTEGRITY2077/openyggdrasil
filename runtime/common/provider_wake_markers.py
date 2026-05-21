from __future__ import annotations


PROVIDER_REJUDGMENT_WAKE_SENTINEL = "\u2063oy-cpr-rejudge\u2063"


def is_provider_rejudgment_wakeup_text(text: object) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if PROVIDER_REJUDGMENT_WAKE_SENTINEL in normalized:
        return True
    return normalized.startswith("OpenYggdrasil 보강 후보가 ")


__all__ = [
    "PROVIDER_REJUDGMENT_WAKE_SENTINEL",
    "is_provider_rejudgment_wakeup_text",
]
