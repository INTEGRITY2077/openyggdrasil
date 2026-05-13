from __future__ import annotations

from runtime.polling.ygg_poll_context import *  # noqa: F401,F403

def _read_jsonl(path: Path) -> list[dict]:
    return read_live_jsonl(path)

def _count_pending() -> tuple[int, int, int]:
    intents = _read_jsonl(MAILBOX / intent_name)
    receipts = _read_jsonl(MAILBOX / receipt_name)
    completed = {r.get("in_reply_to") for r in receipts if isinstance(r, dict)}
    pending = [m for m in intents if m.get("mail_id") not in completed]
    return len(intents), len(receipts), len(pending)

def _latest_receipt_summary() -> str:
    receipts = _read_jsonl(MAILBOX / receipt_name)
    if not receipts:
        return "최신 receipt 없음"
    last = receipts[-1]
    if MODE == "produce" and not ((os.environ.get("OY_LIVE_DELIVERY") == "1") and WORKER_OWNED_NATIVE_LOOP):
        nodes = last.get("nodes", []) if isinstance(last, dict) else []
        return (
            f"reply_to={last.get('in_reply_to', '?')} "
            f"produced={last.get('produced_count', 0)} nodes={len(nodes)}"
        )
    bundle = last.get("bundle", {}) if isinstance(last, dict) else {}
    nodes = bundle.get("nodes", []) if isinstance(bundle, dict) else []
    facts = bundle.get("support_facts", []) if isinstance(bundle, dict) else []
    return f"reply_to={last.get('in_reply_to', '?')} matches={len(nodes)} support_facts={len(facts)}"

def _check_ptc_intents(mailbox: Path) -> list[dict]:
    return check_ptc_intents(mailbox=mailbox, receipt_name=receipt_name)

def _route_ptc_to_hermes(mailbox: Path, intent: dict):
    decision = prepare_ptc_trigger(
        mailbox=mailbox,
        intent=intent,
        trigger_timeout=TRIGGER_TIMEOUT,
    )
    trigger_file = decision.trigger_file
    if not decision.created:
        _workflow(
            now="PTC trigger 중복 발행 방지",
            watching=f"{trigger_file} age={decision.trigger_age_seconds or 0:.0f}s",
            creating="새 trigger 없음",
            created="기존 trigger 유지",
            evidence=str(trigger_file),
            next_action="Hermes 처리 완료 또는 timeout까지 대기",
            status="pending",
        )
        return
    if decision.cleared_timeout_trigger:
        _workflow(
            now="timeout된 PTC trigger 정리",
            watching=f"{trigger_file} age={decision.trigger_age_seconds or 0:.0f}s",
            creating="trigger 삭제",
            created="timeout trigger 삭제 완료",
            evidence=str(trigger_file),
            next_action="새 trigger 생성",
            status="running",
        )

    msg = build_ptc_trigger_prompt(role=role, trigger_file=trigger_file, intent=intent)
    paste_text_enter(tmux_target, msg, reason="ptc_trigger_workflow")
    _workflow(
        now="PTC intent를 Hermes LLM 처리 표면으로 전달",
        watching=f"{mailbox / 'intents.jsonl'} mail_id={intent['mail_id']}",
        creating="ptc_trigger.json + Hermes WORKFLOW 알림",
        created=f"{trigger_file}",
        evidence=f"{trigger_file}",
        next_action="Ready Gate가 trigger 존재를 기준으로 중복 전달 방지",
        status="done",
    )

def _pending_summary() -> str:
    total, done, pending = _count_pending()
    return f"{intent_name}={total}, {receipt_name}={done}, pending={pending}"

def _delivered_live_ids() -> set[str]:
    return delivered_live_ids(MAILBOX)

def _check_live_events() -> list[dict]:
    return check_live_events(mailbox=MAILBOX, receipt_name=receipt_name, mode=MODE)

def _mark_live_delivered(event: dict, status: str = "sent_to_live_session") -> None:
    mark_live_delivered(mailbox=MAILBOX, event=event, status=status)

def _receipt_for_mail_id(mail_id: str) -> dict:
    return receipt_for_mail_id(mailbox=MAILBOX, receipt_name=receipt_name, mail_id=mail_id)

def _append_live_operator_log(row: dict) -> None:
    append_live_operator_log(mailbox=MAILBOX, row=row)

def _append_goal_log(row: dict) -> None:
    append_goal_log(mailbox=MAILBOX, row=row)

def _append_native_goal_log(row: dict) -> None:
    append_native_goal_log(mailbox=MAILBOX, row=row)


__all__ = [
    "_read_jsonl",
    "_count_pending",
    "_latest_receipt_summary",
    "_check_ptc_intents",
    "_route_ptc_to_hermes",
    "_pending_summary",
    "_delivered_live_ids",
    "_check_live_events",
    "_mark_live_delivered",
    "_receipt_for_mail_id",
    "_append_live_operator_log",
    "_append_goal_log",
    "_append_native_goal_log",
]
