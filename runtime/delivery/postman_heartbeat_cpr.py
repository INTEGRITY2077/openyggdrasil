from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from attachments.provider_inbox import inject_session_packet, read_session_inbox
from delivery.consumer_receipt_ingress import build_typed_unavailable, validate_typed_unavailable
from harness_common import utc_now_iso


POSTMAN_HEARTBEAT_CPR_SCHEMA_VERSION = "postman_heartbeat_cpr.v1"
POSTMAN_HEARTBEAT_CPR_DELIVERY_SCHEMA_VERSION = "postman_heartbeat_cpr_inbox_delivery.v1"
POSTMAN_CPR_PACKET_TYPE = "operator_brief"
REQUIRED_LIVE_GROUP_ROLES = ("provider", "op1", "op2")
REQUIRED_ENGINE_COMPONENTS = ("tmux", "watcher", "mailbox", "receipt_registry")
READY_STATES = {"active", "available", "healthy", "ok", "present", "ready", "running"}
ROLE_ALIASES = {
    "provider": ("provider", "pro1", "ygg-pro1", "hermes"),
    "op1": ("op1", "producer", "ygg-op1"),
    "op2": ("op2", "consumer", "ygg-op2"),
}
FORBIDDEN_TEXT_TOKENS = (
    "---\nname:",
    "```",
    ".skill.md",
    "<instructions>",
    "raw provider transcript",
    "transcript.txt",
)
LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|file://|/[A-Za-z0-9_.-])")


POSTMAN_ROLE = {
    "owns": [
        "heartbeat_cpr",
        "engine_bootstrap_presence_check",
        "watcher_mailbox_receipt_health_surface",
        "delivery_receipt_correlation",
        "provider_inbox_handoff",
    ],
    "does_not_own": [
        "semantic_quality",
        "support_fact_truth",
        "graphify_topology_completion",
        "provider_final_judgment",
        "readme_scorecard_promotion",
    ],
}
HARD_NONCLAIMS = {
    "hermes_true_hot_reload_passed": False,
    "full_ux_passed": False,
    "graphify_full_topology_passed": False,
    "readme_scorecard_promotion_allowed": False,
    "production_ready": False,
    "multi_provider_parity": False,
    "postman_semantic_quality_owner": False,
}


def _clean_string(value: Any, *, max_length: int = 600) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower().replace("\\", "/")
    if any(token.lower().replace("\\", "/") in lowered for token in FORBIDDEN_TEXT_TOKENS):
        raise ValueError("Postman CPR payload contains unsafe provider material")
    return text[:max_length]


