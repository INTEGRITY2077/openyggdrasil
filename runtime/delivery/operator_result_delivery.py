from __future__ import annotations

import json
import os
import subprocess
import time
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


def _worker_lane_session(mailbox: Path) -> str | None:
    name = mailbox.name.upper()
    if not name.startswith("OP"):
        return None
    try:
        index = int(name[2:])
    except ValueError:
        return None
    if index < 1:
        return None
    unit = (index + 1) // 2
    return f"ygg-ms{unit}" if index % 2 == 1 else f"ygg-mf{unit}"


def _support_counts(bundle: dict[str, Any] | None) -> tuple[int, int]:
    if not isinstance(bundle, dict):
        return 0, 0
    facts = bundle.get("support_facts")
    paths = bundle.get("source_paths")
    nested = bundle.get("support_bundle")
    if isinstance(nested, dict):
        facts = facts or nested.get("support_facts")
        paths = paths or nested.get("source_paths")
    return (
        len(facts) if isinstance(facts, list) else 0,
        len(paths) if isinstance(paths, list) else 0,
    )


def _support_fact_text(fact: Any) -> str:
    if isinstance(fact, dict):
        subject = fact.get("subject") or fact.get("title") or fact.get("claim") or ""
        predicate = fact.get("predicate") or ""
        obj = fact.get("object") or fact.get("summary") or fact.get("text") or ""
        text = " ".join(str(part).strip() for part in [subject, predicate, obj] if str(part).strip())
        return " ".join(text.split())
    return " ".join(str(fact).split())


def _support_summary(bundle: dict[str, Any] | None, *, limit: int = 240) -> str | None:
    if not isinstance(bundle, dict):
        return None
    facts = bundle.get("support_facts")
    nested = bundle.get("support_bundle")
    if (not isinstance(facts, list) or not facts) and isinstance(nested, dict):
        facts = nested.get("support_facts")
    if not isinstance(facts, list):
        return None
    candidates = [_support_fact_text(fact) for fact in facts]
    for text in candidates:
        lowered = text.lower()
        if "decision" in lowered or "determined" in lowered:
            return text[:limit]
    for text in candidates:
        if text:
            return text[:limit]
    return None


def _native_result_projection_text(
    mailbox: Path,
    *,
    status: str,
    produced_count: int,
    node_count: int,
    result_bundle: dict[str, Any] | None,
) -> str:
    role = "MS1 Memory Saver" if mailbox.name.upper() == "OP1" else "MF1 Memory Finder"
    facts_count, paths_count = _support_counts(result_bundle)
    support_summary = _support_summary(result_bundle)
    if mailbox.name.upper().startswith("OP") and mailbox.name[2:].isdigit():
        role_index = int(mailbox.name[2:])
        unit = (role_index + 1) // 2
        role = f"MS{unit} Memory Saver" if role_index % 2 == 1 else f"MF{unit} Memory Finder"
    if produced_count > 0 or node_count > 0:
        receipt_kind = "save receipt"
        observation = f"produced_count={produced_count}, node_count={node_count}"
        judgment = "enough for storage close if the mission was to save this candidate"
    elif facts_count > 0 and paths_count > 0:
        receipt_kind = "recall receipt"
        observation = f"support_facts={facts_count}, source_paths={paths_count}"
        judgment = "enough for recall close if these facts align with the requested topic"
    else:
        receipt_kind = "limited receipt"
        observation = "durable evidence weak or unavailable"
        judgment = "typed_unavailable unless another receipt supplies source-backed evidence"
    return " | ".join(
        item
        for item in [
            f"[{role} RESULT NOTE]",
            "Postman matched the current mailbox work order to a result receipt.",
            f"receipt kind: {receipt_kind}",
            f"observation: {observation}",
            f"support summary: {support_summary}" if support_summary else None,
            f"judgment: {judgment}",
            "SOT: Result Receipt / Evidence Pack; this pane is only the public projection.",
        ]
        if item
    )


def _project_native_result_note(
    mailbox: Path,
    *,
    status: str,
    produced_count: int,
    node_count: int,
    result_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    if os.environ.get("OY_POSTMAN_NATIVE_RESULT_PROJECTION", "0") != "1":
        return {"enabled": False, "written": False, "status": "disabled"}
    session = _worker_lane_session(mailbox)
    if not session:
        return {"enabled": True, "written": False, "status": "no_worker_lane"}
    target = f"{session}:1"
    text = _native_result_projection_text(
        mailbox,
        status=status,
        produced_count=produced_count,
        node_count=node_count,
        result_bundle=result_bundle,
    )
    try:
        has_session = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if has_session.returncode != 0:
            return {"enabled": True, "written": False, "status": "tmux_session_missing", "session": session}
        wait_deadline = time.monotonic() + float(os.environ.get("OY_POSTMAN_NATIVE_RESULT_PROJECTION_IDLE_TIMEOUT", "180"))
        while time.monotonic() < wait_deadline:
            captured = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", target, "-S", "-16"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if captured.returncode == 0:
                recent = [line.strip() for line in captured.stdout.splitlines()[-8:] if line.strip()]
                prompt_mark = "\u276f"
                separator_mark = "\u2500"
                tail_is_prompt = bool(
                    recent
                    and (
                        recent[-1] == prompt_mark
                        or (
                            len(recent) >= 2
                            and recent[-1].startswith(separator_mark)
                            and recent[-2] == prompt_mark
                        )
                    )
                )
                if tail_is_prompt and not any("msg=interrupt" in line for line in recent):
                    break
            time.sleep(1.0)
        subprocess.run(
            ["tmux", "send-keys", "-t", target, "-X", "cancel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        subprocess.run(["tmux", "set-buffer", text], check=True, capture_output=True, text=True, timeout=3)
        subprocess.run(["tmux", "paste-buffer", "-t", target], check=True, capture_output=True, text=True, timeout=3)
        subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=True, capture_output=True, text=True, timeout=3)
    except Exception as exc:  # noqa: BLE001 - result projection must never break receipt recording.
        return {
            "enabled": True,
            "written": False,
            "status": "projection_failed",
            "session": session,
            "reason": type(exc).__name__,
        }
    return {"enabled": True, "written": True, "status": "sent_to_native_pane", "session": session}


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

    try:
        projection = _project_native_result_note(
            mailbox,
            status=status,
            produced_count=produced_count,
            node_count=len(nodes),
            result_bundle=result_bundle,
        )
        if projection.get("enabled"):
            append_jsonl(
                mailbox / "postman_observations.jsonl",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sender": "Postman",
                    "receiver": mailbox.name,
                    "mail_id": mail_id,
                    "delivery_mode": "native_worker_result_projection",
                    "delivery_owner": "postman",
                    "projection": projection,
                    "hard_nonclaim": "pane_note_is_not_semantic_truth",
                },
            )
    except OSError:
        pass

    return receipt


__all__ = ["deliver_operator_result"]
