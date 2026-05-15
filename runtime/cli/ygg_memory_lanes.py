from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from runtime.cli.ygg_config import (
    DEFAULT_MEMORY_FINDER_COMMAND,
    DEFAULT_MEMORY_SAVER_COMMAND,
    PRIVATE_DEV,
    PROVIDER_PAIR_SESSION,
    REGISTRY_DIR,
    REPO,
    SCRIPTS_DIR,
    SESSIONS_DIR,
    _default_vault,
    _env_text,
    _format_launcher_command,
    _provider_command,
    _provider_id,
    _provider_profile,
    _shell_quote,
    _workflow,
)
from runtime.cli.ygg_cpr import _append_jsonl, _jsonl_rows, _provider_cpr_status_summary_for_op, cmd_cpr
from runtime.cli.ygg_registry import (
    _canonical_alias_for_op,
    _ensure_memory_lane_tmux_name,
    _ensure_tmux_hygiene,
    _existing_pair_for_provider,
    _load_registry,
    _next_pair,
    _op_command_for,
    _op_label,
    _op_number,
    _provider_lane_record_path,
    _provider_session_id_for,
    _read_provider_lane_record,
    _resolve_op,
    _save_registry,
    _write_provider_lane_record,
    cmd_provider_lane_doctor,
)
from runtime.cli.ygg_tmux import _tmux_attach_or_switch, _tmux_session_exists
from runtime.delivery.postman_native_activation import activate_native_lane

def _memory_lane_command(op: str, record: dict, mailbox: Path, vault: str) -> str | None:
    is_saver = record.get("type") == "producer"
    role = "memory_saver" if is_saver else "memory_finder"
    provider_id = str(record.get("provider") or _provider_id())
    provider_profile = _provider_profile(provider_id)
    env_names = (
        ("OY_MS_COMMAND", "OY_MEMORY_SAVER_COMMAND")
        if is_saver
        else ("OY_MF_COMMAND", "OY_MEMORY_FINDER_COMMAND")
    )
    template = next((_env_text(name) for name in env_names if _env_text(name)), "")
    if template:
        return _format_launcher_command(
            template,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=_provider_session_id_for(PROVIDER_PAIR_SESSION),
            op=op,
            role=role,
            mailbox=str(mailbox),
            vault=vault,
        )
    if provider_id == "hermes":
        return DEFAULT_MEMORY_SAVER_COMMAND if is_saver else DEFAULT_MEMORY_FINDER_COMMAND
    return None


def _live_delivery_recipient_for(op: str) -> str:
    if str(op).upper().startswith("OP") and str(op)[2:].isdigit():
        return _canonical_alias_for_op(op)
    return str(op).upper()

def _run_operator(mode: str, mailbox: Path, vault: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "runtime.operator_entrypoint", mode,
         "--mailbox", str(mailbox), "--vault", str(vault)],
        capture_output=True, text=True, timeout=120,
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

def _tail_jsonl(path: Path) -> dict | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"raw_unparsed": lines[-1][:160]}

def _latest_status_summary(op: str, r: dict, receipt_file: Path, is_producer: bool) -> tuple[str, str]:
    last = _tail_jsonl(receipt_file)
    if not last:
        return "최신 receipt 없음", str(receipt_file)
    if is_producer:
        nodes = last.get("nodes", []) if isinstance(last, dict) else []
        produced = last.get("produced_count", 0) if isinstance(last, dict) else 0
        return (
            f"reply_to={last.get('in_reply_to', '?')} produced={produced} nodes={len(nodes)}",
            f"{receipt_file}"
        )
    bundle = last.get("bundle", {}) if isinstance(last, dict) else {}
    nodes = bundle.get("nodes", []) if isinstance(bundle, dict) else []
    return (
        f"reply_to={last.get('in_reply_to', '?')} matches={len(nodes)}",
        f"{receipt_file}"
    )

def _looks_like_memory_ticket_text(message: str) -> bool:
    """Return True when a text blob is a MemoryTicket-shaped contract pasted into classic tell."""
    lowered = message.lower()
    requiredish = [
        "intent_field:",
        "decomposition_guard:",
        "min_split_unit:",
        "why_not_atomic:",
        "topic_hint:",
        "category_community_hint:",
    ]
    return sum(1 for marker in requiredish if marker in lowered) >= 3

def _parse_range_value(value: str) -> dict:
    text = value.strip()
    if not text:
        return {}
    if text.startswith("{"):
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {}
    match = re.fullmatch(r"\s*([0-9]+)\s*(?:\.\.|-|:)\s*([0-9]+)\s*", text)
    if match:
        return {"start": int(match.group(1)), "end": int(match.group(2))}
    match = re.fullmatch(r"\s*([^.\-:]+)\s*(?:\.\.|-|:)\s*([^.\-:]+)\s*", text)
    if match:
        return {"start": match.group(1).strip(), "end": match.group(2).strip()}
    return {}

