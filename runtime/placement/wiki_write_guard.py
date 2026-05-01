from __future__ import annotations

import os
import re
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from harness_common import utc_now_iso


LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:\b[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|mnt|tmp|var|etc)/)"
)


def stable_content_hash(text: str) -> str:
    return sha256(str(text).encode("utf-8")).hexdigest()


def normalize_wiki_relative_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("target_relative_path is required")
    if LOCAL_PATH_PATTERN.search(raw):
        raise ValueError("target_relative_path must not contain a local filesystem path")
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("target_relative_path must be a safe relative path")
    if path.suffix != ".md":
        raise ValueError("target_relative_path must point to a markdown page")
    return path.as_posix()


def build_wiki_write_guard(
    *,
    target_relative_path: str,
    new_text: str,
    existing_text: str | None = None,
    expected_existing_hash: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    target = normalize_wiki_relative_path(target_relative_path)
    next_hash = stable_content_hash(new_text)
    current_hash = stable_content_hash(existing_text) if existing_text is not None else None
    expected = str(expected_existing_hash or "").strip() or None

    reason_codes: list[str] = []
    write_allowed = True
    if existing_text is None and expected is not None:
        reason_codes.append("expected_hash_for_absent_page")
        write_allowed = False
    elif existing_text is not None and expected is not None and current_hash != expected:
        reason_codes.append("manual_edit_guard_mismatch")
        write_allowed = False

    return {
        "schema_version": "wiki_write_guard.v1",
        "target_relative_path": target,
        "status": "write_guard_passed" if write_allowed else "typed_unavailable",
        "write_allowed": write_allowed,
        "current_content_hash": current_hash,
        "expected_existing_hash": expected,
        "next_content_hash": next_hash,
        "manual_edit_protection": "content_hash_compare_before_replace",
        "atomic_write_boundary": "write_temp_file_then_os_replace",
        "rollback_boundary": "abort_before_replace_when_guard_fails",
        "reason_codes": reason_codes,
        "checked_at": checked_at or utc_now_iso(),
    }


def atomic_write_wiki_page(
    *,
    target_path: Path,
    target_relative_path: str,
    new_text: str,
    expected_existing_hash: str | None = None,
) -> dict[str, Any]:
    existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    guard = build_wiki_write_guard(
        target_relative_path=target_relative_path,
        new_text=new_text,
        existing_text=existing_text,
        expected_existing_hash=expected_existing_hash,
    )
    if guard["write_allowed"] is not True:
        return {**guard, "write_committed": False}

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(new_text, encoding="utf-8")
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return {**guard, "status": "written", "write_committed": True}
