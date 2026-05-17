from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


PRODUCTION_VAULT_ENV_ORDER = (
    "OPENYGGDRASIL_VAULT_ROOT",
    "OY_VAULT",
)
DEV_VAULT_ENV_ORDER = (
    "OPENYGGDRASIL_DEV_VAULT_ROOT",
    "OY_DEV_VAULT",
)
DEV_ENV_VALUES = {"dev", "development", "test", "testbed", "local"}


def _env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name) or "").strip()


def _expand(path_text: str, *, home: Path | None = None) -> Path:
    if home is None:
        return Path(path_text).expanduser()
    if path_text == "~":
        return home
    if path_text.startswith("~/") or path_text.startswith("~\\"):
        return home / path_text[2:]
    return Path(path_text).expanduser()


def _home_default(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / ".yggdrasil" / "vault"


def resolve_vault_root(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    workspace_root: Path | None = None,
) -> Path:
    """Resolve the OpenYggdrasil vault root without user-path hardcoding.

    Order:
    1. explicit production env: OPENYGGDRASIL_VAULT_ROOT, then OY_VAULT
    2. explicit dev/test mode env: OPENYGGDRASIL_DEV_VAULT_ROOT, then OY_DEV_VAULT
    3. explicit dev/test workspace override through OY_PRIVATE_DEV
    4. user-home default: ~/.yggdrasil/vault

    Development/testbed paths are available only when OPENYGGDRASIL_ENV is a
    dev/test value. Production code must not silently fall back to a repo-local
    private testbed vault.
    """

    active_env = env or os.environ
    for name in PRODUCTION_VAULT_ENV_ORDER:
        value = _env_value(active_env, name)
        if value:
            return _expand(value, home=home)

    mode = _env_value(active_env, "OPENYGGDRASIL_ENV").lower()
    if mode in DEV_ENV_VALUES:
        for name in DEV_VAULT_ENV_ORDER:
            value = _env_value(active_env, name)
            if value:
                return _expand(value, home=home)
        private_dev = _env_value(active_env, "OY_PRIVATE_DEV")
        if private_dev:
            return _expand(private_dev, home=home) / "testbed" / ".yggdrasil" / "vault"
        if workspace_root is not None:
            return Path(workspace_root).expanduser() / ".yggdrasil" / "vault"

    return _home_default(home=home)


def to_vault_uri(path: object, *, vault_root: Path) -> str:
    """Return an oy-vault URI for a path inside the vault.

    Absolute paths outside the vault are intentionally not returned. They are
    reduced to typed unavailable refs so receipts/support bundles do not leak
    private local paths.
    """

    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return "oy-vault://typed_unavailable/empty-path"
    if text.startswith("oy-vault://"):
        return text
    if text.startswith("vault/"):
        return "oy-vault://" + text.removeprefix("vault/").strip("/")
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(vault_root.resolve()).as_posix()
        except ValueError:
            return "oy-vault://typed_unavailable/outside-vault"
        return f"oy-vault://{rel}"
    return "oy-vault://" + text.lstrip("/")


__all__ = [
    "DEV_ENV_VALUES",
    "DEV_VAULT_ENV_ORDER",
    "PRODUCTION_VAULT_ENV_ORDER",
    "resolve_vault_root",
    "to_vault_uri",
]
