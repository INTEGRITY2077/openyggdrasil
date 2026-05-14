from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime.cli.ygg_config import (
    DEFAULT_ACTIVE_PAIR,
    LEGACY_OPERATOR_TMUX_SESSION_PATTERN,
    LEGACY_PROVIDER_SESSIONS,
    NATIVE_PROVIDER_SESSION_UNOBSERVED,
    PRIVATE_DEV,
    PROVIDER_LANE_DIR,
    PROVIDER_PAIR_SESSION,
    REGISTRY_DIR,
    REGISTRY_FILE,
    REPO,
    SESSIONS_DIR,
    TMUX_CORE_SESSIONS,
    TMUX_HYGIENE_OPTIONS,
    _env_text,
    _provider_command,
    _provider_id,
    _provider_profile,
    _workflow,
)
from runtime.cli.ygg_tmux import _tmux, _tmux_session_exists

def _provider_lane_record_path(session: str) -> Path:
    return PROVIDER_LANE_DIR / f"{session}.json"

def _read_provider_lane_record(session: str) -> dict:
    path = _provider_lane_record_path(session)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"unparseable_record": str(path)}

def _op_tmux_session(op: str) -> str:
    num = int(str(op).upper().replace("OP", ""))
    unit = (num + 1) // 2
    prefix = "ms" if num % 2 else "mf"
    return f"ygg-{prefix}{unit}"

def _legacy_op_tmux_session(op: str) -> str:
    return f"ygg-{op.lower()}"

def _ensure_memory_lane_tmux_name(op: str) -> str:
    session = _op_tmux_session(op)
    legacy = _legacy_op_tmux_session(op)
    if not _tmux_session_exists(session) and _tmux_session_exists(legacy):
        _tmux("rename-session", "-t", legacy, session)
    return session

def _op_number(op: str) -> int:
    return int(str(op).upper().replace("OP", ""))

def _unit_number_for_op(op: str) -> int:
    num = _op_number(op)
    return (num + 1) // 2

def _canonical_alias_for_op(op: str) -> str:
    num = _op_number(op)
    unit = _unit_number_for_op(op)
    return f"MS{unit}" if num % 2 else f"MF{unit}"

def _role_name_for_op(op: str) -> str:
    return "Memory Saver" if _op_number(op) % 2 else "Memory Finder"

def _op_label(op: str) -> str:
    return f"{_canonical_alias_for_op(op)} ({_role_name_for_op(op)})"

def _op_command_for(op: str) -> str:
    return _canonical_alias_for_op(op).lower()

def _active_pair_from_record(record: dict, reg: dict, provider_id: str) -> tuple[str, str]:
    pair = record.get("active_op_pair") if isinstance(record, dict) else None
    if isinstance(pair, dict):
        producer = pair.get("producer")
        consumer = pair.get("consumer")
        if producer and consumer:
            return str(producer), str(consumer)
    existing = _existing_pair_for_provider(reg, provider_id)
    if existing:
        return existing
    return DEFAULT_ACTIVE_PAIR

def _ensure_runtime_path() -> None:
    runtime_path = str(REPO / "runtime")
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)

def _provider_session_id_for(session: str) -> str:
    value = os.environ.get("OY_PROVIDER_SESSION_ID", "").strip()
    return value or session

def _provider_lane_needs_binding(record: dict) -> bool:
    if not record or "unparseable_record" in record:
        return not record
    provider_inbox = record.get("provider_inbox")
    if record.get("provider_session_id") in ("", None, NATIVE_PROVIDER_SESSION_UNOBSERVED):
        return True
    if record.get("provider_session_id_source") != "ygg_provider_lane_binding.v1":
        return True
    if not isinstance(provider_inbox, dict):
        return True
    if provider_inbox.get("status") != "bound":
        return True
    if not provider_inbox.get("inbox_path"):
        return True
    return False