def _parse_memory_ticket_payload(message: str) -> dict:
    """Parse newline key-value MemoryTicket text into the top-level delivery payload."""
    payload = {"schema_version": "memory_ticket.v1"}
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in {"message_index_range", "message_id_range", "source_line_range"}:
            parsed_range = _parse_range_value(value)
            if parsed_range:
                payload[key] = parsed_range
            continue
        if key == "resolver_options":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                payload[key] = parsed
            continue
        if key == "evidence":
            payload[key] = [part.strip() for part in value.split(";") if part.strip()]
            continue
        payload[key] = value
    return payload

def _has_classic_save_marker(message: str) -> bool:
    markers = ["결정:", "확정:", "채택:", "폐기:", "규칙:", "정책:", "앞으로", "반드시", "확인:", "원인:", "구조:", "설계:", "아키텍처:", "패턴:"]
    return any(marker in message for marker in markers)

def _live_debug_monitor_lines(mode: str, mailbox: Path) -> list[str]:
    target_cmd = f"ygg_poll.py {mode} {mailbox}"
    proc = subprocess.run(["pgrep", "-af", target_cmd], capture_output=True, text=True)
    return [line for line in proc.stdout.splitlines() if "pgrep" not in line and "ygg_poll.py" in line]

def _postman_activate_native_lane(
    op: str,
    record: dict,
    delivery: dict,
    *,
    message_type: str,
    payload: dict,
) -> dict:
    return activate_native_lane(
        op=_live_delivery_recipient_for(op),
        label=_op_label(op),
        role_type=str(record.get("type") or ""),
        session=_ensure_memory_lane_tmux_name(op),
        delivery=delivery,
        message_type=message_type,
        payload=payload,
        registry_dir=REGISTRY_DIR,
        sessions_dir=SESSIONS_DIR,
    )

def _ensure_live_debug_monitor(op: str, record: dict) -> dict:
    """Start the optional MS/MF debug lens if the tmux lane exists."""
    mode = "produce" if record.get("type") == "producer" else "consume"
    session = _ensure_memory_lane_tmux_name(op)
    window = "live-postman"
    mailbox = SESSIONS_DIR / op
    vault = Path(record["vault"])
    running = _live_debug_monitor_lines(mode, mailbox)
    if running:
        return {
            "status": "running",
            "session": session,
            "window": window,
            "pid": running[0].split()[0],
            "vault": str(vault),
        }
    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode != 0:
        return {
            "status": "blocked",
            "reason_code": "memory_lane_tmux_session_missing",
            "session": session,
            "window": window,
            "vault": str(vault),
        }
    existing_windows = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if window in existing_windows.stdout.splitlines():
        subprocess.run(["tmux", "kill-window", "-t", f"{session}:{window}"], capture_output=True)
    private_dev = _shell_quote(PRIVATE_DEV)
    repo = _shell_quote(REPO)
    poll_script = _shell_quote(SCRIPTS_DIR / "ygg_poll.py")
    cmd = (
        f"cd {private_dev} && "
        f"OY_LIVE_DELIVERY=1 OY_OP_WORKER_OWNED_NATIVE_LOOP=${{OY_OP_WORKER_OWNED_NATIVE_LOOP:-1}} "
        f"OY_OP_NATIVE_GOAL=${{OY_OP_NATIVE_GOAL:-0}} "
        f"OY_OP_NATIVE_GOAL_ACTION_LOOP=${{OY_OP_NATIVE_GOAL_ACTION_LOOP:-0}} "
        f"OY_OP_NATIVE_GOAL_MULTI_STEP=${{OY_OP_NATIVE_GOAL_MULTI_STEP:-0}} "
        f"OY_OP_NATIVE_GOAL_STAGE_GOALS=${{OY_OP_NATIVE_GOAL_STAGE_GOALS:-0}} "
        f"OY_ENABLE_LEGACY_RALPH_PROMPTS=${{OY_ENABLE_LEGACY_RALPH_PROMPTS:-0}} "
        f"OY_OP_CONTEXT_CARD=${{OY_OP_CONTEXT_CARD:-0}} PYTHONPATH={repo} "
        f"python3 {poll_script} {mode} {mailbox} {vault}"
    )
    result = subprocess.run(["tmux", "new-window", "-t", session, "-n", window, "-d", cmd], capture_output=True, text=True)
    if result.returncode != 0:
        return {
            "status": "blocked",
            "reason_code": "debug_monitor_start_failed",
            "session": session,
            "window": window,
            "vault": str(vault),
            "stderr": (result.stderr or result.stdout or "").strip()[:240],
        }
    return {
        "status": "started",
        "session": session,
        "window": window,
        "vault": str(vault),
        "flow": "not_started_by_default",
    }

