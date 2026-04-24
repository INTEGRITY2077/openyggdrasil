from __future__ import annotations

import sys

from _core_compat import load_runtime_module


_module = load_runtime_module("support_bundle")
sys.modules[__name__] = _module
