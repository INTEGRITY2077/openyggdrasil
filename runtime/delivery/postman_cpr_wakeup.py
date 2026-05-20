from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.common.role_aliases import LEGACY_MEMORY_FINDER_SUPPORT_METADATA_FIELD
from runtime.common.portable_ref import LOCAL_PATH_RE
from runtime.common.provider_wake_markers import PROVIDER_REJUDGMENT_WAKE_SENTINEL
from runtime.delivery.tmux_lane_adapter import paste_text_enter


PROVIDER_BUSY_MARKERS = (
    "Operation interrupted: waiting for model response",
    "[Interrupted - processing new message]",
    "Interrupted during API call",
    "waiting for model response",
    "processing new message",
)


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _tmux_session_exists(session: str) -> bool:
    return _tmux("has-session", "-t", session).returncode == 0


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return path


def _sanitize(value: object, *, fallback: str = "unknown", max_length: int = 180) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = LOCAL_PATH_RE.sub("[local-ref-redacted]", text)
    return text[:max_length]


def _capture_tmux_pane(session: str, *, lines: int = 80) -> tuple[bool, str]:
    captured = _tmux("capture-pane", "-p", "-t", session, "-S", f"-{lines}")
    if captured.returncode != 0:
        return False, (captured.stderr or captured.stdout or "tmux_capture_failed").strip()
    return True, captured.stdout or ""


def _busy_marker(text: str) -> str | None:
    for marker in PROVIDER_BUSY_MARKERS:
        if marker in text:
            return marker
    return None


def _pane_tail(text: str, *, line_limit: int = 12, char_limit: int = 1200) -> str:
    tail = "\n".join(text.splitlines()[-line_limit:])
    return tail[-char_limit:]


def provider_lane_monitor_summary(monitor: object) -> dict[str, Any]:
    if not isinstance(monitor, dict):
        return {"ready": False, "status": "blocked", "reason_code": "provider_lane_monitor_missing"}
    keys = ("ready", "status", "reason_code", "provider_session", "busy_marker")
    return {key: monitor.get(key) for key in keys if key in monitor}


def _provider_lane_monitor_status(session: str, *, settle_seconds: float) -> dict[str, Any]:
    if not _tmux_session_exists(session):
        return {
            "ready": False,
            "status": "blocked",
            "reason_code": "provider_tmux_lane_missing",
            "provider_session": session,
        }
    first_ok, first_capture = _capture_tmux_pane(session)
    if not first_ok:
        return {
            "ready": False,
            "status": "blocked",
            "reason_code": "provider_lane_capture_failed",
            "provider_session": session,
            "capture_error": first_capture,
        }
    marker = _busy_marker("\n".join(first_capture.splitlines()[-30:]))
    if marker:
        return {
            "ready": False,
            "status": "blocked",
            "reason_code": "provider_lane_busy_or_interrupted",
            "provider_session": session,
            "busy_marker": marker,
            "capture_tail": _pane_tail(first_capture),
        }
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    second_ok, second_capture = _capture_tmux_pane(session)
    if not second_ok:
        return {
            "ready": False,
            "status": "blocked",
            "reason_code": "provider_lane_capture_failed",
            "provider_session": session,
            "capture_error": second_capture,
        }
    if first_capture != second_capture:
        return {
            "ready": False,
            "status": "blocked",
            "reason_code": "provider_lane_unstable_waiting_for_output",
            "provider_session": session,
            "capture_tail": _pane_tail(second_capture),
        }
    return {
        "ready": True,
        "status": "ready",
        "reason_code": "provider_lane_settled",
        "provider_session": session,
        "capture_tail": _pane_tail(second_capture),
    }


