from __future__ import annotations


def register_default_source_ref_resolvers() -> None:
    """Runtime bootstrap boundary for built-in source_ref adapters.

    Importing runtime.source_ref.registry or runtime.source_ref package must not register
    provider-specific adapters. Call this function from a concrete runtime boundary that
    intentionally enables the built-in adapters for MemoryTicket processing.
    """
    from .hermes_session_json import register_hermes_session_json_resolver
    from .local_docs import register_local_docs_resolver

    register_hermes_session_json_resolver()
    register_local_docs_resolver()


__all__ = ["register_default_source_ref_resolvers"]
