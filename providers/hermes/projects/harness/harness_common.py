from __future__ import annotations

import sys

from _core_compat import load_runtime_module


_module = load_runtime_module("harness_common")
sys.modules[__name__] = _module
