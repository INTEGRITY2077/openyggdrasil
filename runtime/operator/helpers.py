"""
Operator Helpers — 14차 Axis 3: operator_entrypoint.py에서 분리.

공유 유틸리티: _update_status, _update_manifest, deliver_receipt, Q13 utilities
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.log_event import warn


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
    mailbox.mkdir(parents=True, exist_ok=True)
    delivery_file = mailbox / "delivery_receipts.jsonl"
    receipt = {
        "receipt_id": str(uuid.uuid4())[:8],
        "in_reply_to": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": node_ids or [],
        "bundle": result_bundle,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_pid": os.getpid(),
    }
    with open(delivery_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

    _append_provider_inbox(mailbox, mail_id, status, produced_count, node_ids or [], result_bundle)

    # Track 1 (계약): Mailbox JSONL — 위에서 완료.
    # Track 2 (관찰): 채팅창 주입 금지. Hermes 네이티브 세션에 tmux send-keys로
    # Postman 알림을 넣으면 진행 중 API call이 interrupt되어 비동기 UX가 깨진다.
    # 따라서 관찰용 로그 파일에만 남긴다.
    _postman_notify(mailbox, mail_id, produced_count, node_ids or [])

    return receipt


def _append_provider_inbox(
    mailbox: Path,
    mail_id: str,
    status: str,
    produced: int,
    nodes: list[str],
    bundle: dict | None,
) -> None:
    """OP→Provider 비동기 수신면. 채팅창 주입 없이 Provider가 읽을 inbox에 기록한다."""
    try:
        provider_inbox = Path(os.environ.get("YGG_PROVIDER_INBOX") or (Path.home() / ".yggdrasil" / "provider_inbox.jsonl"))
        provider_inbox.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": mailbox.name,
            "receiver": "Provider",
            "mail_id": mail_id,
            "status": status,
            "produced_count": produced,
            "nodes": nodes,
            "bundle": bundle,
            "result_bundle": bundle,
            "message": f"📬 {mailbox.name}→Provider: {mail_id} status={status} produced={produced}",
            "delivery_mode": "provider_inbox_file",
        }
        with open(provider_inbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _postman_notify(mailbox: Path, mail_id: str, produced: int, nodes: list[str]):
    """Track 2: 관찰용 로그만 기록한다. Hermes 채팅창에는 절대 주입하지 않는다."""
    try:
        op_name = mailbox.name

        vault = Path("/mnt/d/0_PROJECT/openyggdrasil/vault")
        titles = []
        for nid in nodes[:3]:
            for cat in ["concepts", "entities", "comparisons"]:
                f = vault / cat / f"{nid}.md"
                if f.exists():
                    for line in f.read_text(encoding="utf-8").split("\n"):
                        if line.startswith("title:"):
                            titles.append(line.split(":", 1)[1].strip().strip('"'))
                            break
                    break

        report = ", ".join(titles[:3]) if titles else "no title"
        observation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": op_name,
            "receiver": "Provider",
            "mail_id": mail_id,
            "produced_count": produced,
            "nodes": nodes,
            "titles": titles,
            "message": f"📬 {op_name}→Provider: {mail_id} produced={produced} [{report}]",
            "delivery_mode": "mailbox_log_only",
            "hard_nonclaim": "not_injected_into_hermes_chat",
        }
        with open(mailbox / "postman_observations.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(observation, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
