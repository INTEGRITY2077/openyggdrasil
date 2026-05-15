from __future__ import annotations

import json
import os
import sys
import time

from runtime.delivery.tmux_lane_adapter import paste_text_enter
from runtime.polling.mailbox_summary import _append_goal_log, _append_live_operator_log, _mark_live_delivered
from runtime.polling.native_goal_flow import (
    _send_native_goal_action_result,
    _send_native_goal_answer_draft,
    _send_native_goal_final_close,
    _send_native_goal_for_processed_event,
    _send_native_goal_retry_or_answer,
    _send_native_goal_retry_result,
    _send_native_goal_start,
)
from runtime.polling.operator_runner import _run_consumer_bounded_retries, _run_operator_entrypoint_until_goal
from runtime.polling.receipt_quality import (
    _answer_material,
    _context_card_disabled_status,
    _first_fact_text,
    _goal_contract,
    _ptc_facts_paths,
    _ptc_worker_program,
    _ralph_contract,
    _ralph_todo_state,
    _receipt_outcome,
    _receipt_public_summary,
    _receipt_public_summary_for_event,
    _receipt_quality_for_event,
    _short,
)
from runtime.polling.worker_owned_loop import (
    _paste_context_prompt,
    _send_worker_owned_native_loop,
    _send_worker_owned_receipt_projection,
    _send_worker_owned_structured_close_surface,
    _wait_context_card_lane_ready,
)
from runtime.polling.ygg_poll_context import (
    ENABLE_LEGACY_RALPH_PROMPTS,
    MAILBOX,
    MODE,
    NATIVE_GOAL_ACTION_LOOP,
    NATIVE_GOAL_MODE,
    NATIVE_GOAL_MULTI_STEP,
    REPO_ROOT,
    VAULT,
    WORKER_OWNED_NATIVE_LOOP,
    _shell_quote,
    _workflow,
    role,
    tmux_target,
)

def _build_ralph_turn(event: dict, phase: str, *, attempt: int = 0,
                      receipt: dict | None = None, attempts: list[dict] | None = None) -> str:
    contract = _ralph_contract(event)
    outcome = _receipt_outcome(receipt)
    mission_id = event.get("mail_id")
    attempts = attempts or []
    attempt_count = len(attempts) or attempt
    common_tail = (
        "응답은 공개 작업 노트로만 쓰세요. 숨은 사고과정 원문, 내부 명령, 로컬 경로, receipt id를 쓰지 마세요. "
        "한 번에 끝난 척하지 말고 지금 턴의 판단과 다음 턴의 행동을 분명히 남기세요."
    )
    if phase == "orient":
        return (
            f"[{role} RALPH] job={mission_id} turn=orient\n"
            f"받은 일: {_short(contract['mission'], 360)}\n"
            f"내 역할: {contract['role']}.\n"
            f"이번 job의 목적: {contract['job']}.\n"
            f"먼저 스스로 물을 질문: {contract['self_question']}\n"
            f"지금 고를 다음 행동: {contract['action']}.\n"
            f"필요한 근거: {contract['evidence']}.\n"
            f"{common_tail}"
        )
    if phase == "act":
        return (
            f"[{role} RALPH] job={mission_id} turn=act attempt={attempt}\n"
            f"직전 판단: 목적을 이해했으니 이제 한 번 행동합니다.\n"
            f"이번 행동: {contract['action']}.\n"
            f"행동 뒤 확인할 것: {contract['evidence']}.\n"
            f"부족하면 어떻게 할지: 같은 답을 반복하지 않고 무엇이 부족한지 적고 다음 반복 여부를 판단합니다.\n"
            f"{common_tail}"
        )
    if phase == "inspect":
        return (
            f"[{role} RALPH] job={mission_id} turn=inspect attempt={attempt_count}\n"
            f"방금 행동 뒤 관찰: {outcome['observation']}\n"
            f"내가 다시 묻는 질문: 이 근거로 사용자의 질문에 더 정확히 답할 수 있는가?\n"
            f"현재 판정: {outcome['status']}.\n"
            f"다음 선택: {outcome['next_choice']} 다음 턴에서는 실제 답변 문장을 표면에 냅니다.\n"
            f"{common_tail}"
        )
    if phase == "answer":
        return (
            f"[{role} RALPH] job={mission_id} turn=draft_answer\n"
            f"이번 턴은 사용자에게 넘길 답변 초안을 실제로 표면에 내는 턴입니다.\n"
            f"초안 재료: {_answer_material(event, receipt)}\n"
            "출력 규칙: receipt id, 내부 명령, 로컬 경로를 쓰지 마세요. 단답으로 줄이지 마세요. "
            "구분 기준, 적용 예시, 둘이 겹칠 때의 분리 원칙, 근거 범위 제한을 포함해 답변 초안을 작성하세요."
        )
    if phase == "review":
        return (
            f"[{role} RALPH] job={mission_id} turn=review_answer\n"
            "방금 답변 초안을 스스로 검토하세요. "
            "검토 기준은 1) 사용자의 실제 질문에 직접 답했는가, 2) Hook과 Skill의 차이가 행동 기준으로 분리됐는가, "
            "3) 예시가 충분한가, 4) 근거 범위를 넘겨 말하지 않았는가입니다. "
            "부족한 점을 찾고, 다음 턴에서 무엇을 보강해야 하는지 공개 작업 노트로 남기세요. "
            "숨은 사고과정 원문, 내부 명령, 로컬 경로, receipt id는 쓰지 마세요."
        )
    if phase == "revise":
        return (
            f"[{role} RALPH] job={mission_id} turn=revise_answer\n"
            f"검토를 반영해 사용자에게 넘길 최종 답변을 다시 작성하세요. 답변 재료는 다음 범위입니다: {_answer_material(event, receipt)} "
            "최종 답변은 단답이 아니어야 합니다. 먼저 핵심 결론을 주고, 그 아래에 Hook을 쓰는 경우, Skill을 쓰는 경우, "
            "둘이 겹칠 때 나누는 방법, 이번 답의 근거 제한을 자연스럽게 정리하세요. "
            "내부 시스템명, 로컬 경로, receipt id는 쓰지 마세요."
        )
    if phase == "quality_gate":
        return (
            f"[{role} RALPH] job={mission_id} turn=quality_gate\n"
            "방금 보강한 답변을 최종으로 내도 되는지 공개 품질 게이트를 통과시키세요. "
            "평가 항목은 1) 사용자의 질문 의도를 다시 짚었는가, 2) 회수한 기억과 현재 질문의 정렬을 비교했는가, "
            "3) 바로 적용 가능한 판단 규칙이 있는가, 4) 겹치는 경우의 실제 분리 예시가 있는가, "
            "5) 근거 제한을 유지했는가입니다. "
            "각 항목을 pass/weak로 표시하고, weak가 있으면 다음 final_answer 턴에서 무엇을 보강할지 적으세요. "
            "내부 명령, 로컬 경로, receipt id는 쓰지 마세요."
        )
    if phase == "final":
        return (
            f"[{role} RALPH] job={mission_id} turn=final_answer\n"
            f"품질 게이트를 반영해 사용자에게 실제로 넘길 최종 답을 쓰세요. 답변 재료는 다음 범위입니다: {_answer_material(event, receipt)} "
            "답은 짧은 종료 문장이 아니라 적용 가능한 답이어야 합니다. "
            "구성은 1) 핵심 결론, 2) 판단 규칙, 3) 실제 적용 예시, 4) 겹치는 경우의 분리법, 5) 이번 답의 제한입니다. "
            "질문 의도와 회수한 기억이 어떻게 정렬되는지도 한 문단으로 짚으세요. "
            "내부 시스템명, 내부 명령, 로컬 경로, receipt id는 쓰지 마세요."
        )
    if phase == "close":
        return (
            f"[{role} RALPH] job={mission_id} turn=close\n"
            f"닫는 이유: {outcome['observation']}\n"
            f"최종 판단: {outcome['status']}.\n"
            f"사용자에게 넘길 답의 형태: 근거가 확인된 부분을 충분히 설명하되, 근거 범위를 넘기지 않습니다.\n"
            f"남기는 제한: 이 job은 현재 미션의 근거 회수/저장 판단이며 Full UX나 production-ready 증명이 아닙니다.\n"
            f"이제 이 job은 닫습니다."
        )
    return (
        f"[{role} RALPH] job={mission_id} turn={phase}\n"
        f"{common_tail}"
    )

