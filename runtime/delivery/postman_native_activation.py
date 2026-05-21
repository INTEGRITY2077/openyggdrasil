from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

POSTMAN_PANE_NOTICE_RETIRED_REASON = "postman_pane_notice_retired_worker_loop_only"


VISIBLE_NOTICE_FORBIDDEN_TERMS = (
    "answer",
    "support",
    "support_facts",
    "judgment",
    "quality_assessment",
    "provider_rejudgment",
    "worker_judgment",
    "답변",
    "근거",
    "판단",
    "결론",
)


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _tmux_session_exists(session: str) -> bool:
    return _tmux("has-session", "-t", session).returncode == 0


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _worker_role(label: str, role_type: str) -> str:
    if "Memory Saver" in label or "Memory Finder" in label:
        return label
    if role_type == "producer":
        return f"{label} Memory Saver"
    return f"{label} Memory Finder"


def _mission_summary(message_type: str, payload: Mapping[str, Any]) -> str:
    if message_type == "query":
        text = payload.get("query_text") or payload.get("query") or ""
    elif message_type == "memory_ticket":
        text = payload.get("surface_reason") or payload.get("decision_capsule") or payload.get("topic_hint") or ""
    else:
        text = payload.get("context_snapshot") or ""
    normalized = " ".join(str(text).split())
    return normalized[:700] if normalized else "(empty mission)"


def _native_pane_target(session: str) -> str:
    listed = _tmux("list-windows", "-t", session, "-F", "#{window_index}:#{window_name}:#{window_active}")
    if listed.returncode != 0:
        return session
    parsed: list[dict[str, Any]] = []
    for line in listed.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            parsed.append({"index": parts[0], "name": parts[1], "active": parts[2] == "1"})
    if not parsed:
        return session
    for row in parsed:
        if row["active"] and row["name"] != "live-postman":
            return f"{session}:{row['index']}"
    for row in parsed:
        if row["name"] != "live-postman":
            return f"{session}:{row['index']}"
    return f"{session}:{parsed[0]['index']}"


def _capture_tmux_target_text(target: str, *, lines: int = 80) -> str:
    result = _tmux("capture-pane", "-p", "-t", target, "-S", f"-{max(lines, 1)}")
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _recent_nonempty_lines(text: str, *, limit: int = 16) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[-max(1, limit) :]


def _looks_idle_at_prompt(text: str) -> bool:
    prompt_marker = chr(0x276F)
    for line in reversed(_recent_nonempty_lines(text, limit=10)):
        if line == prompt_marker or line.endswith(f" {prompt_marker}") or line.startswith(f"{prompt_marker} "):
            return True
        if "msg=interrupt" in line.lower() or "ctrl+c cancel" in line.lower():
            return False
    return False


def _native_pane_status(target: str) -> dict[str, Any]:
    text = _capture_tmux_target_text(target)
    if _looks_idle_at_prompt(text):
        return {
            "status": "idle",
            "reason_code": "native_pane_idle_prompt_visible",
        }
    recent = "\n".join(_recent_nonempty_lines(text, limit=24)).lower()
    if "preflight compression" in recent:
        return {
            "status": "busy",
            "reason_code": "native_pane_busy_preflight_compression",
        }
    busy_markers = (
        "msg=interrupt",
        "/queue",
        "/bg",
        "ctrl+c cancel",
        "cogitating",
        "pondering",
        "reasoning...",
    )
    if any(marker in recent for marker in busy_markers):
        return {
            "status": "busy",
            "reason_code": "native_pane_busy_existing_work",
        }
    return {
        "status": "idle",
        "reason_code": "native_pane_idle",
    }


def validate_visible_notice_route_only(text: str) -> None:
    lowered = str(text or "").lower()
    blocked = [term for term in VISIBLE_NOTICE_FORBIDDEN_TERMS if term.lower() in lowered]
    if blocked:
        raise ValueError(f"visible_notice_contains_semantic_material:{','.join(blocked)}")