def cmd_spawn(provider: str, *, force_new: bool = False) -> None:
    _ensure_tmux_hygiene()
    reg = _load_registry()
    existing = _existing_pair_for_provider(reg, provider)
    if existing and not force_new:
        producer, consumer = existing
        vault = reg[producer]["vault"]
        _workflow(
            "YGG SPAWN",
            now=f"{provider} provider memory pair reuse check",
            watching="provider memory pair registry",
            creating="새 memory pair 없음",
            created=f"{_op_label(producer)} + {_op_label(consumer)} already allocated",
            evidence="existing memory pair is already allocated; use --new only when a distinct provider lane is required",
            next_action=f"ygg {_op_command_for(producer)} / ygg {_op_command_for(consumer)} 사용",
            status="done",
        )
        return
    p, c = _next_pair(reg)
    vault = str(_default_vault())
    now = datetime.now(timezone.utc).isoformat()
    for num, otype in [(p, "producer"), (c, "consumer")]:
        op = f"OP{num}"
        (SESSIONS_DIR / op).mkdir(parents=True, exist_ok=True)
        reg[op] = {"provider": provider, "type": otype, "vault": vault, "created": now}
    _save_registry(reg)
    print(f"{_op_label(f'OP{p}')} + {_op_label(f'OP{c}')} allocated for {provider}")
    print("  vault: configured")

def cmd_list() -> None:
    reg = _load_registry()
    if not reg:
        print("(no sessions)")
        return
    for op in sorted(reg.keys(), key=lambda x: _op_number(x)):
        r = reg[op]
        print(f"  {_op_label(op)} [{r['provider']}] {r['type']}")

def cmd_release(op: str) -> None:
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    del reg[op]
    _save_registry(reg)
    print(f"{label} released")

def cmd_status(op: str) -> None:
    reg = _load_registry()
    op = _resolve_op(op)
    if op not in reg:
        label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
        _workflow(
            "YGG STATUS",
            now=f"{label} registration check",
            watching="memory lane registry",
            creating="상태 보고",
            created="등록된 memory lane 없음",
            evidence=f"{label}: not registered",
            next_action="ygg list 또는 ygg spawn으로 세션 등록 상태 확인",
            status="blocked",
        )
        return
    r = reg[op]
    label = _op_label(op)
    sd = SESSIONS_DIR / op
    is_producer = r["type"] == "producer"
    receipt_file = sd / ("receipts.jsonl" if is_producer else "query_receipts.jsonl")
    intents_file = sd / ("intents.jsonl" if is_producer else "queries.jsonl")
    receipt_count = sum(1 for _ in receipt_file.read_text(encoding="utf-8").splitlines() if _.strip()) if receipt_file.exists() else 0
    intent_count = sum(1 for _ in intents_file.read_text(encoding="utf-8").splitlines() if _.strip()) if intents_file.exists() else 0
    last_summary, evidence = _latest_status_summary(op, r, receipt_file, is_producer)
    cpr_summary = _provider_cpr_status_summary_for_op(op, reg)
    if cpr_summary:
        last_summary = f"{last_summary}; {cpr_summary}"
    pending = max(intent_count - receipt_count, 0)
    _workflow(
        "YGG STATUS",
        now=f"{label} status check",
        watching=f"worker={label}; role={r['type']}",
        creating="intent/receipt count and latest processing summary",
        created=f"intents={intent_count}, receipts={receipt_count}, pending={pending}; {last_summary}",
        evidence=evidence,
        next_action="If pending remains, inspect Postman activation/live pane or Result Receipt ledger; do not treat the optional debug lens as the product owner",
        status="done",
    )

