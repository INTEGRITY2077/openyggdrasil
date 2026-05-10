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
from runtime.delivery.worker_result_spec import build_worker_result_spec


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _provider_inbox_path(mailbox: Path) -> Path:
    configured = os.environ.get("YGG_PROVIDER_INBOX")
    if configured:
        return Path(configured)
    return mailbox.parent / "provider_inbox.jsonl"


def _worker_unit_index(mailbox: Path) -> int:
    name = mailbox.name.upper()
    if name.startswith("OP") and name[2:].isdigit():
        return max(1, (int(name[2:]) + 1) // 2)
    for token in ("MS", "MF"):
        if token in name:
            suffix = name.rsplit(token, 1)[-1]
            digits = "".join(char for char in suffix if char.isdigit())
            if digits:
                return max(1, int(digits))
    return 1


def _worker_role_kind(mailbox: Path) -> str:
    name = mailbox.name.upper()
    lowered = mailbox.name.lower().replace("-", "_")
    if name.startswith("OP") and name[2:].isdigit():
        return "memory_saver" if int(name[2:]) % 2 == 1 else "memory_finder"
    if "memory_finder" in lowered or "finder" in lowered or "mf" in lowered:
        return "memory_finder"
    return "memory_saver"


def _worker_surface_label(mailbox: Path) -> str:
    unit = _worker_unit_index(mailbox)
    if _worker_role_kind(mailbox) == "memory_finder":
        return f"MF{unit} Memory Finder"
    return f"MS{unit} Memory Saver"


def _append_provider_inbox(
    mailbox: Path,
    *,
    mail_id: str,
    status: str,
    produced_count: int,
    node_ids: list[str],
    result_bundle: dict[str, Any] | None,
    worker_result_spec: dict[str, Any] | None = None,
) -> None:
    worker_surface = _worker_surface_label(mailbox)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": worker_surface,
        "receiver": "Provider",
        "worker_surface": worker_surface,
        "worker_role": _worker_role_kind(mailbox),
        "mail_id": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": node_ids,
        "bundle": result_bundle,
        "result_bundle": result_bundle,
        "worker_result_spec": worker_result_spec,
        "message": f"{worker_surface} -> Provider: {mail_id} status={status} produced={produced_count}",
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
    worker_result_spec: dict[str, Any] | None = None,
) -> None:
    worker_surface = _worker_surface_label(mailbox)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": worker_surface,
        "receiver": "Provider",
        "worker_surface": worker_surface,
        "worker_role": _worker_role_kind(mailbox),
        "mail_id": mail_id,
        "produced_count": produced_count,
        "nodes": node_ids,
        "worker_result_spec": worker_result_spec,
        "message": f"{worker_surface} -> Provider: {mail_id} produced={produced_count}",
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


def _native_result_projection_text(
    mailbox: Path,
    *,
    status: str,
    produced_count: int,
    node_count: int,
    result_bundle: dict[str, Any] | None,
    worker_result_spec: dict[str, Any] | None = None,
) -> str:
    role = _worker_surface_label(mailbox)
    facts_count, paths_count = _support_counts(result_bundle)
    if produced_count > 0 or node_count > 0:
        receipt_kind = "save receipt"
        observation = f"produced_count={produced_count}, node_count={node_count}"
        judgment = "enough for storage close if the mission was to save this candidate"
    elif facts_count > 0 and paths_count > 0:
        receipt_kind = "recall receipt"
        observation = f"support_facts={facts_count}, source_paths={paths_count}"
        judgment = "receipt available for worker/provider rejudgment"
    else:
        receipt_kind = "limited receipt"
        observation = "durable evidence weak or unavailable"
        judgment = "worker/provider must inspect the result spec before any answer"
    postman_acceptance = None
    provider_action = None
    if isinstance(worker_result_spec, dict):
        postman_acceptance = worker_result_spec.get("postman_acceptance_status")
        rejudgment = worker_result_spec.get("provider_rejudgment")
        if isinstance(rejudgment, dict):
            provider_action = rejudgment.get("provider_action")
    return " | ".join(
        item
        for item in [
            f"[{role} RECEIPT NOTICE]",
            "Postman recorded a mailbox result receipt for the current work order.",
            f"receipt kind: {receipt_kind}",
            f"observation: {observation}",
            f"routing judgment: {judgment}",
            f"postman acceptance: {postman_acceptance}" if postman_acceptance else None,
            f"provider rejudgment action: {provider_action}" if provider_action else None,
            "SOT: worker_result_spec and receipt ledger; this pane is not answer material.",
        ]
        if item
    )


def _project_native_receipt_notice(
    mailbox: Path,
    *,
    status: str,
    produced_count: int,
    node_count: int,
    result_bundle: dict[str, Any] | None,
    worker_result_spec: dict[str, Any] | None = None,
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
        worker_result_spec=worker_result_spec,
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
    worker_result_spec = build_worker_result_spec(
        mailbox,
        mail_id,
        status=status,
        result_bundle=result_bundle,
        produced_count=produced_count,
        node_ids=nodes,
    )
    receipt = {
        "receipt_id": str(uuid.uuid4())[:8],
        "in_reply_to": mail_id,
        "status": status,
        "produced_count": produced_count,
        "nodes": nodes,
        "bundle": result_bundle,
        "worker_result_spec": worker_result_spec,
        "postman_acceptance_status": worker_result_spec["postman_acceptance_status"],
        "provider_rejudgment": worker_result_spec["provider_rejudgment"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_pid": os.getpid(),
        "worker_surface": _worker_surface_label(mailbox),
        "worker_role": _worker_role_kind(mailbox),
        "delivery_owner": "postman",
    }
    append_jsonl(mailbox / "delivery_receipts.jsonl", receipt)
    append_worker_history_event(
        mailbox=mailbox,
        mail_id=mail_id,
        phase="receipt_recorded",
        actor=_worker_surface_label(mailbox),
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
            worker_result_spec=worker_result_spec,
        )
    except OSError:
        pass

    try:
        _append_postman_observation(
            mailbox,
            mail_id=mail_id,
            produced_count=produced_count,
            node_ids=nodes,
            worker_result_spec=worker_result_spec,
        )
    except OSError:
        pass

    try:
        projection = _project_native_receipt_notice(
            mailbox,
            status=status,
            produced_count=produced_count,
            node_count=len(nodes),
            result_bundle=result_bundle,
            worker_result_spec=worker_result_spec,
        )
        if projection.get("enabled"):
            append_jsonl(
                mailbox / "postman_observations.jsonl",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sender": "Postman",
                    "receiver": _worker_surface_label(mailbox),
                    "worker_surface": _worker_surface_label(mailbox),
                    "worker_role": _worker_role_kind(mailbox),
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
