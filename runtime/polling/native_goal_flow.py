from __future__ import annotations

import os
import re
import subprocess
import time

from runtime.delivery.tmux_lane_adapter import paste_text_enter
from runtime.polling.mailbox_summary import _append_native_goal_log
from runtime.polling.receipt_quality import _mission_text, _receipt_public_summary_for_event, _short
from runtime.polling.worker_owned_loop import _extract_session_id_from_tmux, _wait_context_card_lane_ready
from runtime.polling.ygg_poll_context import MODE, NATIVE_GOAL_MODE, NATIVE_GOAL_STAGE_GOALS, role, tmux_target

def _native_goal_text(event: dict, receipt: dict | None, attempts: list[dict], status: str) -> str:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    mission = payload.get("query_text") or payload.get("context_snapshot") or payload.get("decision") or ""
    summary = _receipt_public_summary_for_event(event, receipt or {})
    return (
        f"/goal {role} live job {event.get('mail_id')}: "
        "Use the completed mailbox result to answer the user-facing memory task. "
        f"Mission: {_short(mission, 220)}. "
        f"Observed: {status}; {summary['quality']}; {summary['result']}. "
        "Explain goal, evidence quality, answer or unavailable reason, limits, and next action. "
        "Do not expose local paths, internal commands, hidden chain-of-thought, or receipt ids. "
        "Finish only after a useful public answer is written."
    )

def _native_goal_start_text(event: dict) -> str:
    mission = _mission_text(event)
    action = (
        "read the live mailbox task, choose the bounded PTC/retrieval action, "
        "wait for an ACTION_RESULT observation, then judge evidence quality"
        if MODE == "consume"
        else "read the live mailbox task, save the memory candidate, wait for an "
        "ACTION_RESULT observation, then judge storage evidence quality"
    )
    return (
        f"/goal {role} live job {event.get('mail_id')}: "
        "Stage 1 of a legacy/debug staged-goal proof loop. "
        f"Mission: {_short(mission, 260)}. "
        f"Required action now: {action}. "
        "Required response now: WORKER_STEP_1_ACTION only. "
        "State the goal, what evidence is needed, and what action is now being performed. "
        "Do not answer from memory. Do not write a final answer. "
        "End with exactly: AWAITING_ACTION_RESULT. "
        "This stage goal is complete when WORKER_STEP_1_ACTION and AWAITING_ACTION_RESULT are visible. "
        "The optional debug lens may provide the next stage; do not keep working after that marker. "
        "Waiting for ACTION_RESULT or RETRY_RESULT is debug-lens progress, not user input, "
        "and must not be treated as done or blocked. "
        "Do not expose local paths, internal commands, hidden chain-of-thought, or receipt ids."
    )

def _public_observation_detail(summary: dict) -> str:
    detail = str(summary.get("detail") or "")
    detail = re.sub(r"\breceipt=[A-Za-z0-9_-]+", "processing_evidence=observed", detail)
    detail = re.sub(r"\bpid=\d+", "pid=hidden", detail)
    return _short(detail, 240)

def _native_goal_action_result_text(event: dict, receipt: dict | None, attempts: list[dict],
                                    status: str, result: subprocess.CompletedProcess | None,
                                    elapsed_ms: int) -> str:
    summary = _receipt_public_summary_for_event(event, receipt or {})
    attempt_text = ", ".join(
        f"attempt {a.get('attempt')} returncode={a.get('returncode')} "
        f"{'result_observed' if a.get('receipt_id') else 'no_result'}"
        for a in attempts
    ) or "no attempts"
    process_status = "completed" if result and result.returncode == 0 else "failed"
    return (
        f"ACTION_RESULT for {role} live job {event.get('mail_id')}: "
        f"actual worker action {process_status}; live_status={status}; elapsed_ms={elapsed_ms}; "
        f"attempts={_short(attempt_text, 220)}. "
        f"Evidence quality: {summary['quality']}; observed result: {summary['result']}; "
        f"support detail: {_public_observation_detail(summary)}. "
        f"Limit: {summary['limitation']} "
        "Runtime output is recorded in private logs and is not pasted into this chat. "
        "Required response now: WORKER_STEP_2_OBSERVE_EVALUATE only. "
        "Explain what action just happened, compare the observation against the user's question, "
        "and judge whether support is enough or weak. "
        "Do not write the final answer and do not continue into the next stage by yourself. "
        "End with exactly: AWAITING_RETRY_OR_ANSWER_REQUIRED. "
        "Do not expose local paths, internal commands, hidden chain-of-thought, or receipt ids."
    )