def cmd_tell(op: str, message: str, use_ptc: bool = False, memory_ticket: bool = False) -> None:
    """Provider save 요청을 Postman live-delivery 경로에 위탁한다."""
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    r = reg[op]
    if r["type"] != "producer":
        print(f"Error: {label} is {r['type']}, use 'ygg ask' for Memory Finder")
        sys.exit(1)

    sd = SESSIONS_DIR / op
    if use_ptc and memory_ticket:
        print("Error: --ptc and --memory-ticket cannot be combined")
        sys.exit(2)
    if not use_ptc and _looks_like_memory_ticket_text(message) and not _has_classic_save_marker(message):
        if not memory_ticket:
            _workflow(
                "PROVIDER",
                now="사용자 저장 요청을 Postman live-delivery에 위탁하기 전 양식 검증",
                watching=f"message_chars={len(message)}; recipient={label}; command=ygg {_op_command_for(op)}",
                creating=f"{label} Save Request",
                created="생성 안 함: MemoryTicket 계약 필드가 classic context_snapshot 문자열 안에 섞여 있음",
                evidence="classic tell은 runtime.operator.producer save path에서 extract_decisions(context_snapshot)를 사용하므로 marker 없는 MemoryTicket 문자열은 produced_count=0이 됨",
                next_action="classic 저장이면 '결정: ... 이유: ... 실행: ...' 마커를 넣고, 원본 포인터 티켓이면 'ygg tell --memory-ticket ms1 ...'로 구조화 payload를 발행",
                status="blocked",
            )
            sys.exit(2)

    if memory_ticket:
        payload = _parse_memory_ticket_payload(message)
    else:
        payload = {"context_snapshot": message}
    if use_ptc:
        payload["ptc"] = True
        snapshot_literal = json.dumps(message, ensure_ascii=False)
        payload["ptc_code"] = (
            f"snapshot = {snapshot_literal}\n"
            f'triples = extract_spo(snapshot)\n'
            f'for t in triples:\n'
            f'    cat = suggest_placement(t.get("subject","")).get("suggested_category","concept")\n'
            f'    save_note(t.get("subject","")[:80], t.get("object",""), category=cat)\n'
            f'result({{"saved": len(triples)}})'
        )

    sys.path.insert(0, str(REPO / "runtime"))
    from delivery.postman_live_delivery import PostmanIntegrityError, submit_live_delivery

    try:
        delivery = submit_live_delivery(
            recipient=_live_delivery_recipient_for(op),
            message_type="memory_ticket" if memory_ticket else "save",
            payload=payload,
            provider_id=str(r.get("provider") or _provider_id()),
        )
    except PostmanIntegrityError as exc:
        result = exc.result
        _workflow(
            "POSTMAN",
            now="Provider to Memory Saver delivery integrity check",
            watching=f"message_chars={len(message)}; recipient={label}; command=ygg {_op_command_for(op)}",
            creating=f"{label} Save Request",
            created=f"배달 차단: {result.get('reason')}",
            evidence=f"{REGISTRY_DIR / 'postman' / 'rejected.jsonl'}; {result.get('evidence')}",
            next_action="classic 저장이면 저장 마커를 넣고, 원본 포인터 티켓이면 message_type=memory_ticket 구조화 payload로 발행",
            status="blocked",
        )
        sys.exit(2)

    activation = _postman_activate_native_lane(
        op,
        r,
        delivery,
        message_type="memory_ticket" if memory_ticket else "save",
        payload=payload,
    )
    _workflow(
        "PROVIDER",
        now="사용자 저장 요청을 Postman live-delivery에 위탁",
        watching=f"message_chars={len(message)}; recipient={label}; command=ygg {_op_command_for(op)}",
        creating="Delivery Monitor outbox + delivery_log + Memory Saver mailbox work_order/history" + (" (MemoryTicket)" if memory_ticket else " (PTC)" if use_ptc else ""),
        created=f"delivery_id={delivery['delivery_id']} mail_id={delivery['mail_id']} work_order={delivery.get('work_order_id')}",
        evidence=f"delivery_log; work_order; work_history; postman_activation={activation.get('status')}; legacy_debug_monitor=not_used",
        next_action="Postman이 수신인 Memory lane을 CPR함. 작업 진실은 mailbox work_order/history/receipt로 확인",
        status="done",
    )

def cmd_ask(op: str, question: str, use_ptc: bool = False) -> None:
    """Provider 회상 요청을 Postman live-delivery 경로에 위탁한다."""
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    r = reg[op]
    if r["type"] != "consumer":
        print(f"Error: {label} is {r['type']}, use 'ygg tell' for Memory Saver")
        sys.exit(1)

    sd = SESSIONS_DIR / op
    payload = {"query_text": question}
    if use_ptc:
        question_literal = json.dumps(question, ensure_ascii=False)
        payload["ptc"] = True
        payload["ptc_code"] = f"result(deep_search({question_literal}, max_depth=3, limit=15))"

    sys.path.insert(0, str(REPO / "runtime"))
    from delivery.postman_live_delivery import PostmanIntegrityError, submit_live_delivery

    try:
        delivery = submit_live_delivery(
            recipient=_live_delivery_recipient_for(op),
            message_type="query",
            payload=payload,
            provider_id=str(r.get("provider") or _provider_id()),
        )
    except PostmanIntegrityError as exc:
        result = exc.result
        _workflow(
            "POSTMAN",
            now="Provider to Memory Finder delivery integrity check",
            watching=f"question_chars={len(question)}; recipient={label}; command=ygg {_op_command_for(op)}",
            creating=f"{label} Find Request",
            created=f"배달 차단: {result.get('reason')}",
            evidence=f"{REGISTRY_DIR / 'postman' / 'rejected.jsonl'}; {result.get('evidence')}",
            next_action="query_text가 있는 query payload로 다시 발행",
            status="blocked",
        )
        sys.exit(2)

    activation = _postman_activate_native_lane(
        op,
        r,
        delivery,
        message_type="query",
        payload=payload,
    )
    _workflow(
        "PROVIDER",
        now="사용자 회상/검색 요청을 Postman live-delivery에 위탁",
        watching=f"question_chars={len(question)}; recipient={label}; command=ygg {_op_command_for(op)}",
        creating="Delivery Monitor outbox + delivery_log + Memory Finder mailbox work_order/history" + (" (PTC)" if use_ptc else ""),
        created=f"delivery_id={delivery['delivery_id']} mail_id={delivery['mail_id']} work_order={delivery.get('work_order_id')}",
        evidence=f"delivery_log; work_order; work_history; postman_activation={activation.get('status')}; legacy_debug_monitor=not_used",
        next_action="Postman이 수신인 Memory lane을 CPR함. 작업 진실은 mailbox work_order/history/receipt로 확인",
        status="done",
    )