def _activation_prompt(
    *,
    label: str,
    role_type: str,
    message_type: str,
    payload: Mapping[str, Any],
    delivery: Mapping[str, Any],
) -> str:
    del label, role_type, message_type, payload, delivery
    raise RuntimeError(POSTMAN_PANE_NOTICE_RETIRED_REASON)


def verify_visible_notice_contract() -> dict[str, Any]:
    return {
        "schema_version": "postman_visible_notice_contract_check.v1",
        "status": "pass",
        "visible_by_default_env": "ignored; Postman pane notice is retired",
        "visible_mode_policy": POSTMAN_PANE_NOTICE_RETIRED_REASON,
        "tmux_pane_write_allowed": False,
        "mission_summary_included": False,
        "semantic_material_terms_present": [],
        "cancel_existing_prompt": False,
        "worker_surface_owner": "MS1/MF1 worker loop after mailbox row read",
    }


def activate_native_lane(
    *,
    op: str,
    label: str,
    role_type: str,
    session: str,
    delivery: dict[str, Any],
    message_type: str,
    payload: dict[str, Any],
    registry_dir: Path,
    sessions_dir: Path,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    base = {
        "schema_version": "postman_native_activation.v1",
        "created_at": timestamp,
        "recipient": op,
        "role": _worker_role(label, role_type),
        "delivery_id": delivery.get("delivery_id"),
        "mail_id": delivery.get("mail_id"),
        "message_type": message_type,
        "session": session,
        "activation_owner": "postman",
        "legacy_debug_monitor_used": False,
    }
    if not _tmux_session_exists(session):
        result = {
            **base,
            "status": "blocked",
            "reason_code": "memory_lane_tmux_session_missing",
        }
        _append_jsonl(registry_dir / "postman" / "activation_log.jsonl", result)
        _append_jsonl(sessions_dir / op / "postman_activation.jsonl", result)
        return result

    target = _native_pane_target(session)
    work_history = {
        "schema_version": "worker_work_history.v1",
        "work_order_id": delivery.get("work_order_id"),
        "delivery_id": delivery.get("delivery_id"),
        "mail_id": delivery.get("mail_id"),
        "recipient": op,
        "phase": "postman_work_order_recorded",
        "actor": "postman",
        "created_at": timestamp,
        "summary": "Postman recorded the mailbox work order. It did not write to the worker pane.",
        "status": "recorded",
        "hard_nonclaim": "worker_pane_surface_must_be_authored_by_worker_after_mailbox_row_read",
    }
    _append_jsonl(sessions_dir / op / "work_history.jsonl", work_history)

    visible_cpr_requested = os.environ.get("OY_POSTMAN_VISIBLE_CPR", "0") == "1"
    visible_cpr = False
    prompt = ""
    pane_status = _native_pane_status(target)
    written, reason = False, POSTMAN_PANE_NOTICE_RETIRED_REASON

    result = {
        **base,
        "status": "sent_to_native_pane" if written else "recorded_for_worker_loop",
        "reason_code": "native_pane_activated" if written else reason,
        "target": target,
        "activation_surface": "mailbox_work_order_recorded.worker_loop_only",
        "work_order_id": delivery.get("work_order_id"),
        "work_history_file": delivery.get("work_history_file"),
        "semantic_receipt_included": False,
        "visible_notice_semantic_material_included": False,
        "cancel_existing_prompt": False,
        "prompt_contract": "postman_does_not_write_worker_pane",
        "visible_cpr": visible_cpr,
        "visible_cpr_requested": visible_cpr_requested,
        "tmux_pane_write_attempted": False,
        "native_pane_status": pane_status,
    }
    _append_jsonl(registry_dir / "postman" / "activation_log.jsonl", result)
    _append_jsonl(sessions_dir / op / "postman_activation.jsonl", result)
    return result


__all__ = ["activate_native_lane", "validate_visible_notice_route_only", "verify_visible_notice_contract"]