def _bootstrap_provider_lane_binding(
    *,
    session: str,
    provider_id: str,
    provider_profile: str,
    active_pair: tuple[str, str],
    event: str,
) -> dict:
    provider_session_id = _provider_session_id_for(session)
    try:
        _ensure_runtime_path()
        from attachments.provider_attachment import (  # noqa: PLC0415
            bootstrap_skill_provider_session,
            build_session_uid,
            provider_attachment_root,
            provider_inbox_path,
        )

        bootstrap_skill_provider_session(
            workspace_root=REPO,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            origin_kind="provider-thread",
            origin_locator={
                "tmux_session": session,
                "event": event,
                "active_pair": list(active_pair),
                "workspace_root": str(REPO),
            },
            provider_extras={
                "provider_lane_binding": "ygg_provider_lane_binding.v1",
                "tmux_session": session,
                "active_pair": list(active_pair),
            },
        )
        session_uid = build_session_uid(
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
        return {
            "status": "bound",
            "provider_session_id": provider_session_id,
            "provider_session_id_source": "ygg_provider_lane_binding.v1",
            "session_uid": session_uid,
            "attachment_root": str(
                provider_attachment_root(
                    workspace_root=REPO,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    provider_session_id=provider_session_id,
                )
            ),
            "inbox_path": str(
                provider_inbox_path(
                    workspace_root=REPO,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    provider_session_id=provider_session_id,
                )
            ),
        }
    except Exception as exc:
        return {
            "status": "typed_unavailable",
            "provider_session_id": provider_session_id,
            "provider_session_id_source": "typed_unavailable",
            "reason_code": f"provider_lane_binding_failed:{exc.__class__.__name__}",
        }

def _write_provider_lane_record(session: str, *, event: str) -> None:
    PROVIDER_LANE_DIR.mkdir(parents=True, exist_ok=True)
    provider_id = _provider_id()
    reg = _load_registry()
    producer, consumer = _active_pair_from_record({}, reg, provider_id)
    provider_profile = _provider_profile(provider_id)
    provider_session_id = _provider_session_id_for(session)
    provider_command = _provider_command(provider_id, provider_profile, provider_session_id)
    binding = _bootstrap_provider_lane_binding(
        session=session,
        provider_id=provider_id,
        provider_profile=provider_profile,
        active_pair=(producer, consumer),
        event=event,
    )
    payload = {
        "schema_version": "provider_lane.v1",
        "lane_id": session,
        "active_group_id": f"{session}:{producer}:{consumer}",
        "role": "provider_attach_witness_lane",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": binding.get("provider_session_id", _provider_session_id_for(session)),
        "provider_session_id_source": binding.get("provider_session_id_source", "typed_unavailable"),
        "session_uid": binding.get("session_uid"),
        "workspace_root": str(REPO),
        "tmux_session": session,
        "provider_inbox": {
            "status": binding.get("status"),
            "attachment_root": binding.get("attachment_root"),
            "inbox_path": binding.get("inbox_path"),
            "reason_code": binding.get("reason_code"),
        },
        "active_op_pair": {
            "producer": producer,
            "consumer": consumer,
            "producer_lane": _op_tmux_session(producer),
            "consumer_lane": _op_tmux_session(consumer),
        },
        "command": provider_command,
        "provider_launcher": {
            "status": "configured" if provider_command else "typed_unavailable",
            "source": "OY_PROVIDER_COMMAND" if _env_text("OY_PROVIDER_COMMAND") else (
                "hermes_default" if provider_id == "hermes" else "missing_env"
            ),
            "required_env_when_missing": "OY_PROVIDER_COMMAND",
        },
        "canonical_identity_note": (
            "This lane is not provider identity. Native provider session metadata, "
            "attachment artifacts, mailbox, and receipts are canonical."
        ),
        "last_event": event,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _provider_lane_record_path(session).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload

def _ensure_provider_lane_record_bound(session: str, *, event: str) -> dict:
    record = _read_provider_lane_record(session)
    if _provider_lane_needs_binding(record):
        _write_provider_lane_record(session, event=event)
        record = _read_provider_lane_record(session)
    return record

def _tmux_provider_lane_evidence(session: str) -> tuple[str, str]:
    if not _tmux_session_exists(session):
        return "missing", f"tmux session {session} not found"
    session_created = _tmux("display-message", "-p", "-t", session, "#{session_created}").stdout.strip()
    panes = _tmux(
        "list-panes",
        "-t",
        session,
        "-F",
        "pane=#{session_name}:#{window_index}.#{pane_index} cmd=#{pane_current_command} hist=#{history_size}/#{history_limit}",
    ).stdout.strip()
    return "present", f"session_created={session_created or '?'}\n{panes}"

def _op_pair_health_lines(pair: tuple[str, str], reg: dict) -> list[str]:
    lines = []
    for op in pair:
        r = reg.get(op)
        session = _op_tmux_session(op)
        label = _op_label(op)
        command = f"ygg {_op_command_for(op)}"
        if not r:
            lines.append(
                f"{label}: command={command} registry_missing "
                f"tmux={session}:{'present' if _tmux_session_exists(session) else 'missing'}"
            )
            continue
        mailbox = SESSIONS_DIR / op
        mode = "produce" if r.get("type") == "producer" else "consume"
        target_cmd = f"ygg_poll.py {mode} {mailbox}"
        try:
            proc = subprocess.run(["pgrep", "-af", target_cmd], capture_output=True, text=True)
            proc_stdout = proc.stdout
        except FileNotFoundError:
            proc_stdout = ""
        running = [
            row for row in proc_stdout.splitlines()
            if "pgrep" not in row and "ygg_poll.py" in row
        ]
        lines.append(
            f"{label}: command={command} registry={r.get('provider')}/{r.get('type')} "
            f"tmux={session}:{'present' if _tmux_session_exists(session) else 'missing'} "
            f"debug_monitor={'present' if running else 'missing'} "
            f"mailbox={mailbox}"
        )
    return lines

def _provider_lane_zombie_hints(active_session: str, active_pair: tuple[str, str]) -> list[str]:
    sessions = _tmux("list-sessions", "-F", "#{session_name}").stdout.splitlines()
    active_op_sessions = {_op_tmux_session(op) for op in active_pair}
    provider_like = [
        row for row in sessions
        if re.match(r"^(oy-(provider|\d+)|ygg-pro\d+)$", row) and row != active_session
    ]
    op_like = [
        row for row in sessions
        if re.match(LEGACY_OPERATOR_TMUX_SESSION_PATTERN, row) and row not in active_op_sessions
    ]
    reg = _load_registry()
    inactive_ops = [
        op for op in sorted(reg.keys(), key=lambda x: int(x.replace("OP", "")))
        if op not in set(active_pair)
    ]
    try:
        live = subprocess.run(["pgrep", "-af", "ygg_poll.py"], capture_output=True, text=True)
        live_stdout = live.stdout
    except FileNotFoundError:
        live_stdout = ""
    orphan_live = []
    for row in live_stdout.splitlines():
        if "pgrep" in row or "ygg_poll.py" not in row:
            continue
        match = re.search(r"/sessions/(OP\d+)", row)
        if match and match.group(1) not in set(active_pair):
            orphan_live.append(match.group(1))
    hints = []
    if provider_like:
        hints.append(f"extra_provider_like_tmux={','.join(provider_like)}")
    if op_like:
        hints.append(f"extra_op_tmux={','.join(op_like)}")
    if inactive_ops:
        hints.append(f"inactive_registry_ops={','.join(inactive_ops)}")
    if orphan_live:
        hints.append(f"orphan_debug_monitors={','.join(sorted(set(orphan_live)))}")
    return hints

def cmd_provider_lane_doctor(*, attach_intent: bool = False) -> str:
    _ensure_tmux_hygiene()
    session = PROVIDER_PAIR_SESSION
    record = _read_provider_lane_record(session)
    reg = _load_registry()
    provider_id = record.get("provider_id", _provider_id()) if record else _provider_id()
    active_pair = _active_pair_from_record(record, reg, provider_id)
    tmux_status, tmux_evidence = _tmux_provider_lane_evidence(session)
    if tmux_status != "missing" and _provider_lane_needs_binding(record):
        record = _ensure_provider_lane_record_bound(session, event="provider_session_binding_repaired")
        reg = _load_registry()
        provider_id = record.get("provider_id", _provider_id()) if record else _provider_id()
        active_pair = _active_pair_from_record(record, reg, provider_id)
    op_pair_lines = _op_pair_health_lines(active_pair, reg)
    zombie_hints = _provider_lane_zombie_hints(session, active_pair)
    if tmux_status == "missing":
        status = "blocked" if attach_intent else "done"
        created = "provider lane 없음"
        next_action = "ygg pro1 실행 시 Provider lane을 만들고 같은 명령으로 재소환 가능"
    elif not record:
        status = "degraded"
        created = "tmux lane은 있으나 provider_lane.v1 record 없음"
        next_action = "재소환 전 현재 lane을 legacy_unverified로 재정의하고 record 작성"
    elif "unparseable_record" in record:
        status = "degraded"
        created = "provider_lane.v1 record 파싱 실패"
        next_action = "record를 보존한 뒤 재작성 필요"
    elif "active_op_pair" not in record:
        status = "degraded"
        created = "provider lane record는 있으나 active Memory Saver/Finder pair가 없음"
        next_action = "재소환 전 현재 lane을 active Provider Unit group으로 재정의"
    elif zombie_hints:
        status = "degraded"
        created = "provider lane은 있으나 stale/zombie 후보가 있음"
        next_action = "활성 lane 기준으로 registry와 tmux session을 정리"
    else:
        status = "done"
        created = "provider lane active"
        next_action = "어디서든 ygg pro1 / ygg ms1 / ygg mf1로 현재 Provider Unit 세션 재소환"

    record_path = _provider_lane_record_path(session)
    record_summary = (
        f"record={record_path}; "
        f"provider_id={record.get('provider_id', '?') if record else 'missing'}; "
        f"provider_session_id={record.get('provider_session_id', '?') if record else 'missing'}; "
        f"display_pair={_canonical_alias_for_op(active_pair[0])}/{_canonical_alias_for_op(active_pair[1])}; "
        f"internal_pair={active_pair[0]}/{active_pair[1]}"
    )
    evidence = "\n".join(
        row for row in [
            record_summary,
            tmux_evidence,
            "\n".join(op_pair_lines),
            "; ".join(zombie_hints),
        ] if row
    )
    _workflow(
        "YGG SESSION GROUP HEALTH",
        now="현재 Provider Unit 1 활성 세션 그룹 유효성 확인",
        watching=(
            f"entry=ygg pro1/ygg ms1/ygg mf1; session={session}; "
            f"display_pair={_canonical_alias_for_op(active_pair[0])}/{_canonical_alias_for_op(active_pair[1])}; "
            f"internal_pair={active_pair[0]}/{active_pair[1]}; workspace={REPO}; attach_intent={attach_intent}"
        ),
        creating="active group / stale / zombie chain 판정",
        created=created,
        evidence=evidence[:1200],
        next_action=next_action,
        status=status,
    )
    return status

def cmd_tmux_doctor() -> None:
    _ensure_tmux_hygiene()
    sessions = _tmux("list-sessions", "-F", "#{session_name}").stdout.splitlines()
    clients = _tmux(
        "list-clients",
        "-F",
        "client=#{client_tty} size=#{client_width}x#{client_height} session=#{client_session}",
    ).stdout.strip()
    panes = _tmux(
        "list-panes",
        "-a",
        "-F",
        "pane=#{session_name}:#{window_index}.#{pane_index} hist=#{history_size}/#{history_limit} cmd=#{pane_current_command}",
    ).stdout.strip()
    stale = [session for session in sessions if session not in TMUX_CORE_SESSIONS]
    _workflow(
        "YGG TMUX",
        now="tmux witness surface hygiene check",
        watching=(
            "entry=ygg pro1/ygg ms1/ygg mf1; "
            f"core_tmux={','.join(sorted(TMUX_CORE_SESSIONS))}; stale={','.join(stale) or 'none'}"
        ),
        creating="bounded tmux option set + stale session report",
        created="tmux hygiene options applied",
        evidence=(clients + "\n" + panes)[:1200],
        next_action="inspect with ygg pro1 / ygg ms1 / ygg mf1 before clearing any stale proof sessions; raw tmux names are evidence only",
        status="done",
    )

def _load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    return json.loads(REGISTRY_FILE.read_text())

def _save_registry(reg: dict) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2, ensure_ascii=False))

