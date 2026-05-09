"""
Memory Worker compatibility helpers.

Legacy producer/consumer compatibility modules may call these helpers, but delivery side
effects such as provider inbox and Postman observation records are owned by
`runtime.delivery`.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.delivery.operator_result_delivery import deliver_operator_result

from runtime.log_event import warn


def build_operator_receipt(
    mail_id: str,
    *,
    status: str,
    **fields,
) -> dict:
    receipt = {
        "receipt_id": str(uuid.uuid4())[:8],
        "in_reply_to": mail_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    receipt.update(fields)
    return receipt


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_operator_receipt(
    receipts_file: Path,
    mail_id: str,
    *,
    status: str,
    **fields,
) -> dict:
    receipt = build_operator_receipt(mail_id, status=status, **fields)
    append_jsonl(receipts_file, receipt)
    return receipt


def _update_status(mailbox: Path, *, intents_processed: int = 0):
    status_file = mailbox / "status.json"
    current = {}
    if status_file.exists():
        try:
            current = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            warn("status_json_parse_failed", path=str(status_file))

    summary = current.get("session_summary", {})
    summary["intents_processed"] = intents_processed
    summary["intents_pending"] = max(0, summary.get("intents_received", 0) - intents_processed)
    current["operator_state"] = "alive"
    current["session_summary"] = summary
    current["last_updated"] = datetime.now(timezone.utc).isoformat()
    status_file.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def _update_manifest(mailbox: Path, *, state: str = "alive"):
    session_id = mailbox.name if mailbox.name.startswith("hermes-") else "hermes-A"
    manifest_file = None
    for ancestor in [mailbox.parent, mailbox.parent.parent, mailbox.parent.parent.parent]:
        candidate = ancestor / "manifest.json"
        if candidate.exists():
            manifest_file = candidate
            break
    if manifest_file is None:
        return

    current = {}
    try:
        current = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        warn("manifest_json_parse_failed", path=str(manifest_file))

    sessions = current.get("active_sessions", [])
    updated = False
    for s in sessions:
        if s.get("session_id") == session_id:
            s["operator_state"] = state
            s["intents_pending"] = 0
            updated = True
            break
    if not updated:
        sessions.append({
            "session_id": session_id,
            "provider_type": "hermes",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "operator_state": state,
            "intents_pending": 0,
        })
    current["active_sessions"] = sessions
    current["last_updated"] = datetime.now(timezone.utc).isoformat()
    manifest_file.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def deliver_receipt(
    mailbox: Path, mail_id: str, *,
    status: str = "delivered",
    result_bundle: dict | None = None,
    produced_count: int = 0,
    node_ids: list[str] | None = None,
) -> dict:
    """Compatibility wrapper; delivery side effects are owned by runtime.delivery."""
    return deliver_operator_result(
        mailbox,
        mail_id,
        status=status,
        result_bundle=result_bundle,
        produced_count=produced_count,
        node_ids=node_ids,
    )


def _ensure_q13_dirs(mailbox: Path) -> tuple[Path, Path]:
    context_dir = mailbox / "context"
    curation_dir = mailbox / "curation"
    context_dir.mkdir(exist_ok=True)
    curation_dir.mkdir(exist_ok=True)
    (curation_dir / "reports").mkdir(exist_ok=True)
    return context_dir, curation_dir


def _write_context_bundle(context_dir: Path, related_nodes: list[dict]) -> Path | None:
    if not related_nodes:
        return None
    bundle_path = context_dir / "context_bundle.md"
    lines = ["# Context Bundle\n", f"generated: {datetime.now(timezone.utc).isoformat()}\n"]
    for i, node in enumerate(related_nodes[:5], 1):
        spo = node.get("spo", {})
        lines.append(f"## {i}. {spo.get('subject', node.get('node_id', '?'))}\n")
        lines.append(f"- node_id: {node.get('node_id', '?')}\n")
        lines.append(f"- category: {spo.get('category', '?')}\n")
    bundle_path.write_text("".join(lines), encoding="utf-8")
    return bundle_path
