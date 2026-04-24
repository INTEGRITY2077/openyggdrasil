from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from harness_common import LOCKS_ROOT, utc_now_iso


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_lock_metadata(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def lock_snapshot(
    *,
    lock_root: Path | None = None,
    stale_after_seconds: float = 900.0,
    now: datetime | None = None,
) -> List[Dict[str, Any]]:
    effective_root = lock_root or LOCKS_ROOT
    effective_now = now or datetime.now(timezone.utc)
    snapshots: List[Dict[str, Any]] = []

    if not effective_root.exists():
        return snapshots

    for path in sorted(effective_root.glob("*.lock")):
        metadata = read_lock_metadata(path)
        created_at_raw = metadata.get("created_at")
        created_at = parse_timestamp(created_at_raw)
        age_seconds = None
        if created_at is not None:
            age_seconds = max(0.0, (effective_now - created_at).total_seconds())
        snapshots.append(
            {
                "name": path.stem,
                "path": str(path),
                "created_at": created_at_raw,
                "age_seconds": age_seconds,
                "pid": metadata.get("pid"),
                "host": metadata.get("host"),
                "stale": bool(age_seconds is not None and age_seconds >= stale_after_seconds),
            }
        )
    return snapshots


def recover_stale_locks(
    *,
    lock_root: Path | None = None,
    stale_after_seconds: float = 900.0,
    now: datetime | None = None,
) -> Dict[str, Any]:
    effective_root = lock_root or LOCKS_ROOT
    recovered: List[Dict[str, Any]] = []

    for snapshot in lock_snapshot(
        lock_root=effective_root,
        stale_after_seconds=stale_after_seconds,
        now=now,
    ):
        if not snapshot["stale"]:
            continue
        path = Path(snapshot["path"])
        if path.exists():
            path.unlink()
        recovered.append(snapshot)

    return {
        "recovered_at": utc_now_iso(),
        "stale_after_seconds": stale_after_seconds,
        "recovered_count": len(recovered),
        "recovered_locks": recovered,
    }
