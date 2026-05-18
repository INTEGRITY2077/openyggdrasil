"""PTC engine builder and planner surface."""

from __future__ import annotations

from runtime.ptc import engine_core as _core

__all__ = sorted(
    name
    for name in dir(_core)
    if (
        name.startswith("build_")
        or name.startswith("render_")
        or name.startswith("materialize_")
        or name.startswith("produce_")
        or name.startswith("ingest_")
        or name.startswith("structural_")
    )
)

globals().update({name: getattr(_core, name) for name in __all__})