def _send_native_goal_start(event: dict) -> dict:
    if not NATIVE_GOAL_MODE:
        return {"sent": False, "status": "disabled"}
    text = _native_goal_start_text(event)
    before_session_id = _extract_session_id_from_tmux()
    paste = paste_text_enter(tmux_target, text, reason="native_goal_start")
    if paste.returncode == 0:
        time.sleep(float(os.environ.get("OY_OP_NATIVE_GOAL_POST_SEND_GRACE_SECONDS", "3")))
    row = {
        "timestamp": time.time(),
        "mode": "produce" if MODE == "produce" else "consume",
        "role": role,
        "delivery_id": event.get("delivery_id"),
        "mail_id": event.get("mail_id"),
        "tmux_target": tmux_target,
        "session_id_before_send": before_session_id,
        "native_goal_command": True,
        "native_goal_phase": "start_action_loop",
        "sent": paste.returncode == 0,
        "status": "sent" if paste.returncode == 0 else "failed",
        "stderr": (paste.stderr or paste.stdout or "").strip()[:240],
        "goal_preview": text[:600],
    }
    _append_native_goal_log(row)
    return row

def _stage_goal_completion_rule(phase: str) -> str:
    rules = {
        "action_result_observation": (
            "Complete this stage only after writing WORKER_STEP_2_OBSERVE_EVALUATE and ending with "
            "AWAITING_RETRY_OR_ANSWER_REQUIRED."
        ),
        "retry_or_answer_required": (
            "Complete this stage only after writing WORKER_STEP_3_RETRY_OR_ANSWER_DECISION and ending with "
            "AWAITING_ANSWER_DRAFT_REQUIRED or AWAITING_RETRY_RESULT."
        ),
        "retry_result": (
            "Complete this stage only after updating WORKER_STEP_3_RETRY_OR_ANSWER_DECISION from the retry result and "
            "ending with AWAITING_ANSWER_DRAFT_REQUIRED."
        ),
        "answer_draft_required": (
            "Complete this stage only after writing WORKER_STEP_4_ANSWER_DRAFT and ending with "
            "AWAITING_FINAL_CLOSE_ALLOWED."
        ),
        "final_close_allowed": (
            "Complete this stage only after writing FINAL_ANSWER_AND_CLOSE with the required public sections."
        ),
    }
    return rules.get(phase, "Complete this stage only after writing the requested visible stage marker.")

def _stage_goal_text(event: dict, phase: str, text: str) -> str:
    if not NATIVE_GOAL_STAGE_GOALS:
        return text
    return (
        f"/goal {role} live job {event.get('mail_id')} stage {phase}: "
        f"{text} "
        f"Stage completion rule: {_stage_goal_completion_rule(phase)} "
        "This is a legacy/debug staged-goal proof; do not treat it as the default product path."
    )

def _send_native_goal_stage(event: dict, phase: str, text: str, *,
                            native_goal_command: bool = False,
                            wait_ready: bool = True) -> dict:
    if not NATIVE_GOAL_MODE:
        return {"sent": False, "status": "disabled", "native_goal_phase": phase}
    text = _stage_goal_text(event, phase, text)
    native_goal_command = native_goal_command or NATIVE_GOAL_STAGE_GOALS
    readiness = {"ready": True, "evidence": "not_waited"}
    if wait_ready:
        readiness = _wait_context_card_lane_ready(
            float(os.environ.get("OY_OP_NATIVE_GOAL_OBSERVATION_WAIT_SECONDS", "90"))
        )
    paste = paste_text_enter(tmux_target, text, reason=f"native_goal_stage:{phase}")
    row = {
        "timestamp": time.time(),
        "mode": "produce" if MODE == "produce" else "consume",
        "role": role,
        "delivery_id": event.get("delivery_id"),
        "mail_id": event.get("mail_id"),
        "tmux_target": tmux_target,
        "native_goal_command": native_goal_command,
        "native_goal_phase": phase,
        "lane_ready_before_send": bool(readiness.get("ready")),
        "lane_ready_evidence": readiness.get("evidence"),
        "sent": paste.returncode == 0,
        "status": "sent" if paste.returncode == 0 else "failed",
        "stderr": (paste.stderr or paste.stdout or "").strip()[:240],
        "message_preview": text[:800],
    }
    _append_native_goal_log(row)
    return row

