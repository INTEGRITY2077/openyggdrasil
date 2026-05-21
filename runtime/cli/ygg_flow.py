from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime.cli.ygg_config import PRIVATE_DEV, REGISTRY_DIR, REPO, SCRIPTS_DIR, SESSIONS_DIR, _shell_quote, _workflow
from runtime.cli.ygg_cpr import _append_jsonl, _jsonl_rows
from runtime.cli.ygg_memory_lanes import _canonical_alias_for_op, _ensure_memory_lane_tmux_name, _ensure_tmux_hygiene, _op_command_for, _op_label, _resolve_op
from runtime.cli.ygg_registry import _load_registry
from runtime.cli.ygg_tmux import _tmux, _tmux_session_exists


def _session_evidence_ref(op: str, name: str, line: int) -> str:
    return f"ygg-session://{op}/{name}:{line}"


def _start_flow_window(op: str, record: dict, *, select: bool) -> dict:
    session = _ensure_memory_lane_tmux_name(op)
    window = "flow"
    mailbox = SESSIONS_DIR / op
    vault = Path(record["vault"])
    mode = "produce" if record["type"] == "producer" else "consume"
    label = _canonical_alias_for_op(op)
    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode != 0:
        return {"status": "blocked", "reason_code": "memory_lane_tmux_session_missing", "session": session}
    existing_windows = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if window in existing_windows.stdout.splitlines():
        subprocess.run(["tmux", "kill-window", "-t", f"{session}:{window}"], capture_output=True)
    private_dev = _shell_quote(PRIVATE_DEV)
    cmd = (
        f"cd {private_dev} && "
        f"python3 scripts/ygg_flow.py --label {label} --mode {mode} "
        f"--mailbox {mailbox} --vault {vault}"
    )
    result = subprocess.run(["tmux", "new-window", "-t", session, "-n", window, "-d", cmd], capture_output=True, text=True)
    if result.returncode == 0 and select:
        subprocess.run(["tmux", "select-window", "-t", f"{session}:{window}"], capture_output=True)
    return {
        "status": "started" if result.returncode == 0 else "blocked",
        "session": session,
        "window": window,
        "returncode": result.returncode,
        "stderr": (result.stderr or result.stdout or "").strip()[:240],
    }

def cmd_flow(op: str) -> None:
    """Open an explicit debug receipt-tail window.

    This is not the worker interface. Hermes remains the primary live surface.
    """
    _ensure_tmux_hygiene()
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    result = _start_flow_window(op, reg[op], select=True)
    _workflow(
        "YGG FLOW",
        now=f"{label} explicit debug receipt-tail monitor",
        watching=f"session={result.get('session')}; window={result.get('window')}; mailbox={SESSIONS_DIR / op}",
        creating="debug-only receipt tail window",
        created=f"status={result.get('status')}",
        evidence=str(result),
        next_action="Use Hermes chat pane for worker behavior; use this only for raw receipt debugging",
        status="done" if result.get("status") == "started" else "blocked",
    )

def cmd_live(op: str) -> None:
    """Run the optional MS/MF delivery debug lens in one tmux window."""
    _ensure_tmux_hygiene()
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    r = reg[op]
    mode = "produce" if r["type"] == "producer" else "consume"
    session = _ensure_memory_lane_tmux_name(op)
    window = "live-postman"
    mailbox = SESSIONS_DIR / op
    vault = Path(r["vault"])
    target_cmd = f"ygg_poll.py {mode} {mailbox}"

    proc = subprocess.run(["pgrep", "-af", target_cmd], capture_output=True, text=True)
    running_lines = [line for line in proc.stdout.splitlines() if "pgrep" not in line and "ygg_poll.py" in line]
    if running_lines:
        _workflow(
            "YGG LIVE",
            now=f"{label} optional MS/MF debug lens already running",
            watching=f"session={session}; mailbox={mailbox}; mode={mode}",
            creating="no new MS/MF debug lens",
            created=f"already running pid={running_lines[0].split()[0]}",
            evidence=running_lines[0][:180] + "; flow=not_started_by_default",
            next_action="Use this only as an optional debug lens; mailbox worker loop remains the default product path",
            status="done",
        )
        return

    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode != 0:
        _workflow(
            "YGG LIVE",
            now=f"{label} live session availability check",
            watching=f"session={session}",
            creating="MS/MF debug lens blocker card",
            created="tmux session missing",
            evidence=f"Run ygg {_op_command_for(op)} first",
            next_action=f"Create the live pane with ygg {_op_command_for(op)}, then run ygg live {_op_command_for(op)} only if a debug lens is needed",
            status="blocked",
        )
        return

    if subprocess.run(["tmux", "list-windows", "-t", session, "-F", "#{window_name}"], capture_output=True, text=True).stdout.splitlines().count(window):
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
        f"OY_OP_CONTEXT_CARD=${{OY_OP_CONTEXT_CARD:-0}} PYTHONPATH={repo} "
        f"python3 {poll_script} {mode} {mailbox} {vault}"
    )
    result = subprocess.run(["tmux", "new-window", "-t", session, "-n", window, "-d", cmd], capture_output=True, text=True)
    _workflow(
        "YGG LIVE",
        now=f"{label} optional MS/MF debug lens start",
        watching=f"session={session}; window={window}; mailbox={mailbox}; mode={mode}",
        creating="optional MS/MF debug lens; worker-owned native loop enabled; stage-goal injection disabled",
        created=f"tmux_returncode={result.returncode}",
        evidence=((result.stderr or result.stdout or f"tmux {session}:{window}")[:180] + "; flow=not_started_by_default").replace("\n", " | "),
        next_action="Postman remains the activation owner; use this lens only to inspect delivery flow",
        status="done" if result.returncode == 0 else "blocked",
    )

