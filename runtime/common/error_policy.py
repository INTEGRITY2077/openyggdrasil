from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


RecoverableSink = Callable[[Mapping[str, Any]], None]


def recoverable_to_degraded_event(exc: BaseException, *, component: str, operation: str) -> dict[str, Any]:
    return {
        "schema_version": "recoverable_runtime_error.v1",
        "status": "degraded",
        "component": str(component),
        "operation": str(operation),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def recoverable_to_typed_unavailable(
    exc: BaseException,
    *,
    component: str,
    operation: str,
) -> dict[str, Any]:
    event = recoverable_to_degraded_event(exc, component=component, operation=operation)
    return {
        **event,
        "status": "typed_unavailable",
        "reason_codes": [
            "recoverable_runtime_error",
            f"{component}_{operation}_typed_unavailable",
        ],
    }


def record_recoverable(
    exc: BaseException,
    *,
    component: str,
    operation: str,
    sink: RecoverableSink | None = None,
) -> None:
    event = recoverable_to_degraded_event(exc, component=component, operation=operation)
    if sink is not None:
        sink(event)