def _send_native_goal_action_result(event: dict, receipt: dict | None, attempts: list[dict],
                                    status: str, result: subprocess.CompletedProcess | None,
                                    elapsed_ms: int) -> dict:
    if not NATIVE_GOAL_MODE:
        return {"sent": False, "status": "disabled"}
    text = _native_goal_action_result_text(event, receipt, attempts, status, result, elapsed_ms)
    return _send_native_goal_stage(
        event,
        "action_result_observation",
        text,
        wait_ready=True,
    )

def _native_goal_retry_or_answer_text(event: dict, receipt: dict | None, retry_rows: list[dict] | None = None) -> str:
    summary = _receipt_public_summary_for_event(event, receipt or {})
    mission = _mission_text(event)
    retry_rows = retry_rows or []
    retry_summary = (
        f"bounded retry attempts already run: {len(retry_rows)}"
        if retry_rows
        else "no bounded retry has been run for this stage"
    )
    if summary["quality"] in {"pass", "pass_with_limit"}:
        decision = (
            "Evidence is enough to draft an answer with limits. "
            "Required response now: WORKER_STEP_3_RETRY_OR_ANSWER_DECISION. "
            "State that retry is not required, explain why the support fits the user's question, "
            "and name the exact answer shape you will draft next."
        )
    else:
        decision = (
            "Evidence is weak. Required response now: WORKER_STEP_3_RETRY_OR_ANSWER_DECISION. "
            "State what is missing, whether bounded retry is required, and whether a later retry result is needed "
            "before any answer can be drafted."
        )
    return (
        f"RETRY_OR_ANSWER_REQUIRED for {role} live job {event.get('mail_id')}: "
        f"Mission: {_short(mission, 220)}. "
        f"Current evidence quality: {summary['quality']}; result: {summary['result']}; "
        f"detail: {_public_observation_detail(summary)}. {retry_summary}. "
        f"{decision} "
        "Do not write the final answer and do not continue into the next stage by yourself. "
        "End with exactly: AWAITING_ANSWER_DRAFT_REQUIRED if evidence is enough, "
        "or AWAITING_RETRY_RESULT if retry is still needed. "
        "If waiting for RETRY_RESULT, do not ask the user for input; "
        "the optional debug lens will provide RETRY_RESULT automatically. "
        "Do not expose local paths, internal commands, hidden chain-of-thought, or receipt ids."
    )

def _native_goal_retry_result_text(event: dict, retry_rows: list[dict], receipt: dict | None) -> str:
    summary = _receipt_public_summary_for_event(event, receipt or {})
    rows = [
        f"attempt {row.get('attempt')} quality={row.get('quality')} result={row.get('result')}"
        for row in retry_rows
    ]
    return (
        f"RETRY_RESULT for {role} live job {event.get('mail_id')}: "
        f"bounded retry summary: {_short('; '.join(rows), 360)}. "
        f"Best evidence quality now: {summary['quality']}; observed result: {summary['result']}; "
        f"detail: {_public_observation_detail(summary)}. "
        "Required response now: update WORKER_STEP_3_RETRY_OR_ANSWER_DECISION from this retry result. "
        "If enough, explain why retry succeeded and end with AWAITING_ANSWER_DRAFT_REQUIRED. "
        "If still weak, explain why typed_unavailable is now the correct bounded result and end with "
        "AWAITING_ANSWER_DRAFT_REQUIRED. Do not write the final answer yet and do not continue into the next stage by yourself."
    )

