from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.delivery.postman_work_order import append_worker_history_event


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _provider_inbox_path(mailbox: Path) -> Path:
    configured = os.environ.get("YGG_PROVIDER_INBOX")
    if configured:
        return Path(configured)
    return mailbox.parent / "provider_inbox.jsonl"


def _append_provider_inbox(
    mailbox: Path,
    *,
    mail_id: str,
    status: str,
    produced_count: int,
    node_ids: list[str],
    result_bundle: dict[str, Any] | None,
) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": mailbox.name,
        "receiver": "Provider",
        "mail_id": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": node_ids,
        "bundle": result_bundle,
        "result_bundle": result_bundle,
        "message": f"{mailbox.name} -> Provider: {mail_id} status={status} produced={produced_count}",
        "delivery_mode": "provider_inbox_file",
        "delivery_owner": "postman",
    }
    append_jsonl(_provider_inbox_path(mailbox), row)


def _append_postman_observation(
    mailbox: Path,
    *,
    mail_id: str,
    produced_count: int,
    node_ids: list[str],
) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": mailbox.name,
        "receiver": "Provider",
        "mail_id": mail_id,
        "produced_count": produced_count,
        "nodes": node_ids,
        "message": f"{mailbox.name} -> Provider: {mail_id} produced={produced_count}",
        "delivery_mode": "mailbox_log_only",
        "delivery_owner": "postman",
        "hard_nonclaim": "not_injected_into_hermes_chat",
    }
    append_jsonl(mailbox / "postman_observations.jsonl", row)


def deliver_operator_result(
    mailbox: Path,
    mail_id: str,
    *,
    status: str = "delivered",
    result_bundle: dict[str, Any] | None = None,
    produced_count: int = 0,
    node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Record a bounded worker result and Postman-owned provider notification.

    This is the delivery-layer owner for provider inbox and observation records.
    Memory Worker modules keep semantic work ownership; this module owns result
    delivery side effects.
    """
    mailbox.mkdir(parents=True, exist_ok=True)
    nodes = node_ids or []
    receipt = {
        "receipt_id": str(uuid.uuid4())[:8],
        "in_reply_to": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": nodes,
        "bundle": result_bundle,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_pid": os.getpid(),
        "delivery_owner": "postman",
    }
    append_jsonl(mailbox / "delivery_receipts.jsonl", receipt)
    append_worker_history_event(
        mailbox=mailbox,
        mail_id=mail_id,
        phase="receipt_recorded",
        actor=mailbox.name,
        summary="Worker result receipt was recorded for the mailbox work order.",
        status=status,
        evidence={
            "produced_count": produced_count,
            "node_count": len(nodes),
            "bundle_present": bool(result_bundle),
        },
    )

    try:
        _append_provider_inbox(
            mailbox,
            mail_id=mail_id,
            status=status,
            produced_count=produced_count,
            node_ids=nodes,
            result_bundle=result_bundle,
        )
    except OSError:
        pass

    try:
        _append_postman_observation(
            mailbox,
            mail_id=mail_id,
            produced_count=produced_count,
            node_ids=nodes,
        )
    except OSError:
        pass

    return receipt


__all__ = ["deliver_operator_result"]