def _write_ralph_turn(event: dict, phase: str, *, attempt: int = 0,
                      receipt: dict | None = None, attempts: list[dict] | None = None) -> dict:
    if not ENABLE_LEGACY_RALPH_PROMPTS:
        return {"written": False, "status": "legacy_ralph_prompt_disabled"}
    disabled = _context_card_disabled_status()
    if disabled:
        return disabled
    readiness = _wait_context_card_lane_ready()
    if not readiness.get("ready"):
        return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
    return _paste_context_prompt(_build_ralph_turn(event, phase, attempt=attempt, receipt=receipt, attempts=attempts))

def _build_goal_card(event: dict, phase: str, receipt: dict | None = None, log_row: dict | None = None,
                     attempts: list[dict] | None = None) -> str:
    contract = _goal_contract(event)
    attempts = attempts or []
    if MODE == "produce":
        chain = "Postman live_inbox -> MS1 produce -> vault node -> receipt"
    else:
        chain = "Postman live_inbox -> MF1 consume -> PTC retrieval -> support receipt"
    if phase == "start":
        return (
            f"[{role} GOAL] phase=start | mission_id={event.get('mail_id')} | "
            f"받은 미션={_short(contract['received'], 220)} | "
            f"목표={contract['objective']} | "
            f"내가 되묻는 기준={contract['role_question']} | "
            f"계획={contract['plan']} | "
            f"완료조건={contract['acceptance']} | "
            f"재시도규칙={contract['fallback']} | "
            f"비주장=공개 goal state이며 숨은 사고과정 원문이 아니다. [/{role} GOAL]"
        )
    summary = _receipt_public_summary(receipt or {})
    if summary["quality"] in {"pass", "pass_with_limit"}:
        goal_status = "closed_pass"
    elif receipt:
        goal_status = "closed_weak"
    else:
        goal_status = "blocked_no_receipt"
    attempt_text = ",".join(
        f"{a.get('attempt')}:{a.get('returncode')}/{'receipt' if a.get('receipt_id') else 'no_receipt'}"
        for a in attempts
    ) or "none"
    return (
        f"[{role} GOAL] phase=close | mission_id={event.get('mail_id')} | "
        f"목표상태={goal_status} | "
        f"실행체인={chain} | "
        f"시도={attempt_text} | "
        f"품질판정={summary['quality']} / {summary['result']} | "
        f"결과 요약={_short(summary['detail'], 260)} | "
        f"제한/비주장={summary['limitation']} | "
        f"다음 행동=Provider가 필요하면 이 receipt와 제한 조건만 반영한다. [/{role} GOAL]"
    )

