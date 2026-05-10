"""Postman-backed MS/MF worker signal threads.

Signals are mailbox work artifacts, not semantic answers. MS/MF can use them to
ask for consistency checks, graft decisions, or save/recall follow-up while
Postman owns append/read routing.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "worker_signal.v1"
THREAD_SCHEMA_VERSION = "worker_signal_thread.v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        stream.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _normalize_role(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"ms", "ms1", "memory_saver", "saver", "op1"}:
        return "memory_saver"
    if text in {"mf", "mf1", "memory_finder", "finder", "op2"}:
        return "memory_finder"
    return text or "unknown"


def _role_mailbox_name(role: str) -> str:
    normalized = _normalize_role(role)
    if normalized == "memory_saver":
        return "OP1"
    if normalized == "memory_finder":
        return "OP2"
    raise ValueError("unsupported_worker_role")


def _mailbox(root: Path, role: str) -> Path:
    return root / _role_mailbox_name(role)


def append_worker_signal(
    *,
    sessions_root: str | Path,
    sender_role: str,
    target_role: str,
    signal_type: str,
    work_order_id: str,
    mail_id: str,
    summary: str,
    evidence_refs: list[dict[str, Any]] | None = None,
    thread_id: str | None = None,
    reply_to_signal_id: str | None = None,
) -> dict[str, Any]:
    """Append a signal through Postman-owned mailbox ledgers."""
    root = Path(sessions_root)
    sender = _normalize_role(sender_role)
    target = _normalize_role(target_role)
    if sender not in {"memory_saver", "memory_finder"} or target not in {"memory_saver", "memory_finder"}:
        raise ValueError("unsupported_worker_role")
    if sender == target:
        raise ValueError("worker_signal_requires_distinct_roles")
    created_at = _now_iso()
    resolved_thread = thread_id or f"thread-{work_order_id or mail_id or uuid.uuid4().hex[:8]}"
    signal = {
        "schema_version": SCHEMA_VERSION,
        "signal_id": f"sig-{uuid.uuid4().hex[:10]}",
        "thread_id": resolved_thread,
        "reply_to_signal_id": reply_to_signal_id,
        "created_at": created_at,
        "sender_role": sender,
        "target_role": target,
        "signal_type": str(signal_type or "worker_question"),
        "work_order_id": str(work_order_id or ""),
        "mail_id": str(mail_id or ""),
        "summary": " ".join(str(summary or "").split())[:720],
        "evidence_refs": list(evidence_refs or []),
        "delivery_owner": "postman",
        "status": "ready_for_target_worker",
        "hard_nonclaims": [
            "worker_signal_is_not_answer_material",
            "postman_signal_append_is_not_semantic_success",
        ],
    }
    target_box = _mailbox(root, target)
    sender_box = _mailbox(root, sender)
    _append_jsonl(target_box / "worker_signals.jsonl", signal)
    _append_jsonl(sender_box / "worker_signal_outbox.jsonl", signal)
    _append_jsonl(root / "postman" / "worker_signals.jsonl", signal)
    return signal


def read_worker_signals(
    *,
    sessions_root: str | Path,
    target_role: str,
    mark_read: bool = False,
) -> dict[str, Any]:
    """Read target worker signals and optionally mark unread rows as read."""
    root = Path(sessions_root)
    target = _normalize_role(target_role)
    mailbox = _mailbox(root, target)
    signal_path = mailbox / "worker_signals.jsonl"
    signals = _read_jsonl(signal_path)
    unread = [row for row in signals if not row.get("read_at")]
    if mark_read and unread:
        read_at = _now_iso()
        rewritten: list[dict[str, Any]] = []
        unread_ids = {row.get("signal_id") for row in unread}
        for row in signals:
            item = dict(row)
            if item.get("signal_id") in unread_ids and not item.get("read_at"):
                item["read_at"] = read_at
                item["status"] = "read_by_target_worker"
            rewritten.append(item)
        signal_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rewritten),
            encoding="utf-8",
        )
    return {
        "schema_version": "worker_signal_read_result.v1",
        "target_role": target,
        "signal_count": len(signals),
        "unread_count": len(unread),
        "signals": unread if mark_read else signals,
    }


def summarize_signal_thread(
    *,
    sessions_root: str | Path,
    thread_id: str,
) -> dict[str, Any]:
    root = Path(sessions_root)
    rows = [
        row
        for path in [
            root / "postman" / "worker_signals.jsonl",
            root / "OP1" / "worker_signals.jsonl",
            root / "OP2" / "worker_signals.jsonl",
        ]
        for row in _read_jsonl(path)
        if row.get("thread_id") == thread_id
    ]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: str(item.get("created_at") or "")):
        signal_id = str(row.get("signal_id") or "")
        if not signal_id or signal_id in seen:
            continue
        seen.add(signal_id)
        unique.append(row)
    return {
        "schema_version": THREAD_SCHEMA_VERSION,
        "thread_id": thread_id,
        "signal_count": len(unique),
        "roles": sorted({str(row.get("sender_role")) for row in unique} | {str(row.get("target_role")) for row in unique}),
        "signals": unique,
    }


__all__ = [
    "append_worker_signal",
    "read_worker_signals",
    "summarize_signal_thread",
]