def _capture_memory_lane_surface(op: str, *, lines: int = 120) -> str:
    session = _ensure_memory_lane_tmux_name(op)
    if not _tmux_session_exists(session):
        return ""
    captured = _tmux("capture-pane", "-p", "-t", session, "-S", f"-{lines}")
    if captured.returncode != 0:
        return ""
    return captured.stdout or ""

def _surface_contains_work_summary(surface: str, work_summary: str) -> bool:
    summary = " ".join(str(work_summary or "").split())
    if not summary:
        return False
    if summary in surface:
        return True
    return len(summary) >= 36 and summary[:36] in surface

def _absorb_native_surface_close(
    *,
    op: str,
    mailbox: Path,
    mail_id: str,
    work_order_ids: set[str],
) -> tuple[str, int, dict] | None:
    work_order = None
    for _ln, row in reversed(_jsonl_rows(mailbox / "work_orders.jsonl")):
        if row.get("mail_id") == mail_id or row.get("work_order_id") in work_order_ids:
            work_order = row
            break
    if not work_order:
        return None

    surface = _capture_memory_lane_surface(op)
    if "typed_unavailable" not in surface:
        return None
    if not _surface_contains_work_summary(surface, str(work_order.get("work_summary") or "")):
        return None

    role = str(work_order.get("worker_role") or "")
    receipt_file = "query_receipts.jsonl" if role == "memory_finder" else "receipts.jsonl"
    receipt_path = mailbox / receipt_file
    work_order_id = str(work_order.get("work_order_id") or f"work-{mail_id}")
    for _ln, row in _jsonl_rows(receipt_path):
        if row.get("in_reply_to") in {mail_id, work_order_id} or row.get("mail_id") == mail_id:
            return None

    status = "typed_unavailable_native_surface"
    reason_code = "native_worker_closed_without_structured_receipt"
    receipt = {
        "schema_version": "postman_native_surface_receipt.v1",
        "in_reply_to": work_order_id,
        "mail_id": mail_id,
        "status": status,
        "reason_code": reason_code,
        "produced_count": 0,
        "nodes": [],
        "observed_missing_evidence": [
            "structured_worker_receipt",
            "support_bundle" if role == "memory_finder" else "storage_receipt",
        ],
        "bundle": {
            "typed_unavailable": {
                "schema_version": "typed_unavailable.v1",
                "reason_code": reason_code,
            },
            "support_facts": [],
            "source_paths": [],
        } if role == "memory_finder" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recorded_by": "postman_native_surface_absorber",
        "hard_nonclaims": [
            "native_surface_transcription_is_not_semantic_success",
            "support_or_storage_completion_not_proven",
        ],
    }
    if receipt["bundle"] is None:
        receipt.pop("bundle")
    _append_jsonl(receipt_path, receipt)
    line_no = len(_jsonl_rows(receipt_path))
    return receipt_file, line_no, receipt

