"""Structured worker receipt surface for mailbox work orders.

This module is intentionally small and deterministic. It gives MS/MF workers a
role-scoped way to close a Postman work order by writing the mailbox receipt and
mirroring that receipt into work_history. The Postman native pane transcript can
remain a fallback, but this is the normal structured close path.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.delivery.postman_work_order import (
    append_worker_history_event,
    mirror_worker_receipt_to_history,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_count = len(_read_jsonl(path))
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        fh.write("\n")
    return existing_count + 1


def _append_provider_inbox_handoff(*, worker_role: str, mail_id: str, work_order_id: str, receipt: Mapping[str, Any]) -> None:
    target = os.environ.get("YGG_PROVIDER_INBOX")
    if not target:
        return
    sender = "MF1 Memory Finder" if worker_role == "memory_finder" else "MS1 Memory Saver"
    row = {
        "schema_version": "worker_result_provider_handoff.v1",
        "sender": sender,
        "mail_id": mail_id,
        "work_order_id": work_order_id,
        "delivery_owner": "postman",
        "worker_result_spec": {
            "provider_rejudgment": {
                "provider_action": "compare_worker_result_with_current_user_question_before_answering",
                "absolute_trust_allowed": False,
            },
            "receipt_status": receipt.get("status"),
            "reason_code": receipt.get("reason_code"),
        },
    }
    _append_jsonl(Path(target), row)


def _worker_role_from_label(label: str | None) -> str:
    normalized = (label or "").strip().lower()
    if normalized in {"mf", "mf1", "consumer", "memory_finder", "memory-finder"}:
        return "memory_finder"
    if normalized in {"ms", "ms1", "producer", "memory_saver", "memory-saver"}:
        return "memory_saver"
    return normalized or "unknown"


def _receipt_path(mailbox: Path, worker_role: str) -> Path:
    if worker_role == "memory_finder":
        return mailbox / "query_receipts.jsonl"
    return mailbox / "receipts.jsonl"


def _matching_receipt(receipts: list[dict[str, Any]], *, mail_id: str | None, work_order_id: str | None) -> dict[str, Any] | None:
    for row in reversed(receipts):
        if work_order_id and row.get("in_reply_to") == work_order_id:
            return row
        if work_order_id and row.get("work_order_id") == work_order_id:
            return row
        if mail_id and row.get("in_reply_to") == mail_id:
            return row
        if mail_id and row.get("mail_id") == mail_id:
            return row
    return None


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _semantic_success_gate(
    *,
    worker_role: str,
    status: str | None,
    support_facts: list[str],
    source_paths: list[str],
    node_ids: list[str],
    produced_count: int,
    observed_missing_evidence: list[str],
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if status != "completed":
        missing.append("receipt_status_completed")
    if worker_role == "memory_finder":
        if not support_facts:
            missing.append("support_facts")
        if not source_paths:
            missing.append("source_paths")
    elif worker_role == "memory_saver":
        if produced_count <= 0:
            missing.append("produced_count")
        if not node_ids:
            missing.append("node_ids")
    else:
        missing.append("supported_worker_role")
    missing.extend(observed_missing_evidence)
    missing = _dedupe_strings(missing)
    return not missing, missing


def _existing_semantic_success(existing: Mapping[str, Any], *, worker_role: str) -> tuple[bool, list[str]]:
    support_facts = list(existing.get("support_facts") or [])
    source_paths = list(existing.get("source_paths") or [])
    node_ids = list(existing.get("node_ids") or existing.get("nodes") or [])
    observed_missing_evidence = list(existing.get("observed_missing_evidence") or [])
    try:
        produced_count = int(existing.get("produced_count") or 0)
    except (TypeError, ValueError):
        produced_count = 0
    return _semantic_success_gate(
        worker_role=worker_role,
        status=str(existing.get("status") or ""),
        support_facts=support_facts,
        source_paths=source_paths,
        node_ids=node_ids,
        produced_count=produced_count,
        observed_missing_evidence=observed_missing_evidence,
    )


def _find_work_order(
    mailbox: Path,
    *,
    mail_id: str | None = None,
    work_order_id: str | None = None,
    worker_role: str | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(mailbox / "work_orders.jsonl")
    if not rows:
        raise ValueError("work_order_not_found")

    role = _worker_role_from_label(worker_role)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("schema_version") != "postman_work_order.v1":
            continue
        if work_order_id and row.get("work_order_id") != work_order_id:
            continue
        if mail_id and row.get("mail_id") != mail_id:
            continue
        if role != "unknown" and row.get("worker_role") != role:
            continue
        candidates.append(row)

    if not candidates:
        raise ValueError("work_order_not_found")

    return candidates[-1]


def _latest_open_work_order(mailbox: Path, *, worker_role: str) -> dict[str, Any]:
    rows = _read_jsonl(mailbox / "work_orders.jsonl")
    receipts = _read_jsonl(_receipt_path(mailbox, worker_role))
    for row in reversed(rows):
        if row.get("schema_version") != "postman_work_order.v1":
            continue
        if row.get("worker_role") != worker_role:
            continue
        if _matching_receipt(
            receipts,
            mail_id=row.get("mail_id"),
            work_order_id=row.get("work_order_id"),
        ):
            continue
        return row
    raise ValueError("open_work_order_not_found")


def close_worker_work_order(
    mailbox: str | Path,
    *,
    worker_label: str,
    mail_id: str | None = None,
    work_order_id: str | None = None,
    status: str,
    reason_code: str | None = None,
    public_summary: str | None = None,
    support_facts: list[str] | None = None,
    source_paths: list[str] | None = None,
    node_ids: list[str] | None = None,
    produced_count: int = 0,
    observed_missing_evidence: list[str] | None = None,
    retry_count: int = 0,
    recorded_by: str = "worker_native_structured_receipt_tool",
) -> dict[str, Any]:
    """Write a structured worker receipt and mirror it into work_history."""

    mailbox_path = Path(mailbox).expanduser().resolve()
    worker_role = _worker_role_from_label(worker_label)
    if worker_role not in {"memory_saver", "memory_finder"}:
        raise ValueError("unsupported_worker_role")

    if mail_id or work_order_id:
        work_order = _find_work_order(
            mailbox_path,
            mail_id=mail_id,
            work_order_id=work_order_id,
            worker_role=worker_role,
        )
    else:
        work_order = _latest_open_work_order(mailbox_path, worker_role=worker_role)

    mail_id = str(work_order.get("mail_id") or mail_id or "")
    work_order_id = str(work_order.get("work_order_id") or work_order_id or "")
    receipt_file = _receipt_path(mailbox_path, worker_role)
    receipts = _read_jsonl(receipt_file)
    existing = _matching_receipt(receipts, mail_id=mail_id, work_order_id=work_order_id)
    if existing:
        existing_semantic_success, existing_missing = _existing_semantic_success(existing, worker_role=worker_role)
        mirror_worker_receipt_to_history(
            mailbox=mailbox_path,
            mail_id=mail_id,
            receipt_file=receipt_file.name,
            receipt_line=len(receipts),
            receipt=existing,
            work_order_id=work_order_id,
            actor=recorded_by,
        )
        return {
            "schema_version": "worker_structured_receipt_close_result.v1",
            "status": "already_recorded",
            "worker_role": worker_role,
            "mail_id": mail_id,
            "work_order_id": work_order_id,
            "receipt_status": existing.get("status"),
            "receipt_file_name": receipt_file.name,
            "history_written": True,
            "semantic_success_claimed": existing_semantic_success,
            "missing_evidence": existing_missing,
        }

    support_facts = list(support_facts or [])
    source_paths = list(source_paths or [])
    node_ids = list(node_ids or [])
    observed_missing_evidence = list(observed_missing_evidence or [])
    created_at = _now_iso()
    receipt_id = str(uuid.uuid4())[:8]
    semantic_success, missing_evidence = _semantic_success_gate(
        worker_role=worker_role,
        status=status,
        support_facts=support_facts,
        source_paths=source_paths,
        node_ids=node_ids,
        produced_count=int(produced_count),
        observed_missing_evidence=observed_missing_evidence,
    )
    effective_reason_code = reason_code or ("evidence_gate_failed" if not semantic_success else status)

    receipt: dict[str, Any] = {
        "schema_version": "worker_structured_receipt.v1",
        "receipt_id": receipt_id,
        "created_at": created_at,
        "recorded_by": recorded_by,
        "in_reply_to": work_order_id,
        "mail_id": mail_id,
        "work_order_id": work_order_id,
        "worker_role": worker_role,
        "status": status,
        "reason_code": effective_reason_code,
        "public_summary": public_summary or "",
        "produced_count": int(produced_count),
        "nodes": node_ids,
        "node_ids": node_ids,
        "support_facts": support_facts,
        "source_paths": source_paths,
        "observed_missing_evidence": observed_missing_evidence,
        "evidence_gate": {
            "schema_version": "worker_semantic_success_gate.v1",
            "satisfied": semantic_success,
            "missing_evidence": missing_evidence,
        },
        "retry_count": int(retry_count),
        "acceptance_gate": work_order.get("acceptance_gate"),
        "hard_nonclaims": [
            "mailbox_append_is_not_semantic_success",
            "pane_text_is_not_storage_or_recall_evidence",
            "postman_delivery_is_not_worker_completion",
        ],
    }

    if worker_role == "memory_finder":
        receipt["bundle"] = {
            "schema_version": "support_bundle_or_unavailable.v1",
            "support_facts": support_facts,
            "source_paths": source_paths,
            "typed_unavailable": None
            if semantic_success
            else {
                "schema_version": "typed_unavailable.v1",
                "reason_code": effective_reason_code,
                "detail": public_summary or "",
                "missing_evidence": missing_evidence,
            },
        }
    else:
        receipt["storage_evidence"] = {
            "schema_version": "storage_evidence_or_unavailable.v1",
            "produced_count": int(produced_count),
            "node_ids": node_ids,
            "typed_unavailable": None
            if semantic_success
            else {
                "schema_version": "typed_unavailable.v1",
                "reason_code": effective_reason_code,
                "detail": public_summary or "",
                "missing_evidence": missing_evidence,
            },
        }

    append_worker_history_event(
        mailbox=mailbox_path,
        mail_id=mail_id,
        work_order_id=work_order_id,
        phase="worker_judged",
        actor=recorded_by,
        status=status,
        summary=public_summary or "",
        evidence={
            "schema_version": "worker_judgment_evidence.v1",
            "reason_code": effective_reason_code,
            "support_fact_count": len(support_facts),
            "source_path_count": len(source_paths),
            "produced_count": int(produced_count),
            "missing_evidence": missing_evidence,
            "retry_count": int(retry_count),
        },
    )
    receipt_line = _append_jsonl(receipt_file, receipt)
    mirror_worker_receipt_to_history(
        mailbox=mailbox_path,
        mail_id=mail_id,
        receipt_file=receipt_file.name,
        receipt_line=receipt_line,
        receipt=receipt,
        work_order_id=work_order_id,
        actor=recorded_by,
    )
    _append_provider_inbox_handoff(
        worker_role=worker_role,
        mail_id=mail_id,
        work_order_id=work_order_id,
        receipt=receipt,
    )

    return {
        "schema_version": "worker_structured_receipt_close_result.v1",
        "status": "recorded",
        "worker_role": worker_role,
        "mail_id": mail_id,
        "work_order_id": work_order_id,
        "receipt_status": status,
        "reason_code": effective_reason_code,
        "receipt_file_name": receipt_file.name,
        "history_written": True,
        "semantic_success_claimed": semantic_success,
        "missing_evidence": missing_evidence,
        "support_fact_count": len(support_facts),
        "source_path_count": len(source_paths),
        "produced_count": int(produced_count),
    }
