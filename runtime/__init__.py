"""OpenYggdrasil runtime package.

The runtime used to rely on putting ``runtime/`` itself at the front of
``sys.path`` so modules could import siblings such as ``harness_common`` or
``ptc.primitives``. That path shape can shadow Python's stdlib ``operator``
module with ``runtime/operator``. Keep compatibility aliases for the legacy
top-level module names without adding ``runtime/`` to ``sys.path``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_LEGACY_TOP_LEVEL_ALIASES = (
    "admission",
    "harness_common",
    "attachments",
    "provider_attachment",
    "provider_inbox",
    "antigravity_router_bootstrap",
    "capture",
    "cultivation",
    "evaluation",
    "governance",
    "delivery",
    "korean_text",
    "memory",
    "pipeline",
    "placement",
    "provenance",
    "ptc",
    "reasoning",
    "retrieval",
    "runner",
    "source_ref",
    "log_event",
    "sandbox",
    "shim_policy",
    "surface_policy",
    "vault_guard",
)
_RUNTIME_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _RUNTIME_ROOT.parent


def _append_package_path(module, path: Path) -> None:
    if not path.exists() or not hasattr(module, "__path__"):
        return
    current = [str(Path(entry).resolve()) for entry in module.__path__]
    resolved = str(path.resolve())
    if resolved not in current:
        module.__path__ = [*module.__path__, resolved]


def _install_common_alias() -> None:
    runtime_common = importlib.import_module(f"{__name__}.common")
    module = sys.modules.get("common") or runtime_common
    _append_package_path(module, _RUNTIME_ROOT / "common")
    _append_package_path(module, _PROJECT_ROOT / "common")
    sys.modules["common"] = module


def _install_legacy_aliases() -> None:
    _install_common_alias()
    for name in _LEGACY_TOP_LEVEL_ALIASES:
        if name in sys.modules:
            continue
        try:
            sys.modules[name] = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError:
            # Legacy top-level aliases are compatibility only. A narrow command
            # such as `ygg list` must not fail merely because an unrelated legacy
            # surface imports an optional or undeployed dependency.
            continue


_install_legacy_aliases()