def _next_pair(reg: dict) -> tuple[int, int]:
    used = {int(k.replace("OP", "")) for k in reg}
    n = 1
    while n in used or (n + 1) in used:
        n += 2
    return n, n + 1

def _existing_pair_for_provider(reg: dict, provider: str) -> tuple[str, str] | None:
    ops = sorted(reg.keys(), key=lambda x: int(x.replace("OP", "")))
    for op in ops:
        try:
            num = int(op.replace("OP", ""))
        except ValueError:
            continue
        if num % 2 == 0:
            continue
        peer = f"OP{num + 1}"
        left = reg.get(op, {})
        right = reg.get(peer, {})
        if (
            left.get("provider") == provider
            and right.get("provider") == provider
            and left.get("type") == "producer"
            and right.get("type") == "consumer"
        ):
            return op, peer
    return None

def _resolve_op(arg: str) -> str:
    """Resolve public memory-lane aliases to the internal OP registry id."""
    m = re.match(r'^ms(\d+)$', arg, re.IGNORECASE)
    if m:
        return f"OP{(int(m.group(1)) * 2) - 1}"
    m = re.match(r'^mf(\d+)$', arg, re.IGNORECASE)
    if m:
        return f"OP{int(m.group(1)) * 2}"
    m = re.match(r'^(op|OP)?(\d+)$', arg, re.IGNORECASE)
    if m:
        return f"OP{m.group(2)}"
    if arg.startswith("OP") and arg[2:].isdigit():
        return arg
    return f"OP{arg}" if arg.isdigit() else arg

