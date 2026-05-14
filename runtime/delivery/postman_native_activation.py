from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.delivery.tmux_lane_adapter import paste_text_enter


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


def _send_tmux_target_text(target: str, text: str) -> tuple[bool, str]:
    try:
        validate_visible_notice_route_only(text)
    except ValueError as exc:
        return False, str(exc)
    result = paste_text_enter(
        target,
        text,
        reason="postman_native_activation",
        cancel_existing_prompt=False,
        validate_worker_payload=True,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "tmux_lane_adapter_failed").strip()
    return True, "sent"


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
    role = _worker_role(label, role_type)
    if role_type == "producer":
        request_name = "Save Request"
    elif message_type == "query":
        request_name = "Find Request"
    else:
        request_name = "Work Request"
    prompt = (
        "메일 전달 알림\n"
        f"lane: {label}\n"
        f"role: {role}\n"
        f"kind: {request_name}\n"
        f"mail_id: {delivery.get('mail_id') or 'unknown'}\n"
        f"work_order_id: {delivery.get('work_order_id') or 'unknown'}\n"
        "request_hint: mailbox work order ready\n\n"
        "상세 내용은 mailbox work order에 있습니다. 이 알림은 깨우기 전용이며 mailbox 확인만 요청합니다."
    )
    validate_visible_notice_route_only(prompt)
    return prompt


def verify_visible_notice_contract() -> dict[str, Any]:
    prompt = _activation_prompt(
        label="MS1",
        role_type="producer",
        message_type="query",
        payload={"query_text": "answer support judgment should not leak"},
        delivery={"mail_id": "mail-test", "work_order_id": "work-test"},
    )
    lowered = prompt.lower()
    leaked = [term for term in VISIBLE_NOTICE_FORBIDDEN_TERMS if term.lower() in lowered]
    return {
        "schema_version": "postman_visible_notice_contract_check.v1",
        "status": "pass" if not leaked else "fail",
        "hidden_by_default_env": "OY_POSTMAN_VISIBLE_CPR=0",
        "visible_mode_policy": "dev_fallback_only",
        "mission_summary_included": False,
        "semantic_material_terms_present": leaked,
        "cancel_existing_prompt": False,
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
        "phase": "postman_cpr_sent",
        "actor": "postman",
        "created_at": timestamp,
        "summary": "Postman woke the native provider pane with a short mailbox work-order notice.",
        "status": "cpr_sent",
    }
    _append_jsonl(sessions_dir / op / "work_history.jsonl", work_history)

    visible_cpr = os.environ.get("OY_POSTMAN_VISIBLE_CPR", "0") == "1"
    prompt = ""
    if visible_cpr:
        prompt = _activation_prompt(
            label=label,
            role_type=role_type,
            message_type=message_type,
            payload=payload,
            delivery=delivery,
        )
        written, reason = _send_tmux_target_text(target, prompt)
    else:
        written, reason = False, "mailbox_work_order_recorded"

    result = {
        **base,
        "status": "sent_to_native_pane" if written else "recorded_for_worker_loop",
        "reason_code": "native_pane_activated" if written else reason,
        "target": target,
        "activation_surface": "mailbox_work_order_notice.v1",
        "work_order_id": delivery.get("work_order_id"),
        "work_history_file": delivery.get("work_history_file"),
        "semantic_receipt_included": False,
        "visible_notice_semantic_material_included": False,
        "cancel_existing_prompt": False,
        "prompt_contract": "hidden_by_default_route_only_notice_when_visible",
        "visible_cpr": visible_cpr,
    }
    _append_jsonl(registry_dir / "postman" / "activation_log.jsonl", result)
    _append_jsonl(sessions_dir / op / "postman_activation.jsonl", result)
    return result


__all__ = ["activate_native_lane", "validate_visible_notice_route_only", "verify_visible_notice_contract"]