def _native_goal_answer_draft_text(event: dict, receipt: dict | None) -> str:
    summary = _receipt_public_summary_for_event(event, receipt or {})
    mission = _mission_text(event)
    if summary["quality"] in {"pass", "pass_with_limit"}:
        answer_mode = (
            "Draft the applied answer from the support fact. Include: one sentence answer, "
            "how the recovered memory aligns with the user question, practical placement, limits, and nonclaims."
        )
    else:
        answer_mode = (
            "Draft a typed_unavailable answer. Include: what was asked, what was searched, "
            "what evidence was missing, why you will not answer from memory, and what retry would need."
        )
    return (
        f"ANSWER_DRAFT_REQUIRED for {role} live job {event.get('mail_id')}: "
        f"Mission: {_short(mission, 220)}. "
        f"Evidence quality: {summary['quality']}; result: {summary['result']}; "
        f"detail: {_public_observation_detail(summary)}. "
        f"{answer_mode} "
        "Required response now: WORKER_STEP_4_ANSWER_DRAFT only. "
        "Do not write FINAL_ANSWER_AND_CLOSE yet and do not continue into the next stage by yourself. "
        "End with exactly: AWAITING_FINAL_CLOSE_ALLOWED."
    )

def _native_goal_final_close_text(event: dict, receipt: dict | None) -> str:
    summary = _receipt_public_summary_for_event(event, receipt or {})
    return (
        f"FINAL_CLOSE_ALLOWED for {role} live job {event.get('mail_id')}: "
        f"Final evidence quality: {summary['quality']}; result: {summary['result']}; "
        f"detail: {_public_observation_detail(summary)}. "
        "Now write FINAL_ANSWER_AND_CLOSE. This must not be only 'goal complete'. "
        "Include these public sections: final answer, action actually performed, observation used, "
        "question/evidence alignment, limits/nonclaims, and why closing is allowed now. "
        "If evidence is weak, the final answer must be typed_unavailable, not a guessed answer. "
        "Do not expose local paths, internal commands, hidden chain-of-thought, or receipt ids."
    )

def _send_native_goal_retry_or_answer(event: dict, receipt: dict | None,
                                      retry_rows: list[dict] | None = None) -> dict:
    return _send_native_goal_stage(
        event,
        "retry_or_answer_required",
        _native_goal_retry_or_answer_text(event, receipt, retry_rows),
        wait_ready=True,
    )

def _send_native_goal_retry_result(event: dict, retry_rows: list[dict], receipt: dict | None) -> dict:
    return _send_native_goal_stage(
        event,
        "retry_result",
        _native_goal_retry_result_text(event, retry_rows, receipt),
        wait_ready=True,
    )

def _send_native_goal_answer_draft(event: dict, receipt: dict | None) -> dict:
    return _send_native_goal_stage(
        event,
        "answer_draft_required",
        _native_goal_answer_draft_text(event, receipt),
        wait_ready=True,
    )

def _send_native_goal_final_close(event: dict, receipt: dict | None) -> dict:
    return _send_native_goal_stage(
        event,
        "final_close_allowed",
        _native_goal_final_close_text(event, receipt),
        wait_ready=True,
    )

def _send_native_goal_for_processed_event(event: dict, receipt: dict | None,
                                          attempts: list[dict], status: str) -> dict:
    if not NATIVE_GOAL_MODE:
        return {"sent": False, "status": "disabled"}
    text = _native_goal_text(event, receipt, attempts, status)
    before_session_id = _extract_session_id_from_tmux()
    paste = paste_text_enter(tmux_target, text, reason="native_goal_processed_event")
    row = {
        "timestamp": time.time(),
        "mode": "produce" if MODE == "produce" else "consume",
        "role": role,
        "delivery_id": event.get("delivery_id"),
        "mail_id": event.get("mail_id"),
        "tmux_target": tmux_target,
        "session_id_before_send": before_session_id,
        "native_goal_command": True,
        "sent": paste.returncode == 0,
        "status": "sent" if paste.returncode == 0 else "failed",
        "stderr": (paste.stderr or paste.stdout or "").strip()[:240],
        "goal_preview": text[:600],
    }
    _append_native_goal_log(row)
    return row


__all__ = [
    "_native_goal_text",
    "_native_goal_start_text",
    "_public_observation_detail",
    "_native_goal_action_result_text",
    "_send_native_goal_start",
    "_stage_goal_completion_rule",
    "_stage_goal_text",
    "_send_native_goal_stage",
    "_send_native_goal_action_result",
    "_native_goal_retry_or_answer_text",
    "_native_goal_retry_result_text",
    "_native_goal_answer_draft_text",
    "_native_goal_final_close_text",
    "_send_native_goal_retry_or_answer",
    "_send_native_goal_retry_result",
    "_send_native_goal_answer_draft",
    "_send_native_goal_final_close",
    "_send_native_goal_for_processed_event",
]
