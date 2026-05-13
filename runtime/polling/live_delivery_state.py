from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from runtime.common.jsonl_io import append_jsonl as _append_jsonl


def read_live_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            parsed = {"raw_unparsed": line[:160]}
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def delivered_live_ids(mailbox: Path) -> set[str]:
    path = mailbox / "live_delivered.jsonl"
    return {str(row.get("delivery_id")) for row in read_live_jsonl(path) if row.get("delivery_id")}


def mark_live_delivered(
    *,
    mailbox: Path,
    event: Mapping[str, Any],
    status: str = "sent_to_live_session",
    timestamp: float | None = None,
) -> None:
    _append_jsonl(
        mailbox / "live_delivered.jsonl",
        {
            "delivery_id": event.get("delivery_id"),
            "mail_id": event.get("mail_id"),
            "status": status,
            "timestamp": time.time() if timestamp is None else timestamp,
        },
    )


def receipt_for_mail_id(*, mailbox: Path, receipt_name: str, mail_id: str) -> dict[str, Any]:
    for row in reversed(read_live_jsonl(mailbox / receipt_name)):
        if row.get("in_reply_to") == mail_id or row.get("mail_id") == mail_id:
            return row
    return {}


def check_live_events(*, mailbox: Path, receipt_name: str, mode: str) -> list[dict[str, Any]]:
    delivered_rows = read_live_jsonl(mailbox / "live_delivered.jsonl")
    delivered = {row.get("delivery_id") for row in delivered_rows if row.get("delivery_id")}
    completed = {row.get("in_reply_to") for row in read_live_jsonl(mailbox / receipt_name)}
    for row in delivered_rows:
        if row.get("status") == "sent_to_live_session" and row.get("mail_id") not in completed:
            return []
    expected_intents = ("save", "memory_ticket") if mode == "produce" else ("query",)
    events: list[dict[str, Any]] = []
    for event in read_live_jsonl(mailbox / "live_inbox.jsonl"):
        if event.get("delivery_id") in delivered:
            continue
        if event.get("intent") not in expected_intents + (None,):
            continue
        if event.get("mail_id") in completed:
            mark_live_delivered(mailbox=mailbox, event=event, status="already_receipted")
            continue
        events.append(event)
        break
    return events


def append_live_operator_log(*, mailbox: Path, row: Mapping[str, Any]) -> None:
    _append_jsonl(mailbox / "live_operator_log.jsonl", row)


def append_goal_log(*, mailbox: Path, row: Mapping[str, Any]) -> None:
    _append_jsonl(mailbox / "live_goal_log.jsonl", row)


def append_native_goal_log(*, mailbox: Path, row: Mapping[str, Any]) -> None:
    _append_jsonl(mailbox / "live_native_goal_log.jsonl", row)


__all__ = [
    "append_goal_log",
    "append_live_operator_log",
    "append_native_goal_log",
    "check_live_events",
    "delivered_live_ids",
    "mark_live_delivered",
    "read_live_jsonl",
    "receipt_for_mail_id",
]