def cmd_receipt(mail_id: str) -> None:
    """Check Postman and memory-lane receipt status for one mail_id."""
    reg = _load_registry()
    postman = REGISTRY_DIR / "postman" / "delivery_log.jsonl"
    post_hits = [(ln, row) for ln, row in _jsonl_rows(postman) if row.get("mail_id") == mail_id]
    work_order_ids = {f"work-{mail_id}"}
    for _ln, row in post_hits:
        if row.get("work_order_id"):
            work_order_ids.add(str(row.get("work_order_id")))
    receipt_hits = []
    delivery_hits = []
    live_hits = []
    history_hits = []
    for op in sorted(reg):
        sd = SESSIONS_DIR / op
        for name in ["receipts.jsonl", "query_receipts.jsonl"]:
            for ln, row in _jsonl_rows(sd / name):
                if row.get("in_reply_to") == mail_id or row.get("mail_id") == mail_id or row.get("in_reply_to") in work_order_ids:
                    receipt_hits.append((op, name, ln, row))
        for ln, row in _jsonl_rows(sd / "delivery_receipts.jsonl"):
            if row.get("in_reply_to") == mail_id or row.get("mail_id") == mail_id or row.get("in_reply_to") in work_order_ids:
                delivery_hits.append((op, "delivery_receipts.jsonl", ln, row))
        for ln, row in _jsonl_rows(sd / "work_history.jsonl"):
            if row.get("mail_id") == mail_id or row.get("work_order_id") in work_order_ids:
                history_hits.append((op, "work_history.jsonl", ln, row))
        for ln, row in _jsonl_rows(sd / "live_delivered.jsonl"):
            if row.get("mail_id") == mail_id:
                live_hits.append((op, "live_delivered.jsonl", ln, row))

    if not receipt_hits and post_hits:
        for op in sorted(reg):
            absorbed = _absorb_native_surface_close(
                op=op,
                mailbox=SESSIONS_DIR / op,
                mail_id=mail_id,
                work_order_ids=work_order_ids,
            )
            if absorbed:
                name, ln, row = absorbed
                receipt_hits.append((op, name, ln, row))
                break

    for op, name, ln, row in receipt_hits:
        try:
            if str(REPO) not in sys.path:
                sys.path.insert(0, str(REPO))
            from runtime.delivery.postman_work_order import mirror_worker_receipt_to_history

            mirrored = mirror_worker_receipt_to_history(
                mailbox=SESSIONS_DIR / op,
                mail_id=mail_id,
                receipt=row,
                receipt_file=name,
                receipt_line=ln,
                actor=op,
            )
            if mirrored:
                history_hits.append((op, "work_history.jsonl", -1, mirrored))
        except Exception:
            pass

    status = "done" if receipt_hits or delivery_hits else "pending" if post_hits or live_hits else "blocked"
    latest = receipt_hits[-1] if receipt_hits else None
    if latest:
        row = latest[3]
        if "bundle" in row:
            bundle = row.get("bundle") or {}
            facts = bundle.get("support_facts", []) if isinstance(bundle, dict) else []
            nodes = bundle.get("nodes", []) if isinstance(bundle, dict) else []
            created = f"query_receipt support_facts={len(facts)} nodes={len(nodes)}"
        else:
            nodes = row.get("nodes", []) if isinstance(row, dict) else []
            created = f"receipt status={row.get('status', '?')} produced_count={row.get('produced_count', 0)} nodes={nodes}"
        evidence = _session_evidence_ref(str(latest[0]), str(latest[1]), int(latest[2]))
    elif delivery_hits:
        latest = delivery_hits[-1]
        created = f"delivery_receipt status={latest[3].get('status', '?')} produced_count={latest[3].get('produced_count', '?')}"
        evidence = _session_evidence_ref(str(latest[0]), str(latest[1]), int(latest[2]))
    elif post_hits:
        created = f"Postman delivered, memory-lane receipt pending; delivery_id={post_hits[-1][1].get('delivery_id', '?')}"
        evidence = f"{postman}:{post_hits[-1][0]}"
    else:
        created = "mail_id를 Postman/memory lane 원장에서 찾지 못함"
        evidence = "ygg-session://registry"

    _workflow(
        "YGG RECEIPT",
        now="mail_id 단위 receipt 확인",
        watching=f"mail_id={mail_id}; work_order={','.join(sorted(work_order_ids))}; postman={len(post_hits)}; receipt={len(receipt_hits)}; delivery={len(delivery_hits)}; history={len(history_hits)}; live={len(live_hits)}",
        creating="처리 상태 판정",
        created=created,
        evidence=evidence,
        next_action="pending이면 mailbox worker-loop status를 확인하고, done이면 Vault 또는 support_facts 확인",
        status=status,
    )

def cmd_watch(op: str) -> None:
    """Tail a memory-lane mailbox in real time (Ctrl+C exits)."""
    reg = _load_registry()
    op = _resolve_op(op)
    label = _op_label(op) if str(op).upper().startswith("OP") and str(op)[2:].isdigit() else op
    if op not in reg:
        print(f"Error: {label} not found")
        sys.exit(1)
    r = reg[op]
    sd = SESSIONS_DIR / op
    files = " ".join(str(sd / f) for f in ["intents.jsonl", "receipts.jsonl", "delivery_receipts.jsonl"]
                     if (sd / f).exists())
    if not files:
        # 최소한 intents.jsonl 생성
        (sd / "intents.jsonl").touch()
        files = str(sd / "intents.jsonl")
    print(f"Watching {label} ({r['type']}) - Ctrl+C to stop")
    os.execvp("tail", ["tail", "-f"] + files.split())


__all__ = [
    "_start_flow_window",
    "cmd_flow",
    "cmd_live",
    "_capture_memory_lane_surface",
    "_surface_contains_work_summary",
    "_absorb_native_surface_close",
    "cmd_receipt",
    "cmd_watch",
]
