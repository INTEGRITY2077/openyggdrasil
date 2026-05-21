from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime.cli.ygg_config import (
    PROVIDER_PAIR_SESSION,
    REGISTRY_DIR,
    REPO,
    _provider_id,
    _provider_profile,
    _workflow,
)
from runtime.cli.ygg_registry import (
    _active_pair_from_record,
    _ensure_provider_lane_record_bound,
    _ensure_runtime_path,
    _read_provider_lane_record,
)
from runtime.cli.ygg_tmux import _tmux_session_exists
from runtime.delivery.postman_cpr_wakeup import provider_lane_monitor_summary, wake_provider_with_cpr

def _jsonl_rows(path: Path) -> list[tuple[int, dict]]:
    if not path.exists():
        return []
    rows = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append((idx, json.loads(line)))
        except Exception:
            continue
    return rows

def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _timestamp_value(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _latest_provider_inbox_handoff() -> dict:
    path = REGISTRY_DIR / "sessions" / "provider_inbox.jsonl"
    latest: dict = {}
    for _line, row in _jsonl_rows(path):
        if str(row.get("worker_role") or "") != "memory_finder":
            continue
        if not row.get("mail_id"):
            continue
        if _timestamp_value(row.get("timestamp")) >= _timestamp_value(latest.get("timestamp")):
            latest = row
    latest_receipt = _latest_mf1_query_receipt_handoff()
    if _timestamp_value(latest_receipt.get("timestamp")) > _timestamp_value(latest.get("timestamp")):
        return latest_receipt
    return latest


def _latest_mf1_query_receipt_handoff() -> dict:
    path = REGISTRY_DIR / "sessions" / "MF1" / "query_receipts.jsonl"
    latest: dict = {}
    for _line, receipt in _jsonl_rows(path):
        mail_id = receipt.get("mail_id") or receipt.get("in_reply_to")
        if not mail_id:
            continue
        timestamp = receipt.get("timestamp") or receipt.get("created_at")
        row = {
            "timestamp": timestamp,
            "worker_role": "memory_finder",
            "mail_id": mail_id,
            "receipt_id": receipt.get("receipt_id") or mail_id,
            "status": receipt.get("status"),
            "bundle": receipt.get("bundle") or receipt.get("support_bundle") or {},
            "result_bundle": receipt.get("bundle") or receipt.get("support_bundle") or {},
            "source": "mf1_query_receipts",
        }
        if _timestamp_value(row.get("timestamp")) >= _timestamp_value(latest.get("timestamp")):
            latest = row
    return latest


def _bridge_latest_provider_handoff_to_cpr(record: dict, packets: list[dict]) -> tuple[list[dict], dict]:
    handoff = _latest_provider_inbox_handoff()
    if not handoff:
        return packets, {"status": "not_applicable", "reason_code": "provider_inbox_handoff_missing"}
    latest_packet = packets[-1] if packets else {}
    latest_payload = latest_packet.get("payload") if isinstance(latest_packet, dict) else {}
    latest_correlation = latest_payload.get("mailbox_correlation") if isinstance(latest_payload, dict) else {}
    if (
        isinstance(latest_correlation, dict)
        and latest_correlation.get("mail_id") == handoff.get("mail_id")
    ):
        return packets, {"status": "not_applicable", "reason_code": "cpr_already_current"}
    if packets and _timestamp_value(latest_packet.get("created_at")) >= _timestamp_value(handoff.get("timestamp")):
        return packets, {"status": "not_applicable", "reason_code": "cpr_packet_newer_than_provider_handoff"}
    provider_id = str(record.get("provider_id") or _provider_id())
    provider_profile = str(record.get("provider_profile") or _provider_profile(provider_id))
    provider_session_id = str(record.get("provider_session_id") or "")
    if not provider_session_id:
        return packets, {"status": "blocked", "reason_code": "provider_session_id_missing"}
    try:
        _ensure_runtime_path()
        from delivery.postman_heartbeat_cpr import (  # noqa: PLC0415
            inject_postman_heartbeat_cpr_to_provider_inbox,
            read_postman_heartbeat_cpr_packets,
        )

        delivery = inject_postman_heartbeat_cpr_to_provider_inbox(
            workspace_root=REPO,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            live_group={
                "provider": {"status": "ready", "session_name": provider_session_id},
                "ms1": {"status": "ready", "session_name": "ygg-ms1"},
                "mf1": {"status": "ready", "session_name": "ygg-mf1"},
            },
            engine_status={
                "tmux": {"status": "ready"},
                "postman_helper": {"status": "ready"},
                "mailbox": {"status": "ready"},
                "receipt_registry": {"status": "ready", "receipt_id": handoff.get("receipt_id")},
            },
            mf1_receipt={
                "mail_id": handoff.get("mail_id"),
                "in_reply_to": handoff.get("mail_id"),
                "receipt_id": handoff.get("receipt_id") or handoff.get("mail_id"),
                "status": handoff.get("status"),
                "bundle": handoff.get("bundle") or handoff.get("result_bundle") or {},
                "worker_result_spec": handoff.get("worker_result_spec") or {},
                "provider_rejudgment": handoff.get("provider_rejudgment"),
            },
            created_at=str(handoff.get("timestamp") or ""),
        )
        packets = read_postman_heartbeat_cpr_packets(
            workspace_root=REPO,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
    except Exception as exc:  # noqa: BLE001 - CPR read must still return the last known packet.
        return packets, {"status": "failed", "reason_code": exc.__class__.__name__}
    return packets, {
        "status": delivery.get("delivery_status") or "created",
        "reason_code": "provider_inbox_handoff_bridged",
        "mail_id": handoff.get("mail_id"),
        "message_id": delivery.get("message_id"),
    }


def _provider_cpr_blocked_result(record: dict, *, reason_code: str) -> dict:
    provider_inbox = record.get("provider_inbox") if isinstance(record, dict) else {}
    if not isinstance(provider_inbox, dict):
        provider_inbox = {}
    return {
        "schema_version": "ygg_provider_cpr_inbox_read.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "reason_code": reason_code,
        "provider_id": record.get("provider_id", _provider_id()) if isinstance(record, dict) else _provider_id(),
        "provider_profile": record.get("provider_profile", _provider_profile(_provider_id())) if isinstance(record, dict) else _provider_profile(_provider_id()),
        "provider_session_id": record.get("provider_session_id") if isinstance(record, dict) else None,
        "provider_session_id_source": record.get("provider_session_id_source") if isinstance(record, dict) else None,
        "inbox_path": provider_inbox.get("inbox_path"),
        "hard_nonclaims": {
            "full_ux_passed": False,
            "graphify_full_topology_passed": False,
            "hermes_true_hot_reload_passed": False,
            "readme_scorecard_promotion_allowed": False,
            "postman_semantic_quality_owner": False,
        },
    }


def _support_facts_preview(support_facts: object, *, limit: int = 5, width: int = 360) -> list[str]:
    if not isinstance(support_facts, list):
        return []
    preview: list[str] = []
    for item in support_facts[:limit]:
        if isinstance(item, dict):
            text = item.get("text") or item.get("support_fact") or item.get("fact") or ""
        else:
            text = item
        text = " ".join(str(text).split())
        if not text:
            continue
        if len(text) > width:
            text = text[: width - 1].rstrip() + "…"
        preview.append(text)
    return preview


def _latest_provider_cpr_result(record: dict) -> dict:
    if not record or "unparseable_record" in record:
        return _provider_cpr_blocked_result(record, reason_code="provider_lane_record_unavailable")
    provider_inbox = record.get("provider_inbox")
    if not isinstance(provider_inbox, dict) or provider_inbox.get("status") != "bound":
        return _provider_cpr_blocked_result(record, reason_code="provider_inbox_not_bound")
    provider_id = record.get("provider_id", _provider_id())
    provider_profile = record.get("provider_profile", _provider_profile(provider_id))
    provider_session_id = record.get("provider_session_id")
    if not provider_session_id:
        return _provider_cpr_blocked_result(record, reason_code="provider_session_id_missing")
    try:
        _ensure_runtime_path()
        from delivery.postman_heartbeat_cpr import read_postman_heartbeat_cpr_packets  # noqa: PLC0415

        packets = read_postman_heartbeat_cpr_packets(
            workspace_root=REPO,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
    except Exception as exc:
        result = _provider_cpr_blocked_result(record, reason_code=f"cpr_read_failed:{exc.__class__.__name__}")
        result["error_class"] = exc.__class__.__name__
        return result
    packets, bridge = _bridge_latest_provider_handoff_to_cpr(record, packets)
    if not packets:
        return _provider_cpr_blocked_result(record, reason_code="postman_cpr_packet_missing")

    packet = packets[-1]
    payload = packet.get("payload", {}) if isinstance(packet, dict) else {}
    handoff = payload.get("provider_inbox_handoff", {}) if isinstance(payload, dict) else {}
    support = (
        payload.get("mf1_support_metadata")
        or payload.get("mf1_support_metadata", {})
        if isinstance(payload, dict)
        else {}
    )
    correlation = payload.get("mailbox_correlation", {}) if isinstance(payload, dict) else {}
    hard_nonclaims = payload.get("hard_nonclaims", {}) if isinstance(payload, dict) else {}
    source_paths = support.get("source_paths") if isinstance(support, dict) else []
    support_facts = support.get("support_facts") if isinstance(support, dict) else []
    korean_query_expansion = support.get("korean_query_expansion") if isinstance(support, dict) else None
    recall_digest = support.get("recall_digest") if isinstance(support, dict) else None
    node_taxonomy = support.get("node_taxonomy") if isinstance(support, dict) else None
    provider_rejudgment = support.get("provider_rejudgment") if isinstance(support, dict) else None
    return {
        "schema_version": "ygg_provider_cpr_inbox_read.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "done",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_session_id_source": record.get("provider_session_id_source"),
        "session_uid": record.get("session_uid"),
        "inbox_path": provider_inbox.get("inbox_path"),
        "packet_count": len(packets),
        "message_id": packet.get("message_id"),
        "packet_created_at": packet.get("created_at"),
        "packet_type": packet.get("packet_type"),
        "heartbeat_cpr_status": payload.get("heartbeat_cpr_status") if isinstance(payload, dict) else None,
        "provider_inbox_bridge": bridge,
        "handoff_status": handoff.get("handoff_status") if isinstance(handoff, dict) else None,
        "manual_prompt_injection_required": handoff.get("manual_prompt_injection_required") if isinstance(handoff, dict) else None,
        "mailbox_correlation": {
            "mail_id": correlation.get("mail_id") if isinstance(correlation, dict) else None,
            "delivery_id": correlation.get("delivery_id") if isinstance(correlation, dict) else None,
            "receipt_id": correlation.get("receipt_id") if isinstance(correlation, dict) else None,
            "mf1_query_receipt_id": correlation.get("mf1_query_receipt_id") if isinstance(correlation, dict) else None,
        },
        "mf1_support_metadata": {
            "status": support.get("status") if isinstance(support, dict) else None,
            "support_schema_version": support.get("support_schema_version") if isinstance(support, dict) else None,
            "topic_key": support.get("topic_key") if isinstance(support, dict) else None,
            "ring_id": support.get("ring_id") if isinstance(support, dict) else None,
            "source_paths": source_paths if isinstance(source_paths, list) else [],
            "source_ref": support.get("source_ref") if isinstance(support, dict) else None,
            "community_id": support.get("community_id") if isinstance(support, dict) else None,
            "currentness": support.get("currentness") if isinstance(support, dict) else None,
            "origin_locator": support.get("origin_locator") if isinstance(support, dict) else None,
            "provider_session_id": support.get("provider_session_id") if isinstance(support, dict) else None,
            "message_index_range": support.get("message_index_range") if isinstance(support, dict) else None,
            "source_line_range": support.get("source_line_range") if isinstance(support, dict) else None,
            "anchor_hash_present": support.get("anchor_hash_present") if isinstance(support, dict) else None,
            "commit_watermark": support.get("commit_watermark") if isinstance(support, dict) else None,
            "origin_claims_count": support.get("origin_claims_count") if isinstance(support, dict) else None,
            "recent_rings_count": support.get("recent_rings_count") if isinstance(support, dict) else None,
            "community_edges_count": support.get("community_edges_count") if isinstance(support, dict) else None,
            "semantic_edges_count": support.get("semantic_edges_count") if isinstance(support, dict) else None,
            "support_facts_count": len(support_facts) if isinstance(support_facts, list) else 0,
            "support_facts_preview": _support_facts_preview(support_facts),
            "korean_query_expansion": korean_query_expansion if isinstance(korean_query_expansion, dict) else None,
            "recall_digest": recall_digest if isinstance(recall_digest, dict) else None,
            "provider_rejudgment": provider_rejudgment if isinstance(provider_rejudgment, dict) else None,
            "node_taxonomy": node_taxonomy if isinstance(node_taxonomy, dict) else None,
            "continent": support.get("continent") if isinstance(support, dict) else None,
            "node_type": support.get("node_type") if isinstance(support, dict) else None,
            "topography_level": support.get("topography_level") if isinstance(support, dict) else None,
            "community_role": support.get("community_role") if isinstance(support, dict) else None,
            "typed_unavailable_present": bool(support.get("typed_unavailable")) if isinstance(support, dict) else False,
        },
        "support_facts_preview": _support_facts_preview(support_facts),
        "provider_rejudgment": provider_rejudgment if isinstance(provider_rejudgment, dict) else None,
        "hard_nonclaims": {
            "full_ux_passed": bool(hard_nonclaims.get("full_ux_passed")) if isinstance(hard_nonclaims, dict) else False,
            "graphify_full_topology_passed": bool(hard_nonclaims.get("graphify_full_topology_passed")) if isinstance(hard_nonclaims, dict) else False,
            "hermes_true_hot_reload_passed": bool(hard_nonclaims.get("hermes_true_hot_reload_passed")) if isinstance(hard_nonclaims, dict) else False,
            "readme_scorecard_promotion_allowed": bool(hard_nonclaims.get("readme_scorecard_promotion_allowed")) if isinstance(hard_nonclaims, dict) else False,
            "postman_semantic_quality_owner": bool(hard_nonclaims.get("postman_semantic_quality_owner")) if isinstance(hard_nonclaims, dict) else False,
        },
    }

def _provider_cpr_status_summary_for_op(op: str, reg: dict) -> str | None:
    record = _read_provider_lane_record(PROVIDER_PAIR_SESSION)
    if not record:
        return None
    provider_id = str(record.get("provider_id") or _provider_id())
    active_pair = _active_pair_from_record(record, reg, provider_id)
    if op != active_pair[1]:
        return None
    cpr = _latest_provider_cpr_result(record)
    if cpr.get("status") != "done":
        reason = cpr.get("reason_code") or "unavailable"
        return f"provider_cpr={cpr.get('status', 'blocked')} reason={reason}"
    support = cpr.get("mf1_support_metadata", {})
    correlation = cpr.get("mailbox_correlation", {})
    if not isinstance(support, dict):
        return "provider_cpr=done support=unavailable"
    source_paths = support.get("source_paths") if isinstance(support.get("source_paths"), list) else []
    recall_digest = support.get("recall_digest") if isinstance(support, dict) else None
    recall_status = recall_digest.get("status") if isinstance(recall_digest, dict) else "none"
    provider_rejudgment = support.get("provider_rejudgment") if isinstance(support, dict) else None
    provider_action = provider_rejudgment.get("provider_action") if isinstance(provider_rejudgment, dict) else "none"
    receipt_id = "none"
    if isinstance(correlation, dict):
        receipt_id = correlation.get("mf1_query_receipt_id") or correlation.get("receipt_id") or "none"
    return (
        f"provider_cpr={support.get('status', 'unknown')} "
        f"schema={support.get('support_schema_version') or 'none'} "
        f"receipt={receipt_id} "
        f"recall_digest={recall_status} "
        f"provider_action={provider_action} "
        f"support_facts={support.get('support_facts_count', 0)} "
        f"source_paths={len(source_paths)} "
        f"typed_unavailable={str(bool(support.get('typed_unavailable_present'))).lower()}"
    )

def _print_cpr_workflow(result: dict) -> None:
    support = result.get("mf1_support_metadata")
    if not isinstance(support, dict):
        support = {}
    provider_rejudgment = result.get("provider_rejudgment")
    if not isinstance(provider_rejudgment, dict):
        provider_rejudgment = support.get("provider_rejudgment") if isinstance(support.get("provider_rejudgment"), dict) else {}
    source_paths = support.get("source_paths") if isinstance(support.get("source_paths"), list) else []
    evidence = {
        "provider_session_id": result.get("provider_session_id"),
        "heartbeat_cpr_status": result.get("heartbeat_cpr_status"),
        "handoff_status": result.get("handoff_status"),
        "support_status": support.get("status"),
        "support_schema_version": support.get("support_schema_version"),
        "support_facts_preview": result.get("support_facts_preview") or support.get("support_facts_preview") or [],
        "source_path_count": len(source_paths),
        "node_taxonomy": support.get("node_taxonomy"),
        "provider_action": provider_rejudgment.get("provider_action"),
        "provider_reason_code": provider_rejudgment.get("reason_code"),
        "hard_nonclaims": result.get("hard_nonclaims"),
    }
    _workflow(
        "YGG CPR",
        now="Read internal current-dialogue support card",
        watching=f"session={PROVIDER_PAIR_SESSION}; workspace={REPO}",
        creating="bounded Provider current-dialogue CPR card",
        created=f"status={result.get('status')}; message_id={result.get('message_id') or 'none'}",
        evidence=json.dumps(evidence, ensure_ascii=False)[:1600],
        next_action="Provider may reflect bounded metadata only; no Full UX or topology claim",
        status=result.get("status", "blocked"),
    )

def _wake_provider_with_cpr(
    result: dict,
    *,
    inject_visible: bool = False,
    wait_attempts: int | None = None,
    wait_interval_seconds: float | None = None,
    settle_seconds: float | None = None,
) -> dict:
    """Facade for the Postman-owned private CPR wakeup adapter."""
    return wake_provider_with_cpr(
        result,
        registry_dir=REGISTRY_DIR,
        provider_session=PROVIDER_PAIR_SESSION,
        inject_visible=inject_visible,
        wait_attempts=wait_attempts,
        wait_interval_seconds=wait_interval_seconds,
        settle_seconds=settle_seconds,
    )

def _print_cpr_wakeup_workflow(wakeup: dict) -> None:
    _workflow(
        "YGG CPR WAKE",
        now="Record internal Provider heartbeat only",
        watching=f"session={PROVIDER_PAIR_SESSION}; wakeup_id={wakeup.get('wakeup_id')}",
        creating="side-channel state for runtime hook; no Provider pane text",
        created=f"status={wakeup.get('status')}; reason={wakeup.get('reason_code')}",
        evidence=json.dumps(
            {
                "message_id": wakeup.get("message_id"),
                "scope": wakeup.get("scope"),
                "delivery_mode": wakeup.get("delivery_mode"),
                "provider_context_window_written": wakeup.get("provider_context_window_written"),
                "tmux_injection_attempted": wakeup.get("tmux_injection_attempted"),
                "internal_heartbeat_path": wakeup.get("internal_heartbeat_path"),
                "lane_monitor": provider_lane_monitor_summary(wakeup.get("lane_monitor")),
                "lane_monitor_attempts": wakeup.get("lane_monitor_attempts"),
                "deferred_queue_path": wakeup.get("deferred_queue_path"),
                "log_path": wakeup.get("log_path"),
                "autonomous_daemon_claimed": wakeup.get("autonomous_daemon_claimed"),
                "full_ux_passed": wakeup.get("full_ux_passed"),
            },
            ensure_ascii=False,
        ),
        next_action="Provider pane must remain user/provider dialogue only",
        status=wakeup.get("status", "blocked"),
    )

def cmd_cpr(args: list[str]) -> None:
    allowed_args = {"--json", "--wake-provider"}
    if any(arg not in allowed_args for arg in args) or len(args) != len(set(args)):
        print("Usage: ygg cpr [--json] [--wake-provider]")
        sys.exit(1)
    json_mode = "--json" in args
    wake_mode = "--wake-provider" in args
    inject_visible = False
    session = PROVIDER_PAIR_SESSION
    if not _tmux_session_exists(session):
        result = _provider_cpr_blocked_result(_read_provider_lane_record(session), reason_code="provider_tmux_lane_missing")
    else:
        record = _ensure_provider_lane_record_bound(session, event="provider_cpr_read_binding_repaired")
        result = _latest_provider_cpr_result(record)
    if wake_mode:
        result["provider_wakeup"] = _wake_provider_with_cpr(result, inject_visible=inject_visible)
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_cpr_workflow(result)
        if wake_mode:
            _print_cpr_wakeup_workflow(result["provider_wakeup"])


__all__ = [
    "_jsonl_rows",
    "_append_jsonl",
    "_provider_cpr_blocked_result",
    "_latest_provider_cpr_result",
    "_provider_cpr_status_summary_for_op",
    "_print_cpr_workflow",
    "_wake_provider_with_cpr",
    "_print_cpr_wakeup_workflow",
    "cmd_cpr",
]
