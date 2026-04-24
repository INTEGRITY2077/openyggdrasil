from __future__ import annotations

import sys

from _core_compat import load_runtime_module


_module = load_runtime_module("promotion_worthiness")
sys.modules[__name__] = _module


if __name__ == "__main__" and hasattr(_module, "main"):
    raise SystemExit(_module.main())