def _build_ralph_todo_turn(event: dict, todo: dict, index: int, total: int) -> str:
    mission_id = event.get("mail_id")
    return (
        f"[{role} RALPH TODO] job={mission_id} todo={index}/{total} id={todo.get('todo_id')}\n"
        f"목적: {todo.get('purpose')}\n"
        f"입력: {_short(todo.get('input'), 260)}\n"
        f"관찰: {_short(todo.get('observed_result'), 360)}\n"
        f"품질판정: {todo.get('quality')}\n"
        f"다음 행동: {todo.get('next_action')}\n"
        "이 todo는 PTC receipt를 소비한 공개 작업 상태입니다. "
        "숨은 사고과정 원문, 내부 명령, 로컬 경로, receipt id는 쓰지 마세요. "
        "단답으로 닫지 말고 이 todo가 전체 목표에서 어떤 역할을 하는지와 다음 todo로 왜 넘어가는지 설명하세요."
    )

def _write_ralph_todo_turn(event: dict, todo: dict, index: int, total: int) -> dict:
    if not ENABLE_LEGACY_RALPH_PROMPTS:
        return {"written": False, "status": "legacy_ralph_prompt_disabled"}
    disabled = _context_card_disabled_status()
    if disabled:
        return disabled
    readiness = _wait_context_card_lane_ready()
    if not readiness.get("ready"):
        return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
    return _paste_context_prompt(_build_ralph_todo_turn(event, todo, index, total))

def _build_ptc_card(event: dict, phase: str, receipt: dict | None = None,
                    attempts: list[dict] | None = None) -> str:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    query = payload.get("query_text") if isinstance(payload, dict) else ""
    requested_code = payload.get("ptc_code") if isinstance(payload, dict) else ""
    ptc_requested = bool(payload.get("ptc")) if isinstance(payload, dict) else False
    if phase == "plan":
        return (
            f"[{role} PTC WORK] phase=plan | mission_id={event.get('mail_id')} | "
            f"query={_short(query, 220)} | "
            f"top_concept=tool_discovery_then_bounded_program_execution | "
            f"catalog_policy=do_not_load_full_tool_catalog_into_context | "
            f"worker_action=discover_needed_tools, write/select bounded program, execute read-only tools, evaluate result, retry if weak | "
            f"requested_ptc={ptc_requested} | "
            f"worker_program_probe={_short(requested_code or 'typed_unavailable_no_ptc_code', 300)} | "
            f"expected_tools=locate_region,select_topic_anchor,read_origin_claims,read_recent_claims,collect_claim_ids,read_source_paths,assemble_support_bundle | "
            f"acceptance=support_bundle_or_typed_unavailable_with_tool_trace | "
            f"nonclaim=not hidden chain-of-thought, not arbitrary write-enabled code execution. [/{role} PTC WORK]"
        )

    attempts = attempts or []
    program = _ptc_worker_program(receipt)
    discovery = program.get("tool_discovery") if isinstance(program.get("tool_discovery"), dict) else {}
    bounded = program.get("bounded_program") if isinstance(program.get("bounded_program"), dict) else {}
    calls = bounded.get("capability_calls") if isinstance(bounded.get("capability_calls"), list) else []
    call_ids = [
        str(call.get("capability_id"))
        for call in calls
        if isinstance(call, dict) and call.get("capability_id")
    ]
    facts, paths = _ptc_facts_paths(receipt)
    retry = program.get("retry_decision") if isinstance(program.get("retry_decision"), dict) else {}
    attempt_text = ",".join(
        f"{a.get('attempt')}:{a.get('returncode')}/{'receipt' if a.get('receipt_id') else 'no_receipt'}"
        for a in attempts
    ) or "none"
    return (
        f"[{role} PTC WORK] phase=derive | mission_id={event.get('mail_id')} | "
        f"tool_discovery_status={discovery.get('planner_execution_mode') or 'unknown'} | "
        f"selected_tools={','.join(discovery.get('selected_tool_ids') or call_ids) or 'none'} | "
        f"catalog_loaded_into_context={discovery.get('catalog_loaded_into_worker_context')} | "
        f"bounded_program={bounded.get('program_kind') or 'unknown'} dynamic_code_allowed={bounded.get('dynamic_code_execution_allowed')} | "
        f"program_execution={bounded.get('execution_status') or program.get('execution_status') or 'unknown'} | "
        f"tool_calls={len(calls)} | "
        f"candidate_counts=selected:{program.get('selected_candidate_count', 0)} rejected:{program.get('rejected_candidate_count', 0)} total:{program.get('candidate_count', 0)} | "
        f"coverage={program.get('coverage_state') or 'unknown'} retry={retry.get('status') or 'unknown'}:{retry.get('reason') or 'none'} | "
        f"support=facts:{len(facts)} paths:{len(paths)} first_fact={_first_fact_text(facts)} | "
        f"attempts={attempt_text} | "
        f"derivation=answer_must_use_support_facts_and_source_paths_not_stdout_alone | "
        f"nonclaim=not full UX, not production ready, not full raw transcript recall. [/{role} PTC WORK]"
    )

def _write_ptc_card(event: dict, phase: str, receipt: dict | None = None,
                    attempts: list[dict] | None = None) -> dict:
    if MODE != "consume":
        return {"written": False, "status": "not_consumer"}
    disabled = _context_card_disabled_status()
    if disabled:
        return disabled
    readiness = _wait_context_card_lane_ready()
    if not readiness.get("ready"):
        return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
    card = _build_ptc_card(event, phase, receipt=receipt, attempts=attempts)
    prompt = (
        f"{card} / 이 카드는 공개 PTC 작업 메모입니다. "
        "아래 섹션을 구분해서 짧지 않게 남기세요: 목표, 도구 탐색, 작성/선택한 프로그램, 실행 결과, 평가와 재시도 판정, 도출 답, 비주장. "
        "숨은 사고과정 원문, 내부 명령 원문, 로컬 경로 노출은 금지합니다. "
        "stdout만으로 답했다고 말하지 말고 support facts/source paths 또는 typed_unavailable로 마감하세요."
    )
    return _paste_context_prompt(prompt)

