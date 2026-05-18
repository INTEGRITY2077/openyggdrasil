from __future__ import annotations

from typing import Any, Callable

Resolver = Callable[..., dict[str, Any]]

_RESOLVERS: dict[str, Resolver] = {}


def register_source_ref_resolver(scheme: str, resolver: Resolver) -> None:
    """Register a provider-specific source_ref resolver by scheme.

    The common registry does not import provider adapters directly. Hermes,
    Codex, fake-provider, or another adapter/bootstrap layer must explicitly
    register the schemes it owns.
    """
    normalized = scheme.strip().removesuffix("://")
    if not normalized:
        raise ValueError("scheme must not be empty")
    _RESOLVERS[normalized] = resolver


def unregister_source_ref_resolver(scheme: str) -> None:
    """Unregister a resolver for test fixture cleanup."""
    normalized = scheme.strip().removesuffix("://")
    _RESOLVERS.pop(normalized, None)


def list_source_ref_resolvers() -> list[str]:
    """Return the currently registered source_ref schemes."""
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
    """Resolve a provider-neutral source_ref through an explicit adapter.

    MS/MF core does not know provider-specific storage internals. Only
    explicitly registered adapters may resolve provider-native references.
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
