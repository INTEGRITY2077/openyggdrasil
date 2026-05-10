from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _payload_summary(message_type: str, payload: dict[str, Any]) -> str:
    if message_type == "query":
        text = payload.get("query_text") or payload.get("query") or ""
    elif message_type == "memory_ticket":
        text = payload.get("surface_reason") or payload.get("topic_hint") or payload.get("intent_field") or ""
    else:
        text = payload.get("context_snapshot") or ""
    return " ".join(str(text).split())[:360]


def _work_anchor(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    explicit_kind = str(payload.get("anchor_kind") or payload.get("work_anchor_kind") or "").strip()
    user_question = str(
        payload.get("user_question")
        or payload.get("original_user_question")
        or payload.get("current_user_question")
        or ""
    ).strip()
    provider_need = str(
        payload.get("provider_initiated_need")
        or payload.get("surface_reason")
        or payload.get("topic_hint")
        or payload.get("intent_field")
        or ""
    ).strip()
    query_text = str(payload.get("query_text") or payload.get("query") or "").strip()
    if explicit_kind in {"user_question", "provider_initiated_need"}:
        anchor_kind = explicit_kind
    elif user_question:
        anchor_kind = "user_question"
    elif message_type == "memory_ticket" or provider_need:
        anchor_kind = "provider_initiated_need"
    elif query_text:
        anchor_kind = "user_question"
    else:
        anchor_kind = "missing_anchor"
    if anchor_kind == "user_question":
        anchor_text = user_question or query_text
    elif anchor_kind == "provider_initiated_need":
        anchor_text = provider_need or query_text
    else:
        anchor_text = ""
    return {
        "schema_version": "provider_work_anchor.v1",
        "anchor_kind": anchor_kind,
        "anchor_text": " ".join(anchor_text.split())[:720],
        "user_question_present": bool(user_question or (anchor_kind == "user_question" and query_text)),
        "provider_initiated_need_present": bool(provider_need or anchor_kind == "provider_initiated_need"),
        "hard_nonclaims": [
            "missing_user_question_does_not_mean_missing_provider_need",
            "provider_initiated_need_can_anchor_memory_work",
        ],
    }


def _worker_role(message_type: str) -> str:
    if message_type == "query":
        return "memory_finder"
    return "memory_saver"


def _acceptance_gate(message_type: str) -> str:
    if message_type == "query":
        return "support_bundle_or_typed_unavailable"
    if message_type == "memory_ticket":
        return "source_ref_backed_storage_receipt_or_typed_unavailable"
    return "storage_receipt_or_typed_unavailable"


def append_postman_work_order(
    *,
    postman_dir: Path,
    mailbox: Path,
    delivery_id: str,
    mail_id: str,
    recipient: str,
    message_type: str,
    provider_id: str,
    message_file_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Write the mailbox-first work order and initial history event.

    The work order is the worker-facing SOT. Native tmux activation should only
    wake the worker and point to this ledger; it must not become the work spec.
    """
    created_at = _now()
    work_order_id = f"work-{mail_id}"
    work_order = {
        "schema_version": "postman_work_order.v1",
        "work_order_id": work_order_id,
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "sender": "Provider",
        "recipient": recipient,
        "worker_role": _worker_role(message_type),
        "message_type": message_type,
        "provider_id": provider_id,
        "created_at": created_at,
        "status": "ready_for_worker",
        "payload_ref": {
            "kind": "mailbox_payload",
            "mailbox_file": message_file_name,
            "mail_id": mail_id,
        },
        "work_summary": _payload_summary(message_type, payload),
        "work_anchor": _work_anchor(message_type, payload),
        "acceptance_gate": _acceptance_gate(message_type),
        "required_history": [
            "received",
            "planned",
            "action_attempted_or_unavailable",
            "observed",
            "judged",
            "receipt_or_typed_unavailable",
        ],
        "hard_nonclaims": [
            "delivery_is_not_semantic_success",
            "pane_wakeup_is_not_worker_completion",
            "storage_or_recall_requires_worker_receipt",
        ],
    }
    history = {
        "schema_version": "worker_work_history.v1",
        "work_order_id": work_order_id,
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "recipient": recipient,
        "phase": "work_order_created",
        "actor": "postman",
        "created_at": created_at,
        "summary": "Postman accepted the Provider letter, appended the mailbox payload, and created the worker work order.",
        "next_expected_actor": _worker_role(message_type),
        "status": "ready_for_worker",
    }

    work_orders_file = mailbox / "work_orders.jsonl"
    work_history_file = mailbox / "work_history.jsonl"
    append_jsonl(work_orders_file, work_order)
    append_jsonl(work_history_file, history)
    append_jsonl(postman_dir / "work_orders.jsonl", work_order)

    result = {
        "work_order_id": work_order_id,
        "work_orders_file_name": work_orders_file.name,
        "work_history_file_name": work_history_file.name,
        "acceptance_gate": work_order["acceptance_gate"],
        "worker_role": work_order["worker_role"],
    }
    if os.environ.get("YGG_DEBUG_LOCAL_PATHS") == "1":
        result["debug_paths"] = {
            "work_orders_file": str(work_orders_file),
            "work_history_file": str(work_history_file),
        }
    return result


def append_worker_history_event(
    *,
    mailbox: Path,
    mail_id: str,
    phase: str,
    actor: str,
    summary: str,
    status: str,
    work_order_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "schema_version": "worker_work_history.v1",
        "work_order_id": work_order_id or f"work-{mail_id}",
        "mail_id": mail_id,
        "phase": phase,
        "actor": actor,
        "created_at": _now(),
        "summary": summary,
        "status": status,
    }
    if evidence:
        row["evidence"] = evidence
    append_jsonl(mailbox / "work_history.jsonl", row)
    return row


def mirror_worker_receipt_to_history(
    *,
    mailbox: Path,
    mail_id: str,
    receipt: dict[str, Any],
    receipt_file: str,
    receipt_line: int | None = None,
    work_order_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any] | None:
    """Mirror a worker receipt into the mailbox work history.

    Native provider panes may write role receipts directly. Postman still owns
    the mailbox-level history view, so this bridge makes the receipt visible to
    Provider-side history readers without changing the worker's semantic result.
    """
    resolved_work_order_id = work_order_id
    in_reply_to = str(receipt.get("in_reply_to") or "")
    if not resolved_work_order_id:
        resolved_work_order_id = in_reply_to if in_reply_to.startswith("work-") else f"work-{mail_id}"

    receipt_ref = receipt_file if receipt_line is None else f"{receipt_file}:{receipt_line}"
    history_path = mailbox / "work_history.jsonl"
    for row in _read_jsonl(history_path):
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if (
            row.get("schema_version") == "worker_work_history.v1"
            and row.get("phase") == "worker_receipt_recorded"
            and row.get("work_order_id") == resolved_work_order_id
            and evidence.get("receipt_ref") == receipt_ref
        ):
            return None

    status = str(receipt.get("status") or "receipt_recorded")
    nodes = receipt.get("nodes") if isinstance(receipt.get("nodes"), list) else []
    evidence = {
        "receipt_ref": receipt_ref,
        "receipt_status": status,
        "produced_count": int(receipt.get("produced_count") or 0),
        "node_count": len(nodes),
        "storage_evidence": str(receipt.get("storage_evidence") or ""),
        "support_evidence": str(receipt.get("support_evidence") or ""),
    }
    return append_worker_history_event(
        mailbox=mailbox,
        mail_id=mail_id,
        phase="worker_receipt_recorded",
        actor=actor or str(receipt.get("role") or mailbox.name),
        summary="Worker receipt was mirrored into mailbox work history.",
        status=status,
        work_order_id=resolved_work_order_id,
        evidence=evidence,
    )


__all__ = [
    "append_postman_work_order",
    "append_worker_history_event",
    "mirror_worker_receipt_to_history",
]