def _portable_source_ref(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    marker = "/vault/"
    if marker in normalized:
        return "vault/" + normalized.split(marker, 1)[1]
    if normalized.startswith("vault/"):
        return normalized
    if normalized.startswith("hermes-session-json://"):
        return normalized
    if normalized.startswith("memory://"):
        return normalized
    return text[:180]

def _fact_preview(value: object) -> str:
    if isinstance(value, dict):
        for key in ("support_fact", "fact", "claim", "text", "summary"):
            candidate = value.get(key)
            if candidate:
                return str(candidate).strip()[:300]
        spo = [str(value.get(key) or "").strip() for key in ("subject", "predicate", "object")]
        if any(spo):
            return " ".join(part for part in spo if part)[:300]
        return json.dumps(value, ensure_ascii=False)[:300]
    return str(value or "").strip()[:300]

def _first_list(*values: object) -> list:
    for value in values:
        if isinstance(value, list):
            return value
    return []

def _first_dict(*values: object) -> dict:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}

def _support_view_from_query_receipt(receipt: dict) -> dict:
    bundle = receipt.get("bundle") if isinstance(receipt, dict) else {}
    bundle = bundle if isinstance(bundle, dict) else {}
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    recall_digest = _first_dict(bundle.get("recall_digest"), nested.get("recall_digest"))
    ptc = _first_dict(bundle.get("ptc_retrieval_orchestrator"), nested.get("ptc_retrieval_orchestrator"))
    worker_program = _first_dict(bundle.get("ptc_worker_program"), nested.get("ptc_worker_program"))
    tool_discovery = _first_dict(worker_program.get("tool_discovery"))
    bounded_program = _first_dict(worker_program.get("bounded_program"))
    facts = _first_list(bundle.get("support_facts"), nested.get("support_facts"))
    source_paths = _first_list(
        bundle.get("source_paths"),
        bundle.get("Source References"),
        nested.get("source_paths"),
        nested.get("Source References"),
    )
    nodes = _first_list(bundle.get("nodes"), nested.get("nodes"))
    typed_unavailable = bool(bundle.get("typed_unavailable") or nested.get("typed_unavailable"))
    if facts and source_paths:
        state = "present_with_ring_gap" if typed_unavailable else "present"
    elif typed_unavailable:
        state = "typed_unavailable"
    else:
        state = "weak" if facts or nodes else "absent"
    return {
        "receipt_id": receipt.get("receipt_id"),
        "in_reply_to": receipt.get("in_reply_to"),
        "receipt_status": receipt.get("status"),
        "support_state": state,
        "topic_key": nested.get("topic_key") or bundle.get("topic_key"),
        "community_id": nested.get("community_id") or bundle.get("community_id"),
        "source_ref": nested.get("source_ref") or bundle.get("source_ref"),
        "source_line_range": nested.get("source_line_range") or bundle.get("source_line_range"),
        "support_facts": [_fact_preview(item) for item in facts[:5]],
        "source_paths": [_portable_source_ref(item) for item in source_paths[:6] if _portable_source_ref(item)],
        "nodes_count": len(nodes),
        "recall_digest_status": recall_digest.get("status") if recall_digest else None,
        "ptc_coverage_state": ptc.get("coverage_state") if ptc else None,
        "ptc_generators_attempted": ptc.get("generators_attempted") if ptc else None,
        "ptc_selected_tools": tool_discovery.get("selected_tool_ids") if tool_discovery else None,
        "ptc_bounded_program_kind": bounded_program.get("program_kind") if bounded_program else None,
        "ptc_program_execution_status": (
            bounded_program.get("execution_status") or worker_program.get("execution_status")
            if worker_program
            else None
        ),
        "ptc_tool_call_count": len(bounded_program.get("capability_calls") or []) if bounded_program else None,
        "typed_unavailable_present": typed_unavailable,
    }

def _query_receipt_for_mail_id(op: str, mail_id: str) -> dict:
    path = SESSIONS_DIR / _live_delivery_recipient_for(op) / "query_receipts.jsonl"
    for _line, row in reversed(_jsonl_rows(path)):
        if row.get("in_reply_to") == mail_id or row.get("mail_id") == mail_id:
            return row
    return {}

