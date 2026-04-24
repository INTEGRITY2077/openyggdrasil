from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[4]
RUNTIME_ROOT = OPENYGGDRASIL_ROOT / "runtime"


def load_runtime_module(module_name: str) -> ModuleType:
    target = RUNTIME_ROOT / f"{module_name}.py"
    runtime_root_str = str(RUNTIME_ROOT)
    if runtime_root_str not in sys.path:
        sys.path.insert(0, runtime_root_str)
    module_key = f"_openyggdrasil_runtime_{module_name}"
    existing = sys.modules.get(module_key)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_key,
        target,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load OpenYggdrasil runtime module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_key, None)
        raise
    return sys.modules.get(module_key, module)


def export_public(module: ModuleType, namespace: dict[str, object]) -> None:
    for key, value in vars(module).items():
        if key.startswith("__") and key not in {"__all__", "__doc__"}:
            continue
        namespace[key] = value
