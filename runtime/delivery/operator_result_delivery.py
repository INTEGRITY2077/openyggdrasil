from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.common.jsonl_io import append_jsonl
from runtime.delivery.tmux_lane_adapter import (
    cancel_prompt,
    paste_text_enter,
    validate_no_worker_judgment_payload,
)
from runtime.delivery.postman_work_order import append_worker_history_event
from runtime.delivery.worker_result_spec import build_worker_result_spec


def _provider_inbox_path(mailbox: Path) -> Path:
    configured = os.environ.get("YGG_PROVIDER_INBOX")
    if configured:
        return Path(configured)
    return mailbox.parent / "provider_inbox.jsonl"


def _provider_id() -> str:
    return (os.environ.get("OY_PROVIDER_ID") or "hermes").strip() or "hermes"


def _provider_profile(provider_id: str) -> str:
    configured = (os.environ.get("OY_PROVIDER_PROFILE") or "").strip()
    if configured:
        return configured
    return "openyggdrasil-provider" if provider_id == "hermes" else f"openyggdrasil-{provider_id}"


def _provider_session_id() -> str:
    return (
        os.environ.get("YGG_PROVIDER_SESSION_ID")
        or os.environ.get("OY_PROVIDER_SESSION_ID")
        or "ygg-pro1"
    ).strip() or "ygg-pro1"


def _workspace_root(*, provider_id: str, provider_profile: str, provider_session_id: str) -> Path:
    candidates = [
        os.environ.get("OY_PROVIDER_WORKSPACE_ROOT"),
        os.environ.get("OY_PRIVATE_DEV"),
        str(Path(__file__).resolve().parents[2]),
        os.environ.get("OPENYGGDRASIL_REPO"),
    ]
    seen: set[Path] = set()
    roots = []
    for candidate in candidates:
        if not candidate:
            continue
        root = Path(candidate).expanduser()
        if root in seen:
            continue
        seen.add(root)
        roots.append(root)
    try:
        from runtime.attachments.provider_attachment import provider_attachment_root

        for root in roots:
            if (
                provider_attachment_root(
                    workspace_root=root,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    provider_session_id=provider_session_id,
                )
                / "session_attachment.v1.json"
            ).exists():
                return root
    except Exception:
        pass
    return roots[0] if roots else Path(__file__).resolve().parents[2]


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


def _inject_provider_cpr_handoff(
    mailbox: Path,
    *,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    if _worker_role_kind(mailbox) != "memory_finder":
        return {"status": "not_applicable", "reason_code": "worker_role_not_memory_finder"}
    provider_id = _provider_id()
    provider_profile = _provider_profile(provider_id)
    provider_session_id = _provider_session_id()
    try:
        from runtime.delivery.postman_heartbeat_cpr import inject_postman_heartbeat_cpr_to_provider_inbox

        delivery = inject_postman_heartbeat_cpr_to_provider_inbox(
            workspace_root=_workspace_root(
                provider_id=provider_id,
                provider_profile=provider_profile,
                provider_session_id=provider_session_id,
            ),
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            live_group={
                "provider": {"status": "ready", "session_name": provider_session_id},
                "ms1": {"status": "ready", "session_name": "ygg-ms1"},
                "mf1": {"status": "ready", "session_name": "ygg-mf1"},
            },
            engine_status={
                "tmux": {"status": "ready"},
                "postman_helper": {"status": "ready"},
                "mailbox": {"status": "ready"},
                "receipt_registry": {"status": "ready", "receipt_id": receipt.get("receipt_id")},
            },
            mf1_receipt=receipt,
        )
    except Exception as exc:  # noqa: BLE001 - CPR handoff must not break receipt recording.
        return {
            "status": "failed",
            "reason_code": exc.__class__.__name__,
            "provider_session_id": provider_session_id,
        }
    payload = delivery.get("payload") if isinstance(delivery, dict) else {}
    handoff = payload.get("provider_inbox_handoff") if isinstance(payload, dict) else {}
    return {
        "status": delivery.get("delivery_status") or "created",
        "heartbeat_cpr_status": payload.get("heartbeat_cpr_status") if isinstance(payload, dict) else None,
        "handoff_status": handoff.get("handoff_status") if isinstance(handoff, dict) else None,
        "provider_session_id": provider_session_id,
        "message_id": delivery.get("message_id"),
    }


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
    if os.environ.get("OY_ALLOW_UNSAFE_POSTMAN_RESULT_PROJECTION", "0") != "1":
        return {
            "enabled": False,
            "written": False,
            "status": "disabled_unsafe_postman_result_projection_guard",
            "hard_nonclaim": "postman_result_projection_is_not_live_worker_judgment",
        }
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
        validate_no_worker_judgment_payload(text)
    except ValueError as exc:
        return {
            "enabled": True,
            "written": False,
            "status": "blocked_worker_judgment_payload",
            "session": session,
            "reason": str(exc),
        }
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
        cancel_prompt(target, reason="operator_result_delivery")
        result = paste_text_enter(target, text, reason="operator_result_delivery", timeout=3)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "tmux_lane_adapter_failed").strip())
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

    provider_cpr = _inject_provider_cpr_handoff(mailbox, receipt=receipt)
    receipt["provider_cpr"] = provider_cpr
    if provider_cpr.get("status") != "not_applicable":
        try:
            append_jsonl(
                mailbox / "postman_observations.jsonl",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sender": "Postman",
                    "receiver": "Provider",
                    "worker_surface": _worker_surface_label(mailbox),
                    "worker_role": _worker_role_kind(mailbox),
                    "mail_id": mail_id,
                    "delivery_mode": "provider_cpr_packet",
                    "delivery_owner": "postman",
                    "provider_cpr": provider_cpr,
                    "hard_nonclaim": "cpr_packet_is_handoff_metadata_not_answer_material",
                },
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