def _wait_for_query_receipt(op: str, mail_id: str, timeout_seconds: float) -> dict:
    deadline = time.time() + max(0.0, timeout_seconds)
    while time.time() <= deadline:
        receipt = _query_receipt_for_mail_id(op, mail_id)
        if receipt:
            return receipt
        time.sleep(0.5)
    return {}

def _recall_payload(question: str, *, use_ptc: bool) -> dict:
    payload = {"query_text": question}
    if use_ptc:
        question_literal = json.dumps(question, ensure_ascii=False)
        payload["ptc"] = True
        payload["ptc_code"] = f"result(deep_search({question_literal}, max_depth=3, limit=15))"
    return payload

def _recall_blocked_result(label: str, exc) -> dict:
    return {
        "schema_version": "ygg_provider_recall_result.v1",
        "status": "blocked",
        "reason_code": exc.result.get("reason"),
        "recipient": label,
        "evidence": exc.result.get("evidence"),
        "hard_nonclaims": {"full_ux_passed": False, "provider_local_recall_only": False},
    }

def _print_recall_blocked_result(result: dict, *, label: str, question: str, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    _workflow(
        "YGG RECALL",
        now="Provider bounded recall via Memory Finder",
        watching=f"recipient={label}; question_chars={len(question)}",
        creating="Postman Find Request",
        created=f"blocked: {result['reason_code']}",
        evidence=str(result.get("evidence")),
        next_action="Fix query payload before retrying",
        status="blocked",
    )

def _submit_recall_delivery(op: str, record: dict, label: str, question: str, payload: dict, *, json_mode: bool) -> dict:
    sys.path.insert(0, str(REPO / "runtime"))
    from delivery.postman_live_delivery import PostmanIntegrityError, submit_live_delivery

    try:
        return submit_live_delivery(
            recipient=_live_delivery_recipient_for(op),
            message_type="query",
            payload=payload,
            provider_id=str(record.get("provider") or _provider_id()),
        )
    except PostmanIntegrityError as exc:
        result = _recall_blocked_result(label, exc)
        _print_recall_blocked_result(result, label=label, question=question, json_mode=json_mode)
        sys.exit(2)

def _build_recall_result(
    *,
    label: str,
    delivery: dict,
    activation: dict,
    receipt: dict,
    support: dict,
    wait_for_receipt: bool,
    timeout_seconds: float,
    provider_sync_wait_downgraded: bool = False,
) -> dict:
    if wait_for_receipt:
        status = "done" if receipt else "pending"
        reason_code = "result_receipt_received" if receipt else "memory_finder_receipt_timeout"
    else:
        status = "accepted"
        reason_code = "find_request_delivered_async"
    provider_answer_guidance = {
        "schema_version": "provider_async_recall_answer_guidance.v1",
        "answer_state": "not_yet_confirmed" if wait_for_receipt and not receipt else "async_recall_queued" if not wait_for_receipt else "support_received",
        "immediate_action": (
            "Answer the current safe core now; if MF1 later returns stronger source-backed support, apply a correction with the density required by the original question. If the user asks to be brief, remove filler without collapsing multi-concept boundary answers into an unstructured single sentence."
            if not wait_for_receipt
            else "Use only returned support when it is source-backed; otherwise answer unsupported."
        ),
        "later_backfill": "later_needed_density_correction",
        "minimum_answer_shape": [
            "core_conclusion",
            "placement_or_decision_criteria",
            "per_item_boundary_when_multiple_concepts_are_named",
            "evidence_state_or_limit",
        ],
        "forbidden_claims": ["unsupported", "unsupported_without_source", "memory_found_without_receipt"],
        "forbidden_surface": ["local_paths", "source_path_lists", "internal_receipt_payloads"],
    }
    return {
        "schema_version": "ygg_provider_recall_result.v1",
        "status": status,
        "reason_code": reason_code,
        "recipient": label,
        "mail_id": delivery["mail_id"],
        "delivery_id": delivery.get("delivery_id"),
        "delivery_mode": "async_postman",
        "wait_for_receipt": wait_for_receipt,
        "timeout_seconds": timeout_seconds if wait_for_receipt else 0,
        "provider_sync_wait_downgraded": provider_sync_wait_downgraded,
        "postman_activation": activation,
        "support": support,
        "provider_answer_guidance": provider_answer_guidance,
        "hard_nonclaims": {
            "full_ux_passed": False,
            "provider_local_recall_only": False,
            "semantic_truth_owned_by_postman": False,
        },
    }

def _recall_workflow_evidence(delivery: dict, support: dict, activation: dict, *, wait_for_receipt: bool) -> dict:
    return {
        "mail_id": delivery["mail_id"],
        "delivery_id": delivery.get("delivery_id"),
        "receipt_id": support.get("receipt_id"),
        "support_state": support.get("support_state"),
        "topic_key": support.get("topic_key"),
        "community_id": support.get("community_id"),
        "source_ref": _portable_source_ref(support.get("source_ref")),
        "source_paths": support.get("source_paths"),
        "support_facts": support.get("support_facts"),
        "ptc_coverage_state": support.get("ptc_coverage_state"),
        "typed_unavailable_present": support.get("typed_unavailable_present"),
        "postman_activation": activation.get("status"),
        "legacy_debug_monitor": "not_used",
        "wait_for_receipt": wait_for_receipt,
    }


def _provider_sync_recall_allowed() -> bool:
    return os.environ.get("YGG_ALLOW_PROVIDER_SYNC_RECALL", "").strip().lower() in {"1", "true", "yes"}

def _print_recall_workflow(
    *,
    label: str,
    question: str,
    delivery: dict,
    support: dict,
    activation: dict,
    wait_for_receipt: bool,
    timeout_seconds: float,
    status: str,
) -> None:
    evidence = _recall_workflow_evidence(
        delivery,
        support,
        activation,
        wait_for_receipt=wait_for_receipt,
    )
    _workflow(
        "YGG RECALL",
        now="Provider async recall via Memory Finder" if not wait_for_receipt else "Provider bounded recall via Memory Finder",
        watching=f"recipient={label}; question_chars={len(question)}" + (f"; timeout={timeout_seconds}s" if wait_for_receipt else "; no receipt wait"),
        creating="Postman Find Request" + (" + bounded Result Receipt wait" if wait_for_receipt else " only"),
        created=f"mail_id={delivery['mail_id']}; receipt_id={support.get('receipt_id') or 'none'}; support_state={support.get('support_state') or 'pending'}",
        evidence=json.dumps(evidence, ensure_ascii=False)[:1800],
        next_action="Do not wait in Provider chat; answer may be deferred until CPR/receipt arrives" if not wait_for_receipt else "Use support_facts/source_refs only; no Full UX or production-ready claim",
        status=status,
    )

def cmd_recall(
    op: str,
    question: str,
    *,
    use_ptc: bool = False,
    timeout_seconds: float = 75.0,
    json_mode: bool = False,
    wait_for_receipt: bool = False,
) -> None:
    """Provider recall path: async Postman request by default, bounded wait only when explicit."""
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(json.dumps({"status": "blocked", "reason_code": "memory_finder_not_registered", "recipient": label}, ensure_ascii=False) if json_mode else f"Error: {label} not found")
        sys.exit(1)
    r = reg[op]
    if r["type"] != "consumer":
        print(json.dumps({"status": "blocked", "reason_code": "recipient_not_memory_finder", "recipient": label}, ensure_ascii=False) if json_mode else f"Error: {label} is {r['type']}, use a Memory Finder")
        sys.exit(1)
    provider_sync_wait_downgraded = False
    if wait_for_receipt and os.environ.get("YGG_PROVIDER_SESSION_ID") and not _provider_sync_recall_allowed():
        wait_for_receipt = False
        provider_sync_wait_downgraded = True

    payload = _recall_payload(question, use_ptc=use_ptc)
    delivery = _submit_recall_delivery(op, r, label, question, payload, json_mode=json_mode)
    activation = _postman_activate_native_lane(
        op,
        r,
        delivery,
        message_type="query",
        payload=payload,
    )
    mail_id = delivery["mail_id"]
    receipt = _wait_for_query_receipt(op, mail_id, timeout_seconds) if wait_for_receipt else {}
    support = _support_view_from_query_receipt(receipt) if receipt else {}
    result = _build_recall_result(
        label=label,
        delivery=delivery,
        activation=activation,
        receipt=receipt,
        support=support,
        wait_for_receipt=wait_for_receipt,
        timeout_seconds=timeout_seconds,
        provider_sync_wait_downgraded=provider_sync_wait_downgraded,
    )
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    _print_recall_workflow(
        label=label,
        question=question,
        delivery=delivery,
        support=support,
        activation=activation,
        wait_for_receipt=wait_for_receipt,
        timeout_seconds=timeout_seconds,
        status=result["status"],
    )

def cmd_op(op: str) -> None:
    """Open or recall a memory-lane tmux session."""
    _ensure_tmux_hygiene()
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not registered")
        sys.exit(1)
    r = reg[op]
    session = _ensure_memory_lane_tmux_name(op)
    mailbox = SESSIONS_DIR / op
    vault = r["vault"]
    command = _memory_lane_command(op, r, mailbox, vault)
    if not command:
        _workflow(
            "YGG MEMORY LANE",
            now=f"{label} launcher configuration check",
            watching=f"provider={r.get('provider')}; op={op}; mailbox={mailbox}",
            creating="provider-neutral memory lane tmux command",
            created="launcher missing",
            evidence=(
                "Set OY_MEMORY_SAVER_COMMAND/OY_MS_COMMAND for Memory Saver or "
                "OY_MEMORY_FINDER_COMMAND/OY_MF_COMMAND for Memory Finder. "
                "Hermes defaults are used only when provider=hermes."
            ),
            next_action="configure provider command template before opening this memory lane",
            status="blocked",
        )
        sys.exit(2)

    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0:
        _tmux_attach_or_switch(session)
        return

    pid = os.fork()
    if pid == 0:
        os.setsid()
        env = os.environ.copy()
        env["OY_MAILBOX"] = str(mailbox)
        env["OY_VAULT"] = vault
        env["OY_OP"] = op
        env["OY_OP_TYPE"] = r["type"]
        os.execvpe("tmux", [
            "tmux", "new-session", "-d", "-s", session,
            command,
        ], env)
        sys.exit(1)
    time.sleep(1)
    _tmux_attach_or_switch(session)

def cmd_dev(op: str = "") -> None:
    """Open or recall the Provider lane or a memory witness lane."""
    _ensure_tmux_hygiene()
    if op == "--doctor":
        cmd_provider_lane_doctor()
        return
    if op:
        return cmd_op(op)

    session = PROVIDER_PAIR_SESSION
    requested_provider_id = _env_text("OY_PROVIDER_ID")

    # 이미 실행 중인지 확인
    if _tmux_session_exists(session):
        record = _read_provider_lane_record(session)
        active_provider_id = record.get("provider_id") if isinstance(record, dict) else None
        if requested_provider_id and active_provider_id and requested_provider_id != active_provider_id:
            _workflow(
                "YGG PROVIDER LANE",
                now="Provider Lane provider mismatch check",
                watching=f"requested={requested_provider_id}; active={active_provider_id}; session={session}",
                creating="attach safety decision",
                created="attach blocked: active Provider Lane belongs to another provider",
                evidence=str(_provider_lane_record_path(session)),
                next_action="use the active provider lane or close/rebind the lane before changing OY_PROVIDER_ID",
                status="blocked",
            )
            sys.exit(2)
        health_status = cmd_provider_lane_doctor(attach_intent=True)
        record = _read_provider_lane_record(session)
        if health_status == "degraded" and (not record or "active_op_pair" not in record):
            _write_provider_lane_record(session, event="active_group_redefined_before_attach")
            cmd_provider_lane_doctor(attach_intent=True)
        _tmux_attach_or_switch(session)
        return

    # 새 tmux 세션 + hermes 실행
    provider_id = _provider_id()
    provider_profile = _provider_profile(provider_id)
    provider_session_id = _provider_session_id_for(session)
    command = _provider_command(provider_id, provider_profile, provider_session_id)
    if not command:
        _workflow(
            "YGG PROVIDER LANE",
            now="Provider Lane launcher configuration check",
            watching=f"provider={provider_id}; profile={provider_profile}; session={session}",
            creating="provider-neutral Provider Lane tmux command",
            created="launcher missing",
            evidence="Set OY_PROVIDER_COMMAND. Hermes default is used only when OY_PROVIDER_ID is hermes or unset.",
            next_action="configure OY_PROVIDER_COMMAND before creating this Provider Lane",
            status="blocked",
        )
        sys.exit(2)
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.execvp("tmux", [
            "tmux", "new-session", "-d", "-s", session,
            command,
        ])
        sys.exit(1)

    time.sleep(1)
    _write_provider_lane_record(session, event="created_by_ygg_pro1")
    cmd_provider_lane_doctor(attach_intent=True)
    _tmux_attach_or_switch(session)

def cmd_provider_command(args: list[str]) -> None:
    """User-facing Provider lane command. Internal tmux session is ygg-pro1."""
    if args == ["--doctor"]:
        cmd_provider_lane_doctor()
        return
    if args == ["--cpr"]:
        cmd_cpr([])
        return
    if args:
        print("Usage: ygg pro1 [--doctor|--cpr]")
        sys.exit(1)
    cmd_dev("")


__all__ = [
    "_memory_lane_command",
    "_run_operator",
    "_tail_jsonl",
    "_latest_status_summary",
    "_looks_like_memory_ticket_text",
    "_parse_range_value",
    "_parse_memory_ticket_payload",
    "_has_classic_save_marker",
    "_live_debug_monitor_lines",
    "_postman_activate_native_lane",
    "_ensure_live_debug_monitor",
    "cmd_spawn",
    "cmd_list",
    "cmd_release",
    "cmd_status",
    "cmd_tell",
    "cmd_ask",
    "_portable_source_ref",
    "_fact_preview",
    "_first_list",
    "_first_dict",
    "_support_view_from_query_receipt",
    "_query_receipt_for_mail_id",
    "_wait_for_query_receipt",
    "cmd_recall",
    "cmd_op",
    "cmd_dev",
    "cmd_provider_command",
]