def _write_goal_card(event: dict, phase: str, receipt: dict | None = None, log_row: dict | None = None,
                     attempts: list[dict] | None = None) -> dict:
    disabled = _context_card_disabled_status()
    if disabled:
        return disabled
    readiness = _wait_context_card_lane_ready()
    if not readiness.get("ready"):
        return {"written": False, "status": "lane_not_ready", "evidence": readiness.get("evidence")}
    card = _build_goal_card(event, phase, receipt=receipt, log_row=log_row, attempts=attempts)
    prompt = (
        f"{card} / 지시: 위 카드는 이 미션의 공개 goal state입니다. "
        "단답으로 줄이지 마세요. 목표, 현재 이해, 실행 계획, 진행 상태, 판정, 다음 행동, 비주장을 구분해서 공개 작업 메모로 남기세요. "
        "숨은 사고과정 원문, 내부 명령 실행, 로컬 경로 노출은 금지합니다."
    )
    return _paste_context_prompt(prompt)

def _live_entry_mode() -> str:
    return "produce" if MODE == "produce" else "consume"

def _live_operator_cmd(entry_mode: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "runtime.operator_entrypoint",
        entry_mode,
        "--mailbox",
        str(MAILBOX),
        "--vault",
        str(VAULT),
    ]

def _worker_trace_debug_enabled() -> bool:
    return os.environ.get("OY_WORKER_TRACE_DEBUG_JSON", "0") == "1"

def _print_live_debug_event(payload: dict) -> None:
    if _worker_trace_debug_enabled():
        print(json.dumps(payload, ensure_ascii=False), flush=True)

def _dispatch_worker_owned_surface(event: dict, *, delivery_id: str, mail_id: str, entry_mode: str) -> None:
    dispatch = _send_worker_owned_native_loop(event)
    _append_live_operator_log({
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "status": "sent_to_worker_owned_native_loop" if dispatch.get("written") else "worker_owned_native_loop_blocked",
        "context_window_written": bool(dispatch.get("written")),
        "context_card_status": dispatch.get("status"),
        "tmux_target": tmux_target,
        "worker_owned_native_loop": True,
        "timestamp": time.time(),
    })
    _print_live_debug_event({
        "event": "live_delivery_worker_owned_native_loop_dispatched",
        "mode": entry_mode,
        "mail_id": mail_id,
        "delivery_id": delivery_id,
        "sent": bool(dispatch.get("written")),
        "status": dispatch.get("status"),
    })

def _start_native_goal_surface(event: dict, *, delivery_id: str, mail_id: str, entry_mode: str) -> tuple[dict, dict, dict]:
    native_goal_start = (
        _send_native_goal_start(event)
        if NATIVE_GOAL_ACTION_LOOP
        else {"sent": False, "status": "disabled"}
    )
    _append_goal_log({
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "phase": "native_goal_start",
        "goal_status": "active",
        "context_window_written": False,
        "context_card_status": "native_goal_mode",
        "native_goal_action_loop": NATIVE_GOAL_ACTION_LOOP,
        "native_goal_start_sent": bool(native_goal_start.get("sent")),
        "native_goal_start_status": native_goal_start.get("status"),
        "timestamp": time.time(),
    })
    return (
        {"written": False, "status": "native_goal_mode"},
        {"written": False, "status": "native_goal_mode"},
        native_goal_start,
    )

def _start_ralph_goal_surface(event: dict, *, delivery_id: str, mail_id: str, entry_mode: str) -> tuple[dict, dict, dict]:
    orient_turn = _write_ralph_turn(event, "orient")
    _append_goal_log({
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "phase": "ralph_orient",
        "goal_status": "active",
        "context_window_written": bool(orient_turn.get("written")),
        "context_card_status": orient_turn.get("status"),
        "timestamp": time.time(),
    })
    act_turn = _write_ralph_turn(event, "act", attempt=1)
    _append_goal_log({
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "phase": "ralph_act",
        "goal_status": "action_selected",
        "context_window_written": bool(act_turn.get("written")),
        "context_card_status": act_turn.get("status"),
        "timestamp": time.time(),
    })
    return orient_turn, act_turn, {"sent": False, "status": "not_native_goal_mode"}

def _start_goal_surface(event: dict, *, delivery_id: str, mail_id: str, entry_mode: str) -> tuple[dict, dict, dict]:
    if NATIVE_GOAL_MODE:
        return _start_native_goal_surface(
            event,
            delivery_id=delivery_id,
            mail_id=mail_id,
            entry_mode=entry_mode,
        )
    return _start_ralph_goal_surface(event, delivery_id=delivery_id, mail_id=mail_id, entry_mode=entry_mode)

def _run_operator_for_live_event(
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
) -> tuple[object, int, dict, list[dict], str, dict]:
    result, elapsed_ms, receipt, attempts = _run_operator_entrypoint_until_goal(
        _live_operator_cmd(entry_mode),
        mail_id,
    )
    status = "goal_closed" if result and result.returncode == 0 and receipt else "goal_blocked"
    log_row = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "status": status,
        "returncode": result.returncode if result else None,
        "elapsed_ms": elapsed_ms,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "receipt_id": receipt.get("receipt_id"),
        "receipt_status": receipt.get("status"),
        "stdout_preview": ((result.stdout if result else "") or "").strip()[:1000],
        "stderr_preview": ((result.stderr if result else "") or "").strip()[:1000],
        "tmux_target": tmux_target,
        "timestamp": time.time(),
    }
    return result, elapsed_ms, receipt, attempts, status, log_row

