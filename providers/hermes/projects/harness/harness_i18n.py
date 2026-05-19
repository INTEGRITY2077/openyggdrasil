from __future__ import annotations


def normalize_requested_locale(locale: str | None) -> str | None:
    if locale is None:
        return None
    normalized = locale.strip().replace("_", "-")
    if not normalized:
        return None
    return normalized
