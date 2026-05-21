from pathlib import Path

import pytest

from runtime.operator_entrypoint import _require_existing_vault_root


def test_operator_entrypoint_rejects_missing_vault_root_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OY_ALLOW_MISSING_VAULT_ROOT", raising=False)

    with pytest.raises(FileNotFoundError, match="vault root does not exist"):
        _require_existing_vault_root(tmp_path / "missing-vault")


def test_operator_entrypoint_allows_missing_vault_root_only_for_explicit_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OY_ALLOW_MISSING_VAULT_ROOT", "1")

    _require_existing_vault_root(tmp_path / "missing-vault")