def _ensure_tmux_hygiene() -> None:
    """Keep tmux usable as a witness surface, not an unbounded work log."""
    for args in TMUX_HYGIENE_OPTIONS:
        _tmux(*args)
    if (
        any(_tmux_session_exists(session) for session in LEGACY_PROVIDER_SESSIONS)
        and not _tmux_session_exists(PROVIDER_PAIR_SESSION)
    ):
        legacy = next(session for session in LEGACY_PROVIDER_SESSIONS if _tmux_session_exists(session))
        _tmux("rename-session", "-t", legacy, PROVIDER_PAIR_SESSION)
    try:
        reg = _load_registry()
    except Exception:
        reg = {}
    for op in sorted(reg):
        if re.fullmatch(r"OP\d+", op):
            _ensure_memory_lane_tmux_name(op)


__all__ = [
    "_provider_lane_record_path",
    "_read_provider_lane_record",
    "_op_tmux_session",
    "_legacy_op_tmux_session",
    "_ensure_memory_lane_tmux_name",
    "_op_number",
    "_unit_number_for_op",
    "_canonical_alias_for_op",
    "_role_name_for_op",
    "_op_label",
    "_op_command_for",
    "_active_pair_from_record",
    "_ensure_runtime_path",
    "_provider_session_id_for",
    "_provider_lane_needs_binding",
    "_bootstrap_provider_lane_binding",
    "_write_provider_lane_record",
    "_ensure_provider_lane_record_bound",
    "_tmux_provider_lane_evidence",
    "_op_pair_health_lines",
    "_provider_lane_zombie_hints",
    "cmd_provider_lane_doctor",
    "cmd_tmux_doctor",
    "_load_registry",
    "_save_registry",
    "_next_pair",
    "_existing_pair_for_provider",
    "_resolve_op",
    "_ensure_tmux_hygiene",
]