def _non_empty_strings(values: Iterable[Any], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_string(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _first_text(source: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = _clean_string(value)
        if text:
            return text
    return None


def _mapping_at(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _status_ready(record: Any) -> tuple[bool, str]:
    if record is True:
        return True, "ready"
    if record is False or record is None:
        return False, "missing"
    if isinstance(record, str):
        status = _clean_string(record).lower()
        return status in READY_STATES, status or "missing"
    if isinstance(record, Mapping):
        if record.get("ready") is True or record.get("present") is True:
            return True, _clean_string(record.get("status") or "ready").lower()
        if record.get("ready") is False or record.get("present") is False:
            return False, _clean_string(record.get("status") or "missing").lower()
        status = _clean_string(record.get("status") or record.get("state") or "").lower()
        if status:
            return status in READY_STATES, status
        if record:
            return True, "ready"
    return False, "missing"


def _safe_detail(record: Any, allowed_keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {}
    detail: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            detail[key] = _clean_string(value) if isinstance(value, str) else value
    return detail


def _live_role_record(live_group: Mapping[str, Any], role: str) -> Any:
    for alias in ROLE_ALIASES[role]:
        if alias in live_group:
            return live_group[alias]
    return None


def _live_group_report(live_group: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    roles: dict[str, Any] = {}
    missing: list[str] = []
    for role in REQUIRED_LIVE_GROUP_ROLES:
        record = _live_role_record(live_group, role)
        ready, status = _status_ready(record)
        roles[role] = {
            "ready": ready,
            "status": status,
            "detail": _safe_detail(record, ("session_name", "pane_id", "target", "evidence_ref")),
        }
        if not ready:
            missing.append(f"live_group_{role}")
    return {
        "required_roles": list(REQUIRED_LIVE_GROUP_ROLES),
        "ready": not missing,
        "roles": roles,
    }, missing


def _component_record(
    component: str,
    *,
    engine_status: Mapping[str, Any],
    watcher_status: Mapping[str, Any] | None,
    mailbox_status: Mapping[str, Any] | None,
    receipt_registry: Mapping[str, Any] | None,
) -> Any:
    if component == "watcher" and watcher_status is not None:
        return watcher_status
    if component == "mailbox" and mailbox_status is not None:
        return mailbox_status
    if component == "receipt_registry" and receipt_registry is not None:
        return receipt_registry
    return engine_status.get(component)


def _engine_bootstrap_report(
    *,
    engine_status: Mapping[str, Any] | None,
    watcher_status: Mapping[str, Any] | None,
    mailbox_status: Mapping[str, Any] | None,
    receipt_registry: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    status_source = dict(engine_status or {})
    components: dict[str, Any] = {}
    missing: list[str] = []
    for component in REQUIRED_ENGINE_COMPONENTS:
        record = _component_record(
            component,
            engine_status=status_source,
            watcher_status=watcher_status,
            mailbox_status=mailbox_status,
            receipt_registry=receipt_registry,
        )
        ready, status = _status_ready(record)
        components[component] = {
            "ready": ready,
            "status": status,
            "detail": _safe_detail(
                record,
                ("namespace", "consumer", "event_type", "message_id", "receipt_id", "evidence_ref"),
            ),
        }
        if not ready:
            missing.append(f"engine_{component}")
    return {
        "required_components": list(REQUIRED_ENGINE_COMPONENTS),
        "ready": not missing,
        "components": components,
        "restart_action": "not_required" if not missing else "typed_unavailable",
    }, missing


def _safe_source_paths(values: Iterable[Any]) -> list[str]:
    source_paths: list[str] = []
    for value in values:
        text = _clean_string(value, max_length=512).replace("\\", "/")
        if not text:
            continue
        if LOCAL_PATH_RE.match(text):
            raise ValueError("Postman CPR source_paths must be portable relative pointers")
        source_paths.append(text)
    return _non_empty_strings(source_paths, limit=16)


def _typed_unavailable_from(source: Mapping[str, Any]) -> dict[str, Any] | None:
    value = source.get("typed_unavailable")
    if not isinstance(value, Mapping):
        return None
    payload = dict(value)
    if payload.get("schema_version") == "typed_unavailable.v1":
        validate_typed_unavailable(payload)
    return payload


def _support_metadata(op2_receipt: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    receipt = dict(op2_receipt or {})
    support = _mapping_at(
        receipt,
        (
            "support_bundle",
            "ring_support_bundle",
            "recall_support_bundle",
            "pathfinder_bundle",
        ),
    )
    typed_unavailable = _typed_unavailable_from(support) or _typed_unavailable_from(receipt)
    facts = _non_empty_strings(
        support.get("support_facts")
        or support.get("facts")
        or receipt.get("support_facts")
        or receipt.get("facts")
        or (),
        limit=12,
    )
    source_paths = _safe_source_paths(support.get("source_paths") or receipt.get("source_paths") or ())
    support_status = "available" if source_paths and facts else "typed_unavailable" if typed_unavailable else "missing"
    metadata = {
        "status": support_status,
        "support_facts": facts,
        "source_paths": source_paths,
        "source_ref": _first_text(support, ("source_ref", "support_bundle_ref", "canonical_note")),
        "community_id": _first_text(support, ("community_id", "ring_id", "topic_id")),
        "currentness": _first_text(support, ("currentness", "current_authority", "lifecycle_state")),
        "typed_unavailable": typed_unavailable,
    }
    missing: list[str] = []
    if not receipt:
        missing.append("op2_receipt")
    elif support_status == "missing":
        missing.append("op2_support_metadata")
    return metadata, missing


def _mailbox_correlation(op2_receipt: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    receipt = dict(op2_receipt or {})
    correlation = {
        "mail_id": _first_text(receipt, ("mail_id", "query_mail_id", "source_mail_id", "message_id")),
        "delivery_id": _first_text(receipt, ("delivery_id", "postman_delivery_id")),
        "receipt_id": _first_text(receipt, ("receipt_id", "op2_receipt_id", "consumer_receipt_id")),
        "op2_query_receipt_id": _first_text(receipt, ("op2_query_receipt_id", "query_receipt_id")),
    }
    missing = [key for key, value in correlation.items() if not value]
    return correlation, [f"correlation_{key}" for key in missing]


def _unavailable_for_missing(missing_refs: Sequence[str], *, created_at: str) -> dict[str, Any]:
    payload = build_typed_unavailable(
        reason_code="unresolved_evidence_ref",
        blocked_stage="evidence_resolution",
        created_at=created_at,
        unavailable_ref="typed-unavailable-ref://openyggdrasil/postman-heartbeat-cpr/unavailable",
        missing_or_rejected_refs=[
            {
                "ref": f"postman-cpr-ref://openyggdrasil/missing/{_clean_string(ref)}",
                "reason_code": "unresolved_evidence_ref",
                "rejection_kind": "missing",
            }
            for ref in missing_refs
        ],
    )
    validate_typed_unavailable(payload)
    return payload


def build_postman_heartbeat_cpr_payload(
    *,
    live_group: Mapping[str, Any],
    op2_receipt: Mapping[str, Any] | None,
    engine_status: Mapping[str, Any] | None = None,
    watcher_status: Mapping[str, Any] | None = None,
    mailbox_status: Mapping[str, Any] | None = None,
    receipt_registry: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the Postman-owned CPR handoff for provider current-dialogue use.

    Postman owns the liveness, delivery, receipt, and inbox handoff surface. It
    does not validate the semantic quality of OP1/OP2 memory content.
    """

    generated_at = created_at or utc_now_iso()
    live_report, live_missing = _live_group_report(dict(live_group))
    engine_report, engine_missing = _engine_bootstrap_report(
        engine_status=engine_status,
        watcher_status=watcher_status,
        mailbox_status=mailbox_status,
        receipt_registry=receipt_registry,
    )
    correlation, correlation_missing = _mailbox_correlation(op2_receipt)
    support_metadata, support_missing = _support_metadata(op2_receipt)
    missing = live_missing + engine_missing + correlation_missing + support_missing
    typed_unavailable = _unavailable_for_missing(missing, created_at=generated_at) if missing else None
    status = "typed_unavailable" if typed_unavailable else "ready"
    handoff_status = (
        "blocked_typed_unavailable"
        if typed_unavailable
        else "ready_for_provider_current_dialogue"
    )
    return {
        "schema_version": POSTMAN_HEARTBEAT_CPR_SCHEMA_VERSION,
        "created_at": generated_at,
        "heartbeat_cpr_status": status,
        "postman_role": dict(POSTMAN_ROLE),
        "provider_role": "current_dialogue_judgment_owner",
        "operator_roles": {
            "op1": "structured_long_term_memory_supplier",
            "op2": "evidence_backed_support_bundle_supplier",
        },
        "live_group": live_report,
        "engine_bootstrap": engine_report,
        "mailbox_correlation": correlation,
        "op2_support_metadata": support_metadata,
        "provider_inbox_handoff": {
            "handoff_status": handoff_status,
            "packet_type": POSTMAN_CPR_PACKET_TYPE,
            "manual_prompt_injection_required": False,
            "provider_action": "evaluate_current_dialogue_with_postman_supplied_evidence_metadata",
            "completion_claim": "handoff_only",
        },
        "typed_unavailable": typed_unavailable,
        "hard_nonclaims": dict(HARD_NONCLAIMS),
    }


def inject_postman_heartbeat_cpr_to_provider_inbox(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    live_group: Mapping[str, Any],
    op2_receipt: Mapping[str, Any] | None,
    engine_status: Mapping[str, Any] | None = None,
    watcher_status: Mapping[str, Any] | None = None,
    mailbox_status: Mapping[str, Any] | None = None,
    receipt_registry: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    payload = build_postman_heartbeat_cpr_payload(
        live_group=live_group,
        op2_receipt=op2_receipt,
        engine_status=engine_status,
        watcher_status=watcher_status,
        mailbox_status=mailbox_status,
        receipt_registry=receipt_registry,
        created_at=created_at,
    )
    packet = inject_session_packet(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        packet_type=POSTMAN_CPR_PACKET_TYPE,
        payload=payload,
    )
    return {
        "schema_version": POSTMAN_HEARTBEAT_CPR_DELIVERY_SCHEMA_VERSION,
        "created_at": packet["created_at"],
        "delivery_status": "created",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "message_id": packet["message_id"],
        "packet": packet,
        "payload": payload,
    }


def read_postman_heartbeat_cpr_packets(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in read_session_inbox(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
        if row.get("packet_type") == POSTMAN_CPR_PACKET_TYPE
        and isinstance(row.get("payload"), Mapping)
        and row["payload"].get("schema_version") == POSTMAN_HEARTBEAT_CPR_SCHEMA_VERSION
    ]


__all__ = [
    "POSTMAN_HEARTBEAT_CPR_SCHEMA_VERSION",
    "POSTMAN_CPR_PACKET_TYPE",
    "build_postman_heartbeat_cpr_payload",
    "inject_postman_heartbeat_cpr_to_provider_inbox",
    "read_postman_heartbeat_cpr_packets",
]