def _handle_worker_owned_result(
    event: dict,
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
    receipt: dict,
    status: str,
    elapsed_ms: int,
    attempts: list[dict],
    log_row: dict,
) -> bool:
    if not WORKER_OWNED_NATIVE_LOOP:
        return False
    structured_surface = _send_worker_owned_structured_close_surface(
        event, receipt, status, elapsed_ms, attempts
    )
    receipt_projection = _send_worker_owned_receipt_projection(event, receipt, status, elapsed_ms, attempts)
    summary = _receipt_public_summary_for_event(event, receipt)
    log_row.update({
        "goal_phase": "worker_owned_structured_close_surface",
        "goal_status": "closed" if receipt else "blocked",
        "context_window_written": bool(structured_surface.get("written")),
        "context_card_status": structured_surface.get("status"),
        "worker_owned_structured_close_surface_sent": bool(structured_surface.get("written")),
        "worker_owned_receipt_projection_sent": bool(receipt_projection.get("written")),
        "final_support_quality": summary.get("quality"),
        "final_support_result": summary.get("result"),
    })
    _append_live_operator_log(log_row)
    _print_live_debug_event({
        "event": "live_delivery_worker_owned_processed",
        "mode": entry_mode,
        "mail_id": mail_id,
        "delivery_id": delivery_id,
        "status": status,
        "receipt_present": bool(receipt),
        "elapsed_ms": elapsed_ms,
        "attempt_count": len(attempts),
        "structured_surface_sent": bool(structured_surface.get("written")),
        "structured_surface_status": structured_surface.get("status"),
        "receipt_projection_sent": bool(receipt_projection.get("written")),
        "receipt_projection_status": receipt_projection.get("status"),
        "final_support_quality": summary.get("quality"),
    })
    return True

def _run_native_goal_stages(
    event: dict,
    *,
    receipt: dict,
    attempts: list[dict],
    status: str,
    result: object,
    elapsed_ms: int,
) -> tuple[str, dict, list[dict], dict, list[dict]]:
    final_receipt = receipt
    retry_rows: list[dict] = []
    native_goal_stages: list[dict] = []
    if NATIVE_GOAL_ACTION_LOOP:
        native_goal = _send_native_goal_action_result(event, receipt, attempts, status, result, elapsed_ms)
        native_goal_stages.append(native_goal)
        goal_phase = "native_goal_action_result"
        if NATIVE_GOAL_MULTI_STEP:
            native_goal_stages.append(_send_native_goal_retry_or_answer(event, receipt))
            if _receipt_quality_for_event(event, receipt) not in {"pass", "pass_with_limit"}:
                final_receipt, retry_rows = _run_consumer_bounded_retries(event, receipt)
                if retry_rows:
                    native_goal_stages.append(_send_native_goal_retry_result(event, retry_rows, final_receipt))
                    native_goal_stages.append(_send_native_goal_retry_or_answer(event, final_receipt, retry_rows))
            native_goal_stages.append(_send_native_goal_answer_draft(event, final_receipt))
            native_goal = _send_native_goal_final_close(event, final_receipt)
            native_goal_stages.append(native_goal)
            goal_phase = "native_goal_multi_step_final_close"
        return goal_phase, native_goal, native_goal_stages, final_receipt, retry_rows
    native_goal = _send_native_goal_for_processed_event(event, receipt, attempts, status)
    native_goal_stages.append(native_goal)
    return "native_goal_dispatch", native_goal, native_goal_stages, final_receipt, retry_rows

def _native_stage_rows(native_goal_stages: list[dict]) -> list[dict]:
    return [
        {
            "phase": stage.get("native_goal_phase"),
            "sent": stage.get("sent"),
            "status": stage.get("status"),
            "lane_ready_before_send": stage.get("lane_ready_before_send"),
        }
        for stage in native_goal_stages
    ]

