"""PTC engine validation surface."""

from __future__ import annotations

from runtime.ptc import engine_core as _core

__all__ = sorted(
    name
    for name in dir(_core)
    if (
        name.startswith("validate_")
        or name.startswith("_validate_")
        or name.startswith("_normalize_")
        or name.startswith("_safe_")
        or name.startswith("_assert_")
        or name.startswith("_require_")
    )
)

globals().update({name: getattr(_core, name) for name in __all__})
