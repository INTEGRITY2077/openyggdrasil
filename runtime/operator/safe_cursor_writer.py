from __future__ import annotations

from pathlib import Path
from typing import Mapping


def committed_paths_from_artifact_paths(paths: Mapping[str, object]) -> list[str]:
    return [str(value).replace("\\", "/") for value in paths.values() if str(value or "").strip()]


def as_vault_source_paths(paths: Mapping[str, object]) -> list[str]:
    out: list[str] = []
    for value in paths.values():
        text = str(value or "").strip().replace("\\", "/")
        if not text:
            continue
        if text.startswith("oy-vault://"):
            out.append(text)
        elif text.startswith("vault/"):
            out.append("oy-vault://" + text.removeprefix("vault/").strip("/"))
        else:
            out.append(f"oy-vault://{text.lstrip('/')}")
    return sorted(set(out))


def relative_to_vault(path: Path, *, vault: Path) -> str:
    return str(path.resolve().relative_to(vault.resolve())).replace("\\", "/")


__all__ = ["as_vault_source_paths", "committed_paths_from_artifact_paths", "relative_to_vault"]
