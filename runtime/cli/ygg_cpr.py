from __future__ import annotations

from runtime.cli.ygg_config import *  # noqa: F401,F403
from runtime.cli.ygg_tmux import *  # noqa: F401,F403
from runtime.cli.ygg_registry import *  # noqa: F401,F403

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
    if not packets:
        return _provider_cpr_blocked_result(record, reason_code="postman_cpr_packet_missing")

    packet = packets[-1]
    payload = packet.get("payload", {}) if isinstance(packet, dict) else {}
    handoff = payload.get("provider_inbox_handoff", {}) if isinstance(payload, dict) else {}
    support = (
        payload.get("mf1_support_metadata")
        or payload.get("op2_support_metadata", {})
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
        "handoff_status": handoff.get("handoff_status") if isinstance(handoff, dict) else None,
        "manual_prompt_injection_required": handoff.get("manual_prompt_injection_required") if isinstance(handoff, dict) else None,
        "mailbox_correlation": {
            "mail_id": correlation.get("mail_id") if isinstance(correlation, dict) else None,
            "delivery_id": correlation.get("delivery_id") if isinstance(correlation, dict) else None,
            "receipt_id": correlation.get("receipt_id") if isinstance(correlation, dict) else None,
            "op2_query_receipt_id": correlation.get("op2_query_receipt_id") if isinstance(correlation, dict) else None,
        },
        "op2_support_metadata": {
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
            "korean_query_expansion": korean_query_expansion if isinstance(korean_query_expansion, dict) else None,
            "recall_digest": recall_digest if isinstance(recall_digest, dict) else None,
            "node_taxonomy": node_taxonomy if isinstance(node_taxonomy, dict) else None,
            "continent": support.get("continent") if isinstance(support, dict) else None,
            "node_type": support.get("node_type") if isinstance(support, dict) else None,
            "topography_level": support.get("topography_level") if isinstance(support, dict) else None,
            "community_role": support.get("community_role") if isinstance(support, dict) else None,
            "typed_unavailable_present": bool(support.get("typed_unavailable")) if isinstance(support, dict) else False,
        },
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
    support = cpr.get("op2_support_metadata", {})
    correlation = cpr.get("mailbox_correlation", {})
    if not isinstance(support, dict):
        return "provider_cpr=done support=unavailable"
    source_paths = support.get("source_paths") if isinstance(support.get("source_paths"), list) else []
    recall_digest = support.get("recall_digest") if isinstance(support, dict) else None
    recall_status = recall_digest.get("status") if isinstance(recall_digest, dict) else "none"
    receipt_id = "none"
    if isinstance(correlation, dict):
        receipt_id = correlation.get("op2_query_receipt_id") or correlation.get("receipt_id") or "none"
    return (
        f"provider_cpr={support.get('status', 'unknown')} "
        f"schema={support.get('support_schema_version') or 'none'} "
        f"receipt={receipt_id} "
        f"recall_digest={recall_status} "
        f"support_facts={support.get('support_facts_count', 0)} "
        f"source_paths={len(source_paths)} "
        f"typed_unavailable={str(bool(support.get('typed_unavailable_present'))).lower()}"
    )

def _print_cpr_workflow(result: dict) -> None:
    evidence_keys = [
        "provider_session_id",
        "provider_session_id_source",
        "inbox_path",
        "message_id",
        "heartbeat_cpr_status",
        "handoff_status",
        "mailbox_correlation",
        "op2_support_metadata",
        "hard_nonclaims",
        "reason_code",
    ]
    evidence = {key: result.get(key) for key in evidence_keys if key in result}
    _workflow(
        "YGG CPR",
        now="Read Provider-bound Postman heartbeat CPR packet",
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
        now="Send one bounded letter wake-up into Provider Lane 1",
        watching=f"session={PROVIDER_PAIR_SESSION}; wakeup_id={wakeup.get('wakeup_id')}",
        creating="natural Provider continuation prompt without local paths or internal commands",
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
        next_action="Capture Provider same-turn CPR read before making any UX claim",
        status=wakeup.get("status", "blocked"),
    )

def cmd_cpr(args: list[str]) -> None:
    allowed_args = {"--json", "--wake-provider", "--inject-visible"}
    if any(arg not in allowed_args for arg in args) or len(args) != len(set(args)):
        print("Usage: ygg cpr [--json] [--wake-provider] [--inject-visible]")
        sys.exit(1)
    json_mode = "--json" in args
    wake_mode = "--wake-provider" in args
    inject_visible = "--inject-visible" in args
    if inject_visible and not wake_mode:
        print("Usage: ygg cpr [--json] --wake-provider [--inject-visible]")
        sys.exit(1)
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
