from __future__ import annotations

from _core_compat import export_public, load_runtime_module


_module = load_runtime_module("map_identity")
export_public(_module, globals())
