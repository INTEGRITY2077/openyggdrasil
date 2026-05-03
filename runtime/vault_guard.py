"""
Vault Path Guard — 14차 Axis 4: Vault 경로 ../ 탈출 방어.

Vault 외부로의 파일 쓰기를 차단하는 경로 검증.
"""
from __future__ import annotations

from pathlib import Path


def guard_vault_path(vault: Path, target: Path) -> Path:
    """
    target이 vault 내부에 있는지 검증하고 정규화된 절대경로 반환.
    vault 외부 접근 시 ValueError 발생.
    """
    vault = vault.resolve()
    resolved = (vault / target).resolve()

    # vault 내부인지 확인
    try:
        resolved.relative_to(vault)
    except ValueError:
        raise ValueError(
            f"Vault 경로 탈출 시도: target={target} → resolved={resolved}, vault={vault}"
        )

    return resolved


def is_safe_path(vault: Path, target: Path) -> bool:
    """target이 vault 내부에 있는지 bool 반환."""
    try:
        guard_vault_path(vault, target)
        return True
    except ValueError:
        return False