def _wait_for_provider_lane_ready(
    session: str,
    *,
    attempts: int | None,
    interval_seconds: float | None,
    settle_seconds: float | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    total_attempts = attempts if attempts is not None else _env_int("OY_PROVIDER_WAKE_MONITOR_ATTEMPTS", 4)
    retry_interval = interval_seconds if interval_seconds is not None else _env_float("OY_PROVIDER_WAKE_MONITOR_INTERVAL_SECONDS", 1.0)
    settle = settle_seconds if settle_seconds is not None else _env_float("OY_PROVIDER_WAKE_MONITOR_SETTLE_SECONDS", 0.75)
    attempts_log: list[dict[str, Any]] = []
    last_monitor: dict[str, Any] = {
        "ready": False,
        "status": "blocked",
        "reason_code": "provider_lane_not_checked",
        "provider_session": session,
    }
    for attempt in range(1, max(1, int(total_attempts)) + 1):
        last_monitor = _provider_lane_monitor_status(session, settle_seconds=max(0.0, float(settle)))
        summary = provider_lane_monitor_summary(last_monitor)
        summary["attempt"] = attempt
        attempts_log.append(summary)
        if last_monitor.get("ready"):
            return last_monitor, attempts_log
        if attempt < total_attempts and retry_interval > 0:
            time.sleep(float(retry_interval))
    return last_monitor, attempts_log


def _support_metadata(result: Mapping[str, Any]) -> dict[str, Any]:
    support = result.get("mf1_support_metadata") or result.get(LEGACY_MEMORY_FINDER_SUPPORT_METADATA_FIELD) or {}
    if not isinstance(support, dict):
        return {}
    normalized = dict(support)
    if "support_facts_count" not in normalized and isinstance(normalized.get("support_facts"), list):
        normalized["support_facts_count"] = len(normalized["support_facts"])
    if "source_paths_count" not in normalized and isinstance(normalized.get("source_paths"), list):
        normalized["source_paths_count"] = len(normalized["source_paths"])
    if "typed_unavailable_present" not in normalized:
        normalized["typed_unavailable_present"] = normalized.get("typed_unavailable") is not None
    return normalized


def _recall_digest_lines(recall_digest: object) -> list[str]:
    if not isinstance(recall_digest, dict) or recall_digest.get("schema_version") != "recall_digest.v1":
        return []
    alignment = recall_digest.get("current_question_alignment")
    alignment_summary = _sanitize(alignment.get("summary"), fallback="") if isinstance(alignment, dict) else ""
    upgrades = recall_digest.get("answer_resolution_upgrade")
    first_upgrade = _sanitize(upgrades[0], fallback="") if isinstance(upgrades, list) and upgrades else ""
    return [
        "",
        "recalled judgment note:",
        f"- past intent: {_sanitize(recall_digest.get('past_user_intent'))}",
        f"- current question alignment: {alignment_summary or 'provider judgment required'}",
        f"- usable boundary: {first_upgrade or 'use recalled boundary before answering'}",
        "- raw source reprint is forbidden",
    ]


def _node_taxonomy_lines(support: Mapping[str, Any]) -> list[str]:
    fields = {
        "continent": _sanitize(support.get("continent"), fallback=""),
        "node_type": _sanitize(support.get("node_type"), fallback=""),
        "topography_level": _sanitize(support.get("topography_level"), fallback=""),
        "community_role": _sanitize(support.get("community_role"), fallback=""),
    }
    if not any(fields.values()):
        return []
    return ["", "memory node taxonomy:"] + [f"- {key}: {value or 'unknown'}" for key, value in fields.items()]


def _build_provider_cpr_wakeup_prompt(result: Mapping[str, Any]) -> str:
    del result
    return (
        f"{PROVIDER_REJUDGMENT_WAKE_SENTINEL} "
        "OpenYggdrasil 보강 결과가 도착했습니다. "
        "방금 답한 내용을 마지막 사용자 질문과 다시 비교하세요. "
        "충분하면 필요한 밀도로만 보강하고, 부족하거나 현재 답을 바꿀 근거가 없으면 그렇게 짧게 닫으세요. "
        "파일 경로, 내부 식별자, 개수 목록은 사용자 답변에 쓰지 마세요."
    )


def _cpr_wakeup_ready(result: Mapping[str, Any]) -> tuple[bool, str]:
    support = _support_metadata(result)
    base_checks = [
        (result.get("status") == "done", "provider_cpr_not_done"),
        (result.get("heartbeat_cpr_status") == "ready", "heartbeat_cpr_not_ready"),
        (result.get("handoff_status") == "ready_for_provider_current_dialogue", "provider_handoff_not_ready"),
        (result.get("manual_prompt_injection_required") is False, "manual_prompt_injection_required"),
        (bool(result.get("message_id")), "cpr_message_id_missing"),
    ]
    for passed, reason_code in base_checks:
        if not passed:
            return False, reason_code
    if support.get("status") == "available":
        checks = [
            (int(support.get("support_facts_count") or 0) > 0, "support_facts_missing"),
            (int(support.get("source_paths_count") or len(support.get("source_paths") or [])) > 0, "source_paths_missing"),
            (support.get("typed_unavailable_present") is False, "typed_unavailable_present"),
        ]
        for passed, reason_code in checks:
            if not passed:
                return False, reason_code
        return True, "ready"
    if (
        support.get("status") == "typed_unavailable"
        or support.get("typed_unavailable_present") is True
        or isinstance(support.get("typed_unavailable"), Mapping)
    ):
        return True, "ready_typed_unavailable"
    return False, "memory_finder_support_unavailable"


def _write_cpr_wakeup_log(result: Mapping[str, Any], wakeup: Mapping[str, Any], *, registry_dir: Path) -> Path:
    return _append_jsonl(
        registry_dir / "postman" / "cpr_wakeups.jsonl",
        {
            "schema_version": "postman_cpr_provider_wakeup.v1",
            "created_at": wakeup.get("created_at"),
            "status": wakeup.get("status"),
            "reason_code": wakeup.get("reason_code"),
            "wakeup_id": wakeup.get("wakeup_id"),
            "provider_session": wakeup.get("provider_session"),
            "message_id": result.get("message_id"),
            "mailbox_correlation": result.get("mailbox_correlation"),
            "scope": wakeup.get("scope"),
            "delivery_mode": wakeup.get("delivery_mode"),
            "provider_context_window_written": wakeup.get("provider_context_window_written"),
            "tmux_injection_attempted": wakeup.get("tmux_injection_attempted"),
            "lane_monitor": provider_lane_monitor_summary(wakeup.get("lane_monitor")),
            "lane_monitor_attempts": wakeup.get("lane_monitor_attempts"),
            "activation_owner": "postman",
            "autonomous_daemon_claimed": False,
            "full_ux_passed": False,
        },
    )


def _write_internal_cpr_heartbeat(result: Mapping[str, Any], wakeup: Mapping[str, Any], *, registry_dir: Path) -> Path:
    return _append_jsonl(
        registry_dir / "postman" / "cpr_internal_heartbeats.jsonl",
        {
            "schema_version": "postman_cpr_provider_internal_heartbeat.v1",
            "created_at": wakeup.get("created_at"),
            "status": wakeup.get("status"),
            "reason_code": wakeup.get("reason_code"),
            "wakeup_id": wakeup.get("wakeup_id"),
            "provider_session": wakeup.get("provider_session"),
            "message_id": result.get("message_id"),
            "mailbox_correlation": result.get("mailbox_correlation"),
            "delivery_mode": "internal_heartbeat",
            "provider_context_window_written": False,
            "tmux_injection_attempted": False,
            "provider_read_required": True,
            "provider_read_contract": "Provider or runtime hook reads Provider-bound CPR state internally before answering.",
            "activation_owner": "postman",
            "autonomous_daemon_claimed": False,
            "full_ux_passed": False,
        },
    )


def wake_provider_with_cpr(
    result: dict[str, Any],
    *,
    registry_dir: Path,
    provider_session: str,
    inject_visible: bool = False,
    wait_attempts: int | None = None,
    wait_interval_seconds: float | None = None,
    settle_seconds: float | None = None,
) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    wakeup_id = f"cprwake-{uuid.uuid4().hex[:8]}"
    ready, reason_code = _cpr_wakeup_ready(result)
    if not ready:
        wakeup = {
            "schema_version": "postman_cpr_provider_wakeup.v1",
            "created_at": created_at,
            "status": "blocked",
            "reason_code": reason_code,
            "wakeup_id": wakeup_id,
            "provider_session": provider_session,
            "scope": "internal_provider_heartbeat_state",
            "delivery_mode": "internal_heartbeat",
            "provider_context_window_written": False,
            "tmux_injection_attempted": False,
            "activation_owner": "postman",
            "autonomous_daemon_claimed": False,
            "full_ux_passed": False,
        }
        wakeup["log_path"] = str(_write_cpr_wakeup_log(result, wakeup, registry_dir=registry_dir))
        return wakeup

    if not inject_visible:
        wakeup = {
            "schema_version": "postman_cpr_provider_wakeup.v1",
            "created_at": created_at,
            "status": "queued",
            "reason_code": "provider_internal_heartbeat_recorded",
            "wakeup_id": wakeup_id,
            "provider_session": provider_session,
            "message_id": result.get("message_id"),
            "scope": "internal_provider_heartbeat_state",
            "delivery_mode": "internal_heartbeat",
            "provider_context_window_written": False,
            "tmux_injection_attempted": False,
            "activation_owner": "postman",
            "autonomous_daemon_claimed": False,
            "full_ux_passed": False,
        }
        wakeup["internal_heartbeat_path"] = str(_write_internal_cpr_heartbeat(result, wakeup, registry_dir=registry_dir))
        wakeup["log_path"] = str(_write_cpr_wakeup_log(result, wakeup, registry_dir=registry_dir))
        return wakeup

    lane_monitor, lane_monitor_attempts = _wait_for_provider_lane_ready(
        provider_session,
        attempts=wait_attempts,
        interval_seconds=wait_interval_seconds,
        settle_seconds=settle_seconds,
    )
    if not lane_monitor.get("ready"):
        wakeup = {
            "schema_version": "postman_cpr_provider_wakeup.v1",
            "created_at": created_at,
            "status": "deferred",
            "reason_code": lane_monitor.get("reason_code", "provider_lane_not_ready"),
            "wakeup_id": wakeup_id,
            "provider_session": provider_session,
            "message_id": result.get("message_id"),
            "scope": "postman_visible_provider_wakeup",
            "delivery_mode": "visible_tmux_injection",
            "provider_context_window_written": False,
            "tmux_injection_attempted": False,
            "lane_monitor": lane_monitor,
            "lane_monitor_attempts": lane_monitor_attempts,
            "activation_owner": "postman",
            "autonomous_daemon_claimed": False,
            "full_ux_passed": False,
        }
        wakeup["log_path"] = str(_write_cpr_wakeup_log(result, wakeup, registry_dir=registry_dir))
        return wakeup

    prompt = _build_provider_cpr_wakeup_prompt(result)
    sent = paste_text_enter(provider_session, prompt, reason="postman_cpr_wakeup")
    wakeup = {
        "schema_version": "postman_cpr_provider_wakeup.v1",
        "created_at": created_at,
        "status": "sent" if sent.returncode == 0 else "blocked",
        "reason_code": "sent" if sent.returncode == 0 else (sent.stderr or sent.stdout or "tmux_lane_adapter_failed").strip(),
        "wakeup_id": wakeup_id,
        "provider_session": provider_session,
        "message_id": result.get("message_id"),
        "prompt_preview": prompt[:360],
        "scope": "postman_visible_provider_wakeup",
        "delivery_mode": "visible_tmux_injection",
        "provider_context_window_written": sent.returncode == 0,
        "tmux_injection_attempted": True,
        "lane_monitor": lane_monitor,
        "lane_monitor_attempts": lane_monitor_attempts,
        "activation_owner": "postman",
        "autonomous_daemon_claimed": False,
        "full_ux_passed": False,
    }
    wakeup["log_path"] = str(_write_cpr_wakeup_log(result, wakeup, registry_dir=registry_dir))
    return wakeup


__all__ = ["provider_lane_monitor_summary", "wake_provider_with_cpr"]
