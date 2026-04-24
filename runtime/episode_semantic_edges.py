from __future__ import annotations

import importlib
import sys


_module = importlib.import_module("provenance.episode_semantic_edges")
globals().update(
    {
        key: value
        for key, value in vars(_module).items()
        if not (key.startswith("__") and key not in {"__all__", "__doc__"})
    }
)
sys.modules[__name__] = _module
