from __future__ import annotations

import json
import os
import re
import subprocess
import time

from runtime.delivery.tmux_lane_adapter import paste_text_enter
from runtime.polling.mailbox_summary import _append_goal_log, _mark_live_delivered
from runtime.polling.receipt_quality import (
    _mission_text,
    _receipt_public_summary_for_event,
    _short,
    _tst_supervisor_for_receipt,
    _worker_program_public,
    _worker_start_interpretation,
)
from runtime.polling.ygg_poll_context import MAILBOX, MODE, role, tmux_target

def _worker_owned_native_loop_text(event: dict) -> str:
    """Public start note for worker-owned MS/MF action."""

    mission = _short(_mission_text(event), 900)
    interpretation = _worker_start_interpretation()
    return (
        f"[{role} 작업 시작]\n"
        f"받은 일: {mission}\n\n"
        f"내 역할: {interpretation['role_name']}.\n"
        f"내 해석: {interpretation['read']}\n"
        f"내가 세운 작업 방향: {interpretation['work_plan']}.\n"
        f"지금 하는 일: {interpretation['action']} "
        "결과를 보면 그대로 답하지 않고 계속할지, 거절할지, 다른 각도로 다시 볼지 정합니다."
    )

def _send_worker_owned_native_loop(event: dict) -> dict:
    mail_id = str(event.get("mail_id") or "?")
    delivery_id = str(event.get("delivery_id") or "?")
    prompt = _worker_owned_native_loop_text(event)
    if _worker_trace_to_hermes_chat():
        readiness = _wait_context_card_lane_ready(
            float(os.environ.get("OY_OP_WORKER_OWNED_READY_WAIT_SECONDS", "120"))
        )
        if not readiness.get("ready"):
            row = {
                "delivery_id": delivery_id,
                "mail_id": mail_id,
                "mode": "produce" if MODE == "produce" else "consume",
                "phase": "worker_owned_native_loop_blocked",
                "context_window_written": False,
                "context_card_status": "lane_not_ready",
                "evidence": readiness.get("evidence"),
                "timestamp": time.time(),
            }
            _append_goal_log(row)
            return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
        before_session_id = _extract_session_id_from_tmux()
        paste = _paste_context_prompt(prompt)
    else:
        before_session_id = None
        paste = _emit_worker_surface_text(prompt)
    status = "sent_to_worker_owned_native_loop" if paste.get("written") else "worker_owned_native_loop_send_failed"
    if paste.get("written"):
        _mark_live_delivered(event, status=status)

    row = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": "produce" if MODE == "produce" else "consume",
        "phase": "worker_owned_native_loop_dispatched",
        "context_window_written": bool(paste.get("written")),
        "context_card_status": paste.get("status"),
        "session_id_before_send": before_session_id,
        "tmux_target": tmux_target,
        "status": status,
        "mission_preview": _short(_mission_text(event), 240),
        "stderr": paste.get("stderr"),
        "timestamp": time.time(),
    }
    _append_goal_log(row)
    with open(MAILBOX / "live_worker_owned_loop_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return paste

def _append_worker_owned_loop_log(row: dict) -> None:
    with open(MAILBOX / "live_worker_owned_loop_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def _emit_worker_surface_text(text: str) -> dict:
    print("\n" + "─" * 40, flush=True)
    print(text, flush=True)
    print("─" * 40, flush=True)
    return {"written": True, "status": "printed_to_worker_pane", "stderr": ""}

def _worker_trace_to_hermes_chat() -> bool:
    return os.environ.get("OY_WORKER_TRACE_TO_HERMES", "0") == "1"

def _worker_owned_receipt_projection_text(event: dict, receipt: dict | None, status: str,
                                          elapsed_ms: int, attempts: list[dict]) -> str:
    summary = _receipt_public_summary_for_event(event, receipt)
    supervisor = _tst_supervisor_for_receipt(receipt)
    program = _worker_program_public(supervisor)
    judgment = "success" if summary.get("quality") in {"pass", "pass_with_limit"} else "typed_unavailable"
    if MODE == "produce":
        action = "저장 후보를 source/provenance 기준으로 검사했습니다"
        success_line = "저장 근거가 충분합니다" if judgment == "success" else "저장 근거가 부족합니다"
        close_decision = "저장 receipt로 닫음" if judgment == "success" else "저장 불가로 닫음"
    else:
        action = "질문 표식에 맞는 기억 후보와 출처를 확인했습니다"
        success_line = "회상 근거가 질문과 맞습니다" if judgment == "success" else "회상 근거가 질문과 맞지 않거나 부족합니다"
        close_decision = "support bundle로 닫음" if judgment == "success" else "불가로 닫음"
    final_after = program["delta_after"]
    if judgment != "success":
        final_after = (
            "reject_misaligned_support"
            if summary.get("alignment_status") == "misaligned"
            else "typed_unavailable"
        )
    final_delta_verified = bool(supervisor) and program["delta_before"] != final_after
    supervisor_line = (
        f"내가 세운 실행 계획: {program['goal']} "
        f"({program['mode']}, review={program['review']}).\n"
        f"선택한 도구: {program['selected_tools']}.\n"
        f"실행 순서: {program['steps'] or 'not recorded'}.\n"
        f"관찰 뒤 판단 변화: {program['delta_before']} -> {final_after} "
        f"(delta={'pass' if final_delta_verified else 'weak'})."
        if supervisor
        else "내가 세운 실행 계획: receipt에 계획 증거가 없어 action surface missing으로 취급합니다."
    )
    return (
        f"[{role} 작업 관찰]\n"
        f"받은 일: {_short(_mission_text(event), 700)}\n\n"
        f"{supervisor_line}\n"
        f"내가 한 일: {action}.\n"
        f"본 것: {summary.get('result')}; 시도={len(attempts)}; 처리시간={elapsed_ms}ms.\n"
        f"내 판단: {judgment}. {success_line}; 정렬={summary.get('alignment_status')}.\n"
        f"닫는 방식: {close_decision}.\n"
        f"넘지 않을 선: {summary.get('limitation')}"
    )

def _send_worker_owned_receipt_projection(event: dict, receipt: dict | None, status: str,
                                          elapsed_ms: int, attempts: list[dict]) -> dict:
    prompt = _worker_owned_receipt_projection_text(event, receipt, status, elapsed_ms, attempts)
    if _worker_trace_to_hermes_chat():
        readiness = _wait_context_card_lane_ready(
            float(os.environ.get("OY_OP_WORKER_OWNED_READY_WAIT_SECONDS", "120"))
        )
        if not readiness.get("ready"):
            return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
        before_session_id = _extract_session_id_from_tmux()
        paste = _paste_context_prompt(prompt)
    else:
        before_session_id = None
        paste = _emit_worker_surface_text(prompt)
    row = {
        "timestamp": time.time(),
        "mode": "produce" if MODE == "produce" else "consume",
        "role": role,
        "delivery_id": event.get("delivery_id"),
        "mail_id": event.get("mail_id"),
        "tmux_target": tmux_target,
        "session_id_before_send": before_session_id,
        "phase": "worker_owned_receipt_projection",
        "sent": bool(paste.get("written")),
        "written": bool(paste.get("written")),
        "status": paste.get("status"),
        "result_preview": prompt[:600],
    }
    _append_worker_owned_loop_log(row)
    return row

def _paste_context_prompt(prompt: str) -> dict:
    prompt = " ".join(str(prompt).splitlines())
    paste = paste_text_enter(tmux_target, prompt, reason="context_prompt")
    if paste.returncode == 0:
        time.sleep(float(os.environ.get("OY_OP_CONTEXT_CARD_POST_SEND_GRACE_SECONDS", "5")))
    return {
        "written": paste.returncode == 0,
        "status": "written" if paste.returncode == 0 else "failed",
        "stderr": (paste.stderr or paste.stdout or "").strip()[:240],
    }

def _extract_session_id_from_tmux() -> str | None:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", tmux_target, "-S", "-180"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        return None
    matches = re.findall(r"\bSession:\s*([A-Za-z0-9_-]+)", result.stdout)
    return matches[-1] if matches else None

def _wait_context_card_lane_ready(timeout_seconds: float = 120.0) -> dict:
    deadline = time.time() + timeout_seconds
    stable_seconds = float(os.environ.get("OY_OP_NATIVE_GOAL_READY_STABLE_SECONDS", "2.5"))
    busy_markers = (
        "Initializing agent",
        "analyzing",
        "Operation interrupted",
        "[Interrupted",
        "waiting for model response",
        "deliberating",
        "New message detected",
        "msg=interrupt",
        "⚡",
        "Sending after interrupt",
        "brainstorming",
        "ruminating",
        "pondering",
        "mulling",
        "thinking",
        "⏱",
    )
    last_tail = ""
    ready_since = None
    ready_evidence = ""
    while time.time() <= deadline:
        captured = subprocess.run(
            ["tmux", "capture-pane", "-t", tmux_target, "-p", "-S", "-30"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        last_tail = captured.stdout[-2000:] if captured.returncode == 0 else (captured.stderr or "")
        tail_lines = [line for line in last_tail.splitlines() if line.strip()]
        recent = "\n".join(tail_lines[-6:])
        has_prompt = any(line.strip() == "❯" or line.strip().endswith("❯") for line in tail_lines[-4:])
        busy = any(marker in recent for marker in busy_markers)
        if has_prompt and not busy:
            if ready_since is None:
                ready_since = time.time()
                ready_evidence = "prompt_visible_stabilizing"
            elif time.time() - ready_since >= stable_seconds:
                return {"ready": True, "evidence": ready_evidence}
        else:
            ready_since = None
        time.sleep(1.0)
    return {"ready": False, "evidence": _short(last_tail, 300)}


__all__ = [
    "_worker_owned_native_loop_text",
    "_send_worker_owned_native_loop",
    "_append_worker_owned_loop_log",
    "_emit_worker_surface_text",
    "_worker_trace_to_hermes_chat",
    "_worker_owned_receipt_projection_text",
    "_send_worker_owned_receipt_projection",
    "_paste_context_prompt",
    "_extract_session_id_from_tmux",
    "_wait_context_card_lane_ready",
]