def _handle_native_goal_result(
    event: dict,
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
    receipt: dict,
    attempts: list[dict],
    status: str,
    result: object,
    elapsed_ms: int,
    native_goal_start: dict,
    log_row: dict,
) -> bool:
    if not NATIVE_GOAL_MODE:
        return False
    todos = _ralph_todo_state(event, receipt, attempts)
    goal_phase, native_goal, stages, final_receipt, retry_rows = _run_native_goal_stages(
        event,
        receipt=receipt,
        attempts=attempts,
        status=status,
        result=result,
        elapsed_ms=elapsed_ms,
    )
    final_summary = _receipt_public_summary_for_event(event, final_receipt or {})
    log_row.update({
        "goal_phase": goal_phase,
        "goal_status": "closed" if receipt else "blocked",
        "native_goal_mode": True,
        "native_goal_action_loop": NATIVE_GOAL_ACTION_LOOP,
        "native_goal_multi_step": NATIVE_GOAL_MULTI_STEP,
        "native_goal_start_sent": bool(native_goal_start.get("sent")),
        "native_goal_start_status": native_goal_start.get("status"),
        "native_goal_sent": bool(native_goal.get("sent")),
        "native_goal_status": native_goal.get("status"),
        "native_goal_phase": native_goal.get("native_goal_phase"),
        "native_goal_stages": _native_stage_rows(stages),
        "native_goal_session_id_before_send": native_goal.get("session_id_before_send"),
        "context_window_written": False,
        "context_card_status": "native_goal_mode",
        "context_ralph_todo_count": len(todos),
        "context_ralph_todo_ids": [todo.get("todo_id") for todo in todos],
        "bounded_retry_rows": retry_rows,
        "bounded_retry_count": len(retry_rows),
        "final_support_quality": final_summary["quality"],
        "final_support_result": final_summary["result"],
    })
    _append_goal_log({
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "phase": goal_phase,
        "goal_status": log_row["goal_status"],
        "attempts": attempts,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_status": receipt.get("status"),
        "todo_count": len(todos),
        "todo_ids": [todo.get("todo_id") for todo in todos],
        "context_window_written": False,
        "context_card_status": "native_goal_mode",
        "native_goal_action_loop": NATIVE_GOAL_ACTION_LOOP,
        "native_goal_multi_step": NATIVE_GOAL_MULTI_STEP,
        "native_goal_start_sent": log_row["native_goal_start_sent"],
        "native_goal_start_status": log_row["native_goal_start_status"],
        "native_goal_sent": log_row["native_goal_sent"],
        "native_goal_status": log_row["native_goal_status"],
        "native_goal_phase": log_row["native_goal_phase"],
        "native_goal_stage_phases": [stage.get("native_goal_phase") for stage in stages],
        "bounded_retry_count": len(retry_rows),
        "final_support_quality": final_summary["quality"],
        "final_support_result": final_summary["result"],
        "timestamp": time.time(),
    })
    _append_live_operator_log(log_row)
    _print_native_goal_processed(entry_mode, mail_id, delivery_id, status, receipt, elapsed_ms, attempts, log_row, stages)
    return True

