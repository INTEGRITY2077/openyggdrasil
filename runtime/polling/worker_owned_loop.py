from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from runtime.capture.live_compaction_observer import capture_tmux_target
from runtime.capture.auto_compaction_controller import (
    parse_preflight_compression,
    run_auto_compaction_controller_from_vault,
)
from runtime.common.vault_root import resolve_vault_root
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


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append((line_no, row))
    return rows


def _row_id_set(event: dict[str, Any]) -> set[str]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    values = {
        event.get("mail_id"),
        event.get("work_order_id"),
        payload.get("mail_id"),
        payload.get("work_order_id"),
        payload.get("query_mail_id"),
        payload.get("source_mail_id"),
    }
    return {str(value) for value in values if value}


def _matching_mailbox_row(event: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
    ids = _row_id_set(event)
    for line_no, row in reversed(_read_jsonl(MAILBOX / "work_orders.jsonl")):
        row_ids = {
            row.get("mail_id"),
            row.get("work_order_id"),
            row.get("source_mail_id"),
            row.get("query_mail_id"),
        }
        if ids & {str(value) for value in row_ids if value}:
            return line_no, row
    return None, None


def _safe_payload_keys(row: dict[str, Any] | None) -> list[str]:
    payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
    forbidden = {
        "query_text",
        "context_snapshot",
        "answer",
        "support_facts",
        "source_paths",
        "public_summary",
    }
    return sorted(str(key) for key in payload.keys() if str(key) not in forbidden)[:12]


def _mailbox_row_preflight(event: dict[str, Any]) -> dict[str, Any]:
    line_no, row = _matching_mailbox_row(event)
    payload_keys = _safe_payload_keys(row)
    return {
        "resolved": row is not None,
        "mail_id": str((row or {}).get("mail_id") or event.get("mail_id") or "?"),
        "work_order_id": str((row or {}).get("work_order_id") or event.get("work_order_id") or "?"),
        "worker_role": str((row or {}).get("worker_role") or ("memory_saver" if MODE == "produce" else "memory_finder")),
        "line_no": line_no,
        "schema_version": str((row or {}).get("schema_version") or "unknown"),
        "acceptance_gate": str((row or {}).get("acceptance_gate") or "unknown"),
        "payload_keys": payload_keys,
    }


def _worker_owned_native_loop_text(event: dict) -> str:
    """Public start note for worker-owned MS/MF action.

    This surface is intentionally pre-semantic. It proves the worker lane has a
    mailbox row to read before any answer, storage claim, support claim, or
    close decision appears.
    """

    interpretation = _worker_start_interpretation()
    row = _mailbox_row_preflight(event)
    accepted = [
        "mailbox row exists" if row["resolved"] else "mailbox row not resolved yet",
        f"schema={row['schema_version']}",
        f"acceptance_gate={row['acceptance_gate']}",
        f"payload_keys={','.join(row['payload_keys']) or 'none'}",
    ]
    return (
        f"[{role} worker surface | preflight]\n"
        f"mail_id: {row['mail_id']}\n"
        f"work_order_id: {row['work_order_id']}\n"
        f"mailbox_row_resolved: {'yes' if row['resolved'] else 'no'}"
        f"{' line=' + str(row['line_no']) if row['line_no'] else ''}\n"
        f"mission: read the mailbox row as SOT before answering or closing.\n"
        "TODO:\n"
        "1. resolve the active mailbox row\n"
        "2. select a role-scoped TST capability class\n"
        "3. build and run a bounded PTC program\n"
        "4. list accepted and rejected evidence\n"
        "5. close with support_bundle, storage_receipt, or typed_unavailable\n"
        f"chosen action: {interpretation['role_name']} will run the mailbox processor first.\n"
        f"selected capability class: pending after row read ({row['worker_role']})\n"
        "bounded program intent: pending worker-authored PTC program\n"
        "accepted evidence:\n"
        + "".join(f"- {item}\n" for item in accepted)
        + "rejected evidence:\n"
        "- mail arrival banner is not evidence\n"
        "- pane text alone is not storage or recall success\n"
        "- semantic answer material is not accepted before mailbox processing\n"
        "judgment: not_started\n"
        "close decision: pending_worker_execution\n"
        "hard nonclaim: this preflight surface is not a final answer, support bundle, or save receipt"
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
    _append_worker_owned_loop_log(row)
    return paste


def _append_worker_owned_loop_log(row: dict) -> None:
    with open(MAILBOX / "live_worker_owned_loop_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _emit_worker_surface_text(text: str) -> dict:
    print("\n" + "-" * 40, flush=True)
    print(text, flush=True)
    print("-" * 40, flush=True)
    return {"written": True, "status": "printed_to_worker_pane", "stderr": ""}


def _worker_trace_to_hermes_chat() -> bool:
    return os.environ.get("OY_WORKER_TRACE_TO_HERMES", "0") == "1"


def _support_counts(receipt: dict | None) -> tuple[int, int]:
    bundle = receipt.get("bundle") if isinstance(receipt, dict) and isinstance(receipt.get("bundle"), dict) else {}
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    facts = bundle.get("support_facts") or nested.get("support_facts") or []
    paths = bundle.get("source_paths") or nested.get("source_paths") or []
    return (
        len(facts) if isinstance(facts, list) else 0,
        len(paths) if isinstance(paths, list) else 0,
    )


def _safe_cursor_status(receipt: dict | None) -> str:
    bundle = receipt.get("bundle") if isinstance(receipt, dict) and isinstance(receipt.get("bundle"), dict) else {}
    nested = bundle.get("support_bundle") if isinstance(bundle.get("support_bundle"), dict) else {}
    cursor = bundle.get("safe_index_cursor") if isinstance(bundle.get("safe_index_cursor"), dict) else nested.get("safe_index_cursor")
    if not isinstance(cursor, dict):
        return "unknown"
    return f"{cursor.get('status') or 'unknown'} allowed={cursor.get('final_support_allowed')}"


def _candidate_rejection_count(receipt: dict | None) -> int:
    bundle = receipt.get("bundle") if isinstance(receipt, dict) and isinstance(receipt.get("bundle"), dict) else {}
    reranker = bundle.get("candidate_reranker") if isinstance(bundle.get("candidate_reranker"), dict) else {}
    rejected = reranker.get("rejected_hard_gate_reasons") if isinstance(reranker, dict) else []
    return len(rejected) if isinstance(rejected, list) else 0


def _program_hash(supervisor: dict[str, Any]) -> str:
    program = supervisor.get("worker_authored_ptc_program")
    if isinstance(program, dict):
        if program.get("code_hash"):
            return str(program["code_hash"])
        encoded = json.dumps(program, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()
    return "missing"


def _worker_owned_structured_close_text(
    event: dict,
    receipt: dict | None,
    status: str,
    elapsed_ms: int,
    attempts: list[dict],
) -> str:
    row = _mailbox_row_preflight(event)
    summary = _receipt_public_summary_for_event(event, receipt)
    supervisor = _tst_supervisor_for_receipt(receipt)
    program = _worker_program_public(supervisor)
    facts_count, paths_count = _support_counts(receipt)
    judgment = "success" if summary.get("quality") in {"pass", "pass_with_limit"} else "typed_unavailable"
    if MODE == "produce":
        close_decision = "storage_receipt" if judgment == "success" else "typed_unavailable_no_storage_evidence"
        accepted = [
            summary.get("result"),
            f"ptc_program={program['mode']} review={program['review']}",
            f"program_hash={_program_hash(supervisor)}",
        ]
    else:
        close_decision = "support_bundle" if judgment == "success" else "typed_unavailable_no_aligned_support"
        accepted = [
            f"support_facts={facts_count}",
            f"source_paths={paths_count}",
            f"safe_index_cursor={_safe_cursor_status(receipt)}",
            f"ptc_program={program['mode']} review={program['review']}",
            f"program_hash={_program_hash(supervisor)}",
        ]
    rejected = [
        "mail arrival banner",
        "pane text alone",
        f"candidate_hard_gate_rejections={_candidate_rejection_count(receipt)}",
    ]
    if not supervisor:
        rejected.append("fresh worker-authored PTC program missing")
    return (
        f"[{role} worker surface | close]\n"
        f"mail_id: {row['mail_id']}\n"
        f"work_order_id: {row['work_order_id']}\n"
        f"mailbox_row_resolved: {'yes' if row['resolved'] else 'no'}"
        f"{' line=' + str(row['line_no']) if row['line_no'] else ''}\n"
        f"mission: {_short(_mission_text(event), 360)}\n"
        "TODO state:\n"
        f"- mailbox row read: {'pass' if row['resolved'] else 'weak'}\n"
        f"- TST capability selected: {'pass' if supervisor else 'weak'} tools={program['selected_tools']}\n"
        f"- bounded PTC program built: {'pass' if _program_hash(supervisor) != 'missing' else 'weak'}\n"
        f"- execution observation: {program['observation_next']}\n"
        "accepted evidence:\n"
        + "".join(f"- {_short(item, 220)}\n" for item in accepted if item)
        + "rejected evidence:\n"
        + "".join(f"- {_short(item, 220)}\n" for item in rejected)
        + f"judgment: {judgment}\n"
        f"close decision: {close_decision}\n"
        f"elapsed_ms: {elapsed_ms}; attempts={len(attempts)}; receipt_status={status}\n"
        "provider rejudgment: required before answer use\n"
        "hard nonclaim: this surface renders worker-owned receipt evidence; it is not Postman answer material"
    )


def _send_worker_owned_structured_close_surface(
    event: dict,
    receipt: dict | None,
    status: str,
    elapsed_ms: int,
    attempts: list[dict],
) -> dict:
    if os.environ.get("OY_WORKER_STRUCTURED_CLOSE_SURFACE", "1") == "0":
        row = {
            "timestamp": time.time(),
            "mode": "produce" if MODE == "produce" else "consume",
            "role": role,
            "delivery_id": event.get("delivery_id"),
            "mail_id": event.get("mail_id"),
            "phase": "worker_owned_structured_close_surface_blocked",
            "written": False,
            "status": "disabled",
        }
        _append_worker_owned_loop_log(row)
        return row
    prompt = _worker_owned_structured_close_text(event, receipt, status, elapsed_ms, attempts)
    if _worker_trace_to_hermes_chat():
        readiness = _wait_context_card_lane_ready(
            float(os.environ.get("OY_OP_WORKER_OWNED_READY_WAIT_SECONDS", "120"))
        )
        if not readiness.get("ready"):
            row = {
                "written": False,
                "status": "lane_not_ready",
                "evidence": readiness.get("evidence"),
                "phase": "worker_owned_structured_close_surface_blocked",
            }
            _append_worker_owned_loop_log(row)
            return row
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
        "phase": "worker_owned_structured_close_surface",
        "surface_owner": "worker_role_processor",
        "sent": bool(paste.get("written")),
        "written": bool(paste.get("written")),
        "status": paste.get("status"),
        "result_preview": prompt[:600],
        "hard_nonclaim": "structured_surface_is_not_postman_semantic_projection",
    }
    _append_worker_owned_loop_log(row)
    _append_goal_log(row)
    return row


def _worker_owned_receipt_projection_text(
    event: dict,
    receipt: dict | None,
    status: str,
    elapsed_ms: int,
    attempts: list[dict],
) -> str:
    return _worker_owned_structured_close_text(event, receipt, status, elapsed_ms, attempts)


def _send_worker_owned_receipt_projection(
    event: dict,
    receipt: dict | None,
    status: str,
    elapsed_ms: int,
    attempts: list[dict],
) -> dict:
    if os.environ.get("OY_WORKER_OWNED_RECEIPT_PROJECTION", "0") != "1":
        row = {
            "timestamp": time.time(),
            "mode": "produce" if MODE == "produce" else "consume",
            "role": role,
            "delivery_id": event.get("delivery_id"),
            "mail_id": event.get("mail_id"),
            "phase": "worker_owned_receipt_projection_blocked",
            "written": False,
            "status": "disabled_route_only_worker_surface",
            "hard_nonclaim": "worker_result_projection_is_not_live_worker_judgment",
        }
        _append_worker_owned_loop_log(row)
        return row
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
    ok, text, _error = capture_tmux_target(tmux_target, lines=180)
    if not ok:
        return None
    matches = re.findall(r"\bSession:\s*([A-Za-z0-9_-]+)", text)
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
        "Sending after interrupt",
        "brainstorming",
        "ruminating",
        "pondering",
        "mulling",
        "thinking",
        "Preflight compression",
    )
    last_tail = ""
    ready_since = None
    ready_evidence = ""
    while time.time() <= deadline:
        ok, text, error = capture_tmux_target(tmux_target, lines=30)
        last_tail = text[-2000:] if ok else error
        tail_lines = [line for line in last_tail.splitlines() if line.strip()]
        recent = "\n".join(tail_lines[-6:])
        if "Preflight compression" in recent or "Preflight compression" in last_tail:
            _maybe_record_preflight_compaction(last_tail)
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


def _maybe_record_preflight_compaction(pane_tail: str) -> None:
    pressure = parse_preflight_compression(pane_tail)
    event = pressure.get("compaction_event") if isinstance(pressure, dict) else None
    if not isinstance(event, dict):
        return
    observed = event.get("token_estimate") or 0
    threshold = event.get("threshold") or 0
    run_id = "live-precompact-{role}-{digest}".format(
        role=role,
        digest=hashlib.sha256(f"{tmux_target}:{observed}:{threshold}".encode("utf-8")).hexdigest()[:10],
    )
    try:
        result = run_auto_compaction_controller_from_vault(
            vault_root=resolve_vault_root(),
            run_id=run_id,
            preflight_text=pane_tail,
        )
        receipt = result.get("receipt") if isinstance(result, dict) else None
        _append_worker_owned_loop_log(
            {
                "timestamp": time.time(),
                "mode": "produce" if MODE == "produce" else "consume",
                "role": role,
                "tmux_target": tmux_target,
                "phase": "precompact_memento_observer",
                "run_id": run_id,
                "status": result.get("status"),
                "episode_count": result.get("episode_count"),
                "written_memento_ids": result.get("written_memento_ids") or [],
                "actual_compaction_event_proven": bool(
                    isinstance(receipt, dict) and receipt.get("actual_compaction_event_proven") is True
                ),
                "raw_pane_text_included": False,
            }
        )
    except Exception as exc:
        _append_worker_owned_loop_log(
            {
                "timestamp": time.time(),
                "mode": "produce" if MODE == "produce" else "consume",
                "role": role,
                "tmux_target": tmux_target,
                "phase": "precompact_memento_observer",
                "run_id": run_id,
                "status": "failed",
                "error": str(exc)[:240],
                "raw_pane_text_included": False,
            }
        )


__all__ = [
    "_worker_owned_native_loop_text",
    "_send_worker_owned_native_loop",
    "_append_worker_owned_loop_log",
    "_emit_worker_surface_text",
    "_worker_trace_to_hermes_chat",
    "_worker_owned_receipt_projection_text",
    "_send_worker_owned_receipt_projection",
    "_worker_owned_structured_close_text",
    "_send_worker_owned_structured_close_surface",
    "_paste_context_prompt",
    "_extract_session_id_from_tmux",
    "_wait_context_card_lane_ready",
]
