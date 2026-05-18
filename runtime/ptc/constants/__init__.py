"""PTC engine constants surface."""

from __future__ import annotations

from runtime.ptc import engine_core as _core

__all__ = sorted(
    name
    for name in dir(_core)
    if name.isupper() and not name.startswith("_")
)

globals().update({name: getattr(_core, name) for name in __all__})