def _print_native_goal_processed(
    entry_mode: str,
    mail_id: str,
    delivery_id: str,
    status: str,
    receipt: dict,
    elapsed_ms: int,
    attempts: list[dict],
    log_row: dict,
    stages: list[dict],
) -> None:
    print(
        json.dumps(
            {
                "event": "live_delivery_native_goal_processed",
                "mode": entry_mode,
                "mail_id": mail_id,
                "delivery_id": delivery_id,
                "status": status,
                "receipt_id": receipt.get("receipt_id"),
                "elapsed_ms": elapsed_ms,
                "attempt_count": len(attempts),
                "goal_status": log_row["goal_status"],
                "goal_phase": log_row["goal_phase"],
                "native_goal_action_loop": NATIVE_GOAL_ACTION_LOOP,
                "native_goal_multi_step": NATIVE_GOAL_MULTI_STEP,
                "native_goal_start_sent": log_row["native_goal_start_sent"],
                "native_goal_sent": log_row["native_goal_sent"],
                "native_goal_status": log_row["native_goal_status"],
                "native_goal_stage_phases": [stage.get("native_goal_phase") for stage in stages],
                "bounded_retry_count": log_row["bounded_retry_count"],
                "final_support_quality": log_row["final_support_quality"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

def _append_ralph_goal_log(
    *,
    delivery_id: str,
    mail_id: str,
    entry_mode: str,
    phase: str,
    goal_status: str,
    receipt: dict,
    turn: dict | None = None,
    extra: dict | None = None,
) -> None:
    row = {
        "delivery_id": delivery_id,
        "mail_id": mail_id,
        "mode": entry_mode,
        "phase": phase,
        "goal_status": goal_status,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_status": receipt.get("status"),
        "context_window_written": bool(turn.get("written")) if turn else False,
        "context_card_status": turn.get("status") if turn else "log_only",
        "timestamp": time.time(),
    }
    if extra:
        row.update(extra)
    _append_goal_log(row)

def _write_ralph_todo_surfaces(
    event: dict,
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
    receipt: dict,
    attempts: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    inspect_turn = _write_ralph_turn(event, "inspect", attempt=len(attempts), receipt=receipt, attempts=attempts)
    _append_ralph_goal_log(
        delivery_id=delivery_id,
        mail_id=mail_id,
        entry_mode=entry_mode,
        phase="ralph_inspect",
        goal_status="result_inspected" if receipt else "result_missing",
        receipt=receipt,
        turn=inspect_turn,
    )
    todos = _ralph_todo_state(event, receipt, attempts)
    _append_ralph_goal_log(
        delivery_id=delivery_id,
        mail_id=mail_id,
        entry_mode=entry_mode,
        phase="ralph_todo_state_built",
        goal_status="ptc_todo_state_ready" if todos else "ptc_todo_state_empty",
        receipt=receipt,
        extra={"todo_count": len(todos), "todo_ids": [todo.get("todo_id") for todo in todos]},
    )
    todo_turns = []
    for index, todo in enumerate(todos, start=1):
        base = {"todo_id": todo.get("todo_id"), "todo_index": index, "todo_total": len(todos), "todo_quality": todo.get("quality")}
        _append_ralph_goal_log(
            delivery_id=delivery_id,
            mail_id=mail_id,
            entry_mode=entry_mode,
            phase="ralph_todo_start",
            goal_status="todo_visible_write_start",
            receipt=receipt,
            extra={**base, "context_card_status": "pending"},
        )
        todo_turn = _write_ralph_todo_turn(event, todo, index, len(todos))
        todo_turns.append(todo_turn)
        _append_ralph_goal_log(
            delivery_id=delivery_id,
            mail_id=mail_id,
            entry_mode=entry_mode,
            phase="ralph_todo",
            goal_status="todo_visible_written" if todo_turn.get("written") else "todo_visible_blocked",
            receipt=receipt,
            turn=todo_turn,
            extra=base,
        )
    return inspect_turn, todos, todo_turns

def _write_ralph_answer_surfaces(
    event: dict,
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
    receipt: dict,
    attempts: list[dict],
) -> dict[str, dict]:
    phases = [
        ("answer", "ralph_draft_answer", "answer_drafted", "answer_unavailable"),
        ("review", "ralph_review_answer", "answer_reviewed", "answer_review_unavailable"),
        ("revise", "ralph_revise_answer", "answer_revised", "answer_revise_unavailable"),
        ("quality_gate", "ralph_quality_gate", "answer_quality_gated", "answer_quality_gate_unavailable"),
        ("final", "ralph_final_answer", "answer_finalized", "answer_final_unavailable"),
    ]
    turns: dict[str, dict] = {}
    for turn_name, phase, ok_status, missing_status in phases:
        turn = _write_ralph_turn(event, turn_name, receipt=receipt, attempts=attempts)
        turns[turn_name] = turn
        _append_ralph_goal_log(
            delivery_id=delivery_id,
            mail_id=mail_id,
            entry_mode=entry_mode,
            phase=phase,
            goal_status=ok_status if receipt else missing_status,
            receipt=receipt,
            turn=turn,
        )
    return turns

def _populate_ralph_log_row(
    log_row: dict,
    *,
    receipt: dict,
    orient_turn: dict,
    act_turn: dict,
    inspect_turn: dict,
    todos: list[dict],
    todo_turns: list[dict],
    answer_turns: dict[str, dict],
) -> None:
    final_turn = answer_turns["final"]
    log_row.update({
        "goal_phase": "close",
        "goal_status": "closed" if receipt else "blocked",
        "context_goal_start_written": bool(orient_turn.get("written")),
        "context_goal_start_status": orient_turn.get("status"),
        "context_ralph_act_written": bool(act_turn.get("written")),
        "context_ralph_act_status": act_turn.get("status"),
        "context_ralph_inspect_written": bool(inspect_turn.get("written")),
        "context_ralph_inspect_status": inspect_turn.get("status"),
        "context_ralph_todo_count": len(todos),
        "context_ralph_todo_ids": [todo.get("todo_id") for todo in todos],
        "context_ralph_todo_written_count": sum(1 for turn in todo_turns if turn.get("written")),
        "context_ralph_todo_statuses": [turn.get("status") for turn in todo_turns],
        "context_goal_close_written": False,
        "context_goal_close_status": "log_only_after_final_answer",
        "last_visible_phase": "ralph_final_answer",
        "close_visibility": "log_only",
        "context_card_status": final_turn.get("status"),
    })
    for key, prefix in [
        ("answer", "context_ralph_answer"),
        ("review", "context_ralph_review"),
        ("revise", "context_ralph_revise"),
        ("quality_gate", "context_ralph_quality_gate"),
        ("final", "context_ralph_final"),
    ]:
        log_row[f"{prefix}_written"] = bool(answer_turns[key].get("written"))
        log_row[f"{prefix}_status"] = answer_turns[key].get("status")
    log_row["context_window_written"] = bool(
        orient_turn.get("written")
        or act_turn.get("written")
        or inspect_turn.get("written")
        or any(turn.get("written") for turn in todo_turns)
        or any(turn.get("written") for turn in answer_turns.values())
    )

def _handle_ralph_result(
    event: dict,
    *,
    entry_mode: str,
    delivery_id: str,
    mail_id: str,
    receipt: dict,
    attempts: list[dict],
    status: str,
    elapsed_ms: int,
    orient_turn: dict,
    act_turn: dict,
    log_row: dict,
) -> None:
    inspect_turn, todos, todo_turns = _write_ralph_todo_surfaces(
        event,
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
        receipt=receipt,
        attempts=attempts,
    )
    answer_turns = _write_ralph_answer_surfaces(
        event,
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
        receipt=receipt,
        attempts=attempts,
    )
    _populate_ralph_log_row(
        log_row,
        receipt=receipt,
        orient_turn=orient_turn,
        act_turn=act_turn,
        inspect_turn=inspect_turn,
        todos=todos,
        todo_turns=todo_turns,
        answer_turns=answer_turns,
    )
    native_goal = _send_native_goal_for_processed_event(event, receipt, attempts, status)
    log_row["native_goal_mode"] = NATIVE_GOAL_MODE
    log_row["native_goal_sent"] = bool(native_goal.get("sent"))
    log_row["native_goal_status"] = native_goal.get("status")
    log_row["native_goal_session_id_before_send"] = native_goal.get("session_id_before_send")
    _append_ralph_goal_log(
        delivery_id=delivery_id,
        mail_id=mail_id,
        entry_mode=entry_mode,
        phase="ralph_close",
        goal_status=log_row["goal_status"],
        receipt=receipt,
        extra={
            "attempts": attempts,
            "last_visible_phase": "ralph_final_answer",
            "close_visibility": "log_only",
            "native_goal_mode": NATIVE_GOAL_MODE,
            "native_goal_sent": bool(native_goal.get("sent")),
            "native_goal_status": native_goal.get("status"),
        },
    )
    _append_live_operator_log(log_row)
    _print_quiet_processed(entry_mode, mail_id, delivery_id, status, receipt, elapsed_ms, attempts, log_row)

def _print_quiet_processed(
    entry_mode: str,
    mail_id: str,
    delivery_id: str,
    status: str,
    receipt: dict,
    elapsed_ms: int,
    attempts: list[dict],
    log_row: dict,
) -> None:
    print(
        json.dumps(
            {
                "event": "live_delivery_quiet_processed",
                "mode": entry_mode,
                "mail_id": mail_id,
                "delivery_id": delivery_id,
                "status": status,
                "receipt_id": receipt.get("receipt_id"),
                "elapsed_ms": elapsed_ms,
                "attempt_count": len(attempts),
                "goal_status": log_row["goal_status"],
                "context_window_written": log_row["context_window_written"],
                "context_card_status": log_row["context_card_status"],
                "native_goal_mode": log_row["native_goal_mode"],
                "native_goal_sent": log_row["native_goal_sent"],
                "native_goal_status": log_row["native_goal_status"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

def _run_live_event_quietly(event: dict) -> None:
    """Process live delivery without making Postman the semantic owner."""
    mail_id = str(event.get("mail_id") or "?")
    delivery_id = str(event.get("delivery_id") or "?")
    entry_mode = _live_entry_mode()
    if WORKER_OWNED_NATIVE_LOOP:
        _dispatch_worker_owned_surface(
            event,
            delivery_id=delivery_id,
            mail_id=mail_id,
            entry_mode=entry_mode,
        )
    orient_turn, act_turn, native_goal_start = _start_goal_surface(
        event,
        delivery_id=delivery_id,
        mail_id=mail_id,
        entry_mode=entry_mode,
    )
    result, elapsed_ms, receipt, attempts, status, log_row = _run_operator_for_live_event(
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
    )
    _mark_live_delivered(event, status=status)
    if _handle_worker_owned_result(
        event,
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
        receipt=receipt,
        status=status,
        elapsed_ms=elapsed_ms,
        attempts=attempts,
        log_row=log_row,
    ):
        return
    if _handle_native_goal_result(
        event,
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
        receipt=receipt,
        attempts=attempts,
        status=status,
        result=result,
        elapsed_ms=elapsed_ms,
        native_goal_start=native_goal_start,
        log_row=log_row,
    ):
        return
    _handle_ralph_result(
        event,
        entry_mode=entry_mode,
        delivery_id=delivery_id,
        mail_id=mail_id,
        receipt=receipt,
        attempts=attempts,
        status=status,
        elapsed_ms=elapsed_ms,
        orient_turn=orient_turn,
        act_turn=act_turn,
        log_row=log_row,
    )

def _route_live_event_to_hermes(event: dict) -> None:
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    snapshot = payload.get("context_snapshot", "") if isinstance(payload, dict) else ""
    query_text = payload.get("query_text", "") if isinstance(payload, dict) else ""
    mail_id = event.get("mail_id", "?")
    delivery_id = event.get("delivery_id", "?")
    live_inbox = MAILBOX / "live_inbox.jsonl"
    op_name = role
    entry_mode = "produce" if MODE == "produce" else "consume"
    workflow_title = "Postman live delivery 수신분 저장 처리" if MODE == "produce" else "Postman live delivery 수신분 회상 처리"
    artifact = "Vault node + receipts.jsonl + delivery_receipts.jsonl" if MODE == "produce" else "query_receipts.jsonl + delivery_receipts.jsonl + support_facts"
    if MODE == "produce":
        summary = snapshot[:500] or str(payload.get("decision") or payload.get("source_ref") or "")[:500]
    else:
        summary = query_text[:500]
    repo_root = _shell_quote(REPO_ROOT)
    cmd = (
        f"cd {repo_root} && "
        f"PYTHONPATH={repo_root} "
        f"python3 -m runtime.operator_entrypoint {entry_mode} "
        f"--mailbox {MAILBOX} --vault {VAULT}"
    )
    msg = (
        f"[{op_name} WORKFLOW]\n"
        f"지금 할 일: {workflow_title}\n"
        f"보고 있는 것: {live_inbox} delivery_id={delivery_id} mail_id={mail_id}\n"
        f"생성할 것: {artifact}\n"
        f"방금 만든 것: 처리 전\n"
        f"근거: {live_inbox}\n"
        f"다음 행동: 아래 명령을 Hermes 도구로 실행하고 mail_id={mail_id} receipt/Vault를 검증한 뒤 [{op_name} WORKFLOW] done을 보고하십시오.\n"
        f"상태: running\n\n"
        f"수신 payload 요약: {summary}\n\n"
        f"실행 명령:\n{cmd}"
    )
    paste = paste_text_enter(tmux_target, msg, reason="live_delivery_workflow")
    if paste.returncode != 0:
        _workflow(
            now="Postman live delivery를 OP Hermes 세션에 전달 실패",
            watching=f"{live_inbox} delivery_id={delivery_id} mail_id={mail_id}",
            creating="실패 상태 카드",
            created=f"tmux_returncode={paste.returncode}",
            evidence=(paste.stderr or paste.stdout or "(empty)")[:240].replace("\n", " | "),
            next_action="tmux target/입력 모드 확인 후 재전달",
            status="blocked",
        )
        return
    _mark_live_delivered(event)
    _workflow(
        now="Postman live delivery를 OP Hermes 세션에 전달",
        watching=f"{live_inbox} delivery_id={delivery_id} mail_id={mail_id}",
        creating="OP live session WORKFLOW 입력",
        created=f"tmux_target={tmux_target} mail_id={mail_id}",
        evidence=f"{MAILBOX / 'live_delivered.jsonl'}",
        next_action="OP live session이 operator_entrypoint를 실행하고 receipt/Vault를 보고",
        status="done",
    )


__all__ = [
    "_build_ralph_turn",
    "_write_ralph_turn",
    "_build_goal_card",
    "_build_ralph_todo_turn",
    "_write_ralph_todo_turn",
    "_build_ptc_card",
    "_write_ptc_card",
    "_write_goal_card",
    "_run_live_event_quietly",
    "_route_live_event_to_hermes",
]
