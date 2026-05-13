from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from runtime.polling.live_delivery_state import read_live_jsonl


@dataclass(frozen=True)
class PtcTriggerDecision:
    status: str
    trigger_file: Path
    trigger_age_seconds: float | None
    trigger_data: dict[str, Any] | None
    cleared_timeout_trigger: bool

    @property
    def created(self) -> bool:
        return self.status == "created"


def check_ptc_intents(*, mailbox: Path, receipt_name: str) -> list[dict[str, Any]]:
    intents_file = mailbox / "intents.jsonl"
    receipts_file = mailbox / receipt_name
    if not intents_file.exists():
        return []

    completed = {row.get("in_reply_to") for row in read_live_jsonl(receipts_file)}
    pending: list[dict[str, Any]] = []
    for message in read_live_jsonl(intents_file):
        if message.get("mail_id") in completed:
            continue
        payload = message.get("payload") if isinstance(message.get("payload"), Mapping) else {}
        if payload.get("ptc"):
            pending.append(message)
    return pending


def prepare_ptc_trigger(
    *,
    mailbox: Path,
    intent: Mapping[str, Any],
    trigger_timeout: int,
    now: float | None = None,
) -> PtcTriggerDecision:
    timestamp = time.time() if now is None else now
    trigger_file = mailbox / "ptc_trigger.json"
    if trigger_file.exists():
        age = timestamp - trigger_file.stat().st_mtime
        if age < trigger_timeout:
            return PtcTriggerDecision(
                status="existing_pending",
                trigger_file=trigger_file,
                trigger_age_seconds=age,
                trigger_data=None,
                cleared_timeout_trigger=False,
            )
        trigger_file.unlink(missing_ok=True)
        cleared_timeout = True
    else:
        age = None
        cleared_timeout = False

    payload = intent.get("payload") if isinstance(intent.get("payload"), Mapping) else {}
    trigger_data = {
        "mail_id": intent["mail_id"],
        "intent": intent.get("intent", "save"),
        "ptc_code": payload.get("ptc_code", ""),
        "context_snapshot": payload.get("context_snapshot", ""),
        "timestamp": intent.get("timestamp", ""),
        "created_at": timestamp,
    }
    trigger_file.write_text(json.dumps(trigger_data, ensure_ascii=False), encoding="utf-8")
    return PtcTriggerDecision(
        status="created",
        trigger_file=trigger_file,
        trigger_age_seconds=age,
        trigger_data=trigger_data,
        cleared_timeout_trigger=cleared_timeout,
    )


def build_ptc_trigger_prompt(*, role: str, trigger_file: Path, intent: Mapping[str, Any]) -> str:
    return (
        f"[{role} WORKFLOW]\n"
        f"지금 할 일: PTC trigger 처리\n"
        f"보고 있는 것: {trigger_file}\n"
        f"생성할 것: PTC 처리 결과 receipt와 필요한 Vault node\n"
        f"방금 만든 것: trigger mail_id={intent['mail_id']}\n"
        f"근거: {trigger_file}\n"
        f"다음 행동: ptc_trigger.json을 읽고 처리 후 trigger 삭제\n"
        f"상태: pending"
    )


__all__ = [
    "PtcTriggerDecision",
    "build_ptc_trigger_prompt",
    "check_ptc_intents",
    "prepare_ptc_trigger",
]
