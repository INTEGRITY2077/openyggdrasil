from __future__ import annotations

from typing import Any, Callable

Resolver = Callable[..., dict[str, Any]]

_RESOLVERS: dict[str, Resolver] = {}


def register_source_ref_resolver(scheme: str, resolver: Resolver) -> None:
    """source_ref scheme resolver를 명시 등록한다.

    Common registry는 provider-specific adapter를 import하지 않는다. Hermes, Codex,
    fake provider 등은 각 adapter/bootstrap 경계에서 자기 scheme을 등록해야 한다.
    """
    normalized = scheme.strip().removesuffix("://")
    if not normalized:
        raise ValueError("scheme must not be empty")
    _RESOLVERS[normalized] = resolver


def unregister_source_ref_resolver(scheme: str) -> None:
    """테스트/fixture 정리를 위해 등록된 resolver를 제거한다."""
    normalized = scheme.strip().removesuffix("://")
    _RESOLVERS.pop(normalized, None)


def list_source_ref_resolvers() -> list[str]:
    """현재 명시 등록된 source_ref scheme 목록을 반환한다."""
    return sorted(_RESOLVERS)


def _source_ref_scheme(source_ref: str) -> str:
    if "://" not in source_ref:
        return ""
    return source_ref.split("://", 1)[0]


def _typed_unavailable(source_ref: str, reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "source_ref": source_ref,
        "resolver_status": "unavailable",
        "redaction_status": "not_applicable",
    }


def resolve_source_ref(
    *,
    source_ref: str,
    range_hint: dict[str, Any] | None = None,
    anchor_hash: str = "",
    resolver_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Provider-neutral source_ref registry.

    MS/MF core는 provider별 저장소 구조를 알지 않는다. Provider별 원본 접근은
    이 registry 뒤에 명시 등록된 adapter만 수행한다. OP1/OP2 표기는 legacy
    evidence id로만 호환된다.
    """
    range_hint = range_hint or {}
    resolver_options = resolver_options or {}
    scheme = _source_ref_scheme(source_ref)
    if not scheme:
        return _typed_unavailable(source_ref, "source_ref_scheme_missing")

    resolver = _RESOLVERS.get(scheme)
    if resolver is None:
        return _typed_unavailable(source_ref, "unsupported_source_ref_scheme")

    return resolver(
        source_ref=source_ref,
        range_hint=range_hint,
        anchor_hash=anchor_hash,
        resolver_options=resolver_options,
    )


__all__ = [
    "Resolver",
    "list_source_ref_resolvers",
    "register_source_ref_resolver",
    "resolve_source_ref",
    "unregister_source_ref_resolver",
]
