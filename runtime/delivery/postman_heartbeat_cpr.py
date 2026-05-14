from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from attachments.provider_inbox import inject_session_packet, read_session_inbox
from delivery.consumer_receipt_ingress import build_typed_unavailable, validate_typed_unavailable
from runtime.common.portable_ref import looks_like_local_path
from runtime.common.role_aliases import (
    LIVE_GROUP_ROLE_ALIASES,
    LIVE_GROUP_ROLE_COMMAND_TARGETS,
    LIVE_GROUP_ROLE_DISPLAY_NAMES,
    scrub_live_group_legacy_alias,
)
from harness_common import utc_now_iso


POSTMAN_HEARTBEAT_CPR_SCHEMA_VERSION = "postman_heartbeat_cpr.v1"
POSTMAN_HEARTBEAT_CPR_DELIVERY_SCHEMA_VERSION = "postman_heartbeat_cpr_inbox_delivery.v1"
POSTMAN_CPR_PACKET_TYPE = "worker_brief"
REQUIRED_LIVE_GROUP_ROLES = ("provider", "ms1", "mf1")
REQUIRED_ENGINE_COMPONENTS = ("tmux", "postman_helper", "mailbox", "receipt_registry")
READY_STATES = {"active", "available", "healthy", "ok", "present", "ready", "running"}
ROLE_ALIASES = LIVE_GROUP_ROLE_ALIASES
ROLE_DISPLAY_NAMES = LIVE_GROUP_ROLE_DISPLAY_NAMES
ROLE_COMMAND_TARGETS = LIVE_GROUP_ROLE_COMMAND_TARGETS
FORBIDDEN_TEXT_TOKENS = (
    "---\nname:",
    "```",
    ".skill.md",
    "<instructions>",
    "raw provider transcript",
    "transcript.txt",
)


POSTMAN_ROLE = {
    "display_name": "Postman Heartbeat Coordinator",
    "legacy_internal_role_id": "postman",
    "owns": [
        "heartbeat_cpr",
        "engine_bootstrap_presence_check",
        "postman_helper_mailbox_receipt_health_surface",
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
        raise ValueError("Engine Heartbeat CPR payload contains unsafe provider material")
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


def _surface_safe_detail(role: str, record: Any, allowed_keys: Sequence[str]) -> dict[str, Any]:
    detail = _safe_detail(record, allowed_keys)
    for key in ("session_name", "target"):
        value = detail.get(key)
        if not isinstance(value, str):
            continue
        detail[key] = scrub_live_group_legacy_alias(role, value)
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
            "display_name": ROLE_DISPLAY_NAMES[role],
            "command_target": ROLE_COMMAND_TARGETS[role],
            "ready": ready,
            "status": status,
            "detail": _surface_safe_detail(role, record, ("session_name", "pane_id", "target", "evidence_ref")),
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
    postman_helper_status: Mapping[str, Any] | None,
    mailbox_status: Mapping[str, Any] | None,
    receipt_registry: Mapping[str, Any] | None,
) -> Any:
    if component == "postman_helper" and postman_helper_status is not None:
        return postman_helper_status
    if component == "mailbox" and mailbox_status is not None:
        return mailbox_status
    if component == "receipt_registry" and receipt_registry is not None:
        return receipt_registry
    return engine_status.get(component)


def _engine_bootstrap_report(
    *,
    engine_status: Mapping[str, Any] | None,
    postman_helper_status: Mapping[str, Any] | None,
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
            postman_helper_status=postman_helper_status,
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
        if isinstance(value, Mapping):
            path_text = _clean_string(value.get("path"), max_length=512).replace("\\", "/")
            lines = _clean_string(value.get("lines"), max_length=80)
            match = re.search(r"/\.yggdrasil/sessions/([^/]+)/(receipts|query_receipts|work_history)\.jsonl$", path_text)
            if match:
                suffix = f"#L{lines}" if lines else ""
                source_paths.append(f"worker-ledger://{match.group(1)}/{match.group(2)}.jsonl{suffix}")
                continue
        text = _clean_string(value, max_length=512).replace("\\", "/")
        if not text:
            continue
        if looks_like_local_path(text):
            raise ValueError("Engine Heartbeat CPR source_paths must be portable relative pointers")
        source_paths.append(text)
    return _non_empty_strings(source_paths, limit=16)


def _safe_portable_text(value: Any, *, max_length: int = 240) -> str:
    text = _clean_string(value, max_length=max_length).replace("\\", "/")
    if not text or looks_like_local_path(text):
        return ""
    return text


def _safe_portable_strings(values: Iterable[Any], *, limit: int = 16) -> list[str]:
    return _non_empty_strings(
        (_safe_portable_text(value) for value in values),
        limit=limit,
    )


def _typed_unavailable_from(source: Mapping[str, Any]) -> dict[str, Any] | None:
    value = source.get("typed_unavailable")
    if not isinstance(value, Mapping):
        return None
    payload = dict(value)
    if payload.get("schema_version") == "typed_unavailable.v1":
        validate_typed_unavailable(payload)
    return payload


def _safe_hard_nonclaims(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    allowed = (
        "not_grammar_checker",
        "not_kiwi_replacement",
        "not_semantic_quality_proof",
        "not_canonical_text_rewriter",
        "not_es_hangul_code_copied",
    )
    return {key: bool(value.get(key)) for key in allowed if key in value}


def _safe_korean_query_expansion(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    schema_version = _safe_portable_text(value.get("schema_version"))
    if schema_version != "korean_query_expansion.v1":
        return None
    metadata = {
        "schema_version": schema_version,
        "original_query": _safe_portable_text(value.get("original_query")),
        "expansion_status": _safe_portable_text(value.get("expansion_status")),
        "expansion_tokens": _safe_portable_strings(value.get("expansion_tokens") or ()),
        "expansions": _safe_portable_strings(value.get("expansions") or ()),
        "used_as_secondary_signal": bool(value.get("used_as_secondary_signal")),
        "primary_language_analyzer": _safe_portable_text(value.get("primary_language_analyzer")),
        "hard_nonclaims": _safe_hard_nonclaims(value.get("hard_nonclaims")),
    }
    typed_unavailable = _typed_unavailable_from(value)
    if typed_unavailable:
        metadata["typed_unavailable"] = typed_unavailable
    return metadata


def _safe_node_taxonomy(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    schema_version = _safe_portable_text(value.get("schema_version"))
    if schema_version != "wiki_node_taxonomy.v1":
        return None
    return {
        "schema_version": schema_version,
        "continent": _safe_portable_text(value.get("continent")),
        "physical_continent": _safe_portable_text(value.get("physical_continent")),
        "node_type": _safe_portable_text(value.get("node_type")),
        "topography_level": _safe_portable_text(value.get("topography_level")),
        "community_role": _safe_portable_text(value.get("community_role")),
        "classification_source": _safe_portable_text(value.get("classification_source")),
        "taxonomy_status": _safe_portable_text(value.get("taxonomy_status")),
    }


def _safe_recall_digest_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_recall_digest_value(item)
            for key, item in value.items()
            if str(key)
            not in {
                "messages",
                "raw_messages",
                "raw_transcript",
                "session_path",
                "local_path",
                "computed_anchor_hash",
            }
        }
    if isinstance(value, list):
        return [_safe_recall_digest_value(item) for item in value[:12]]
    if isinstance(value, tuple):
        return [_safe_recall_digest_value(item) for item in list(value)[:12]]
    if isinstance(value, str):
        return _safe_portable_text(value, max_length=800)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _safe_portable_text(value, max_length=240)


def _safe_recall_digest(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    schema_version = _safe_portable_text(value.get("schema_version"))
    if schema_version != "recall_digest.v1":
        return None
    metadata = _safe_recall_digest_value(value)
    if not isinstance(metadata, dict):
        return None
    metadata["schema_version"] = schema_version
    metadata["raw_transcript_included"] = False
    metadata["digest_only"] = True
    return metadata


def _korean_query_expansion_from(receipt: Mapping[str, Any], support: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates: list[Any] = [support.get("korean_query_expansion")]
    bundle = receipt.get("bundle")
    if isinstance(bundle, Mapping):
        candidates.append(bundle.get("korean_query_expansion"))
    candidates.append(receipt.get("korean_query_expansion"))
    for candidate in candidates:
        metadata = _safe_korean_query_expansion(candidate)
        if metadata:
            return metadata
    return None


def _support_candidates(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    bundle = receipt.get("bundle")
    if isinstance(bundle, Mapping):
        nested = _mapping_at(
            bundle,
            (
                "support_bundle",
                "ring_support_bundle",
                "recall_support_bundle",
                "pathfinder_bundle",
            ),
        )
        if nested:
            candidates.append(nested)
        if bundle:
            candidates.append(dict(bundle))
    direct = _mapping_at(
        receipt,
        (
            "support_bundle",
            "ring_support_bundle",
            "recall_support_bundle",
            "pathfinder_bundle",
        ),
    )
    if direct:
        candidates.append(direct)
    return candidates


def _support_score(candidate: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    schema = str(candidate.get("schema_version") or "")
    has_ring = int(
        schema == "ring_support_bundle.v1"
        or bool(candidate.get("ring_id"))
        or bool(candidate.get("ring_ids"))
    )
    has_sources = int(bool(candidate.get("source_paths")))
    has_facts = int(bool(candidate.get("support_facts") or candidate.get("facts") or candidate.get("origin_claims")))
    has_topology = int(
        bool(candidate.get("community_edges"))
        or bool(candidate.get("semantic_edges"))
        or bool(candidate.get("origin_locator"))
    )
    is_typed_unavailable = int(bool(candidate.get("typed_unavailable")))
    is_answer_usable = int(bool(has_sources and has_facts and not is_typed_unavailable))
    return is_answer_usable, has_sources, has_facts, has_topology, has_ring


def _select_support(receipt: Mapping[str, Any]) -> dict[str, Any]:
    candidates = _support_candidates(receipt)
    if not candidates:
        return {}
    return max(candidates, key=_support_score)


def _support_fact_texts(support: Mapping[str, Any], receipt: Mapping[str, Any]) -> list[str]:
    direct = support.get("support_facts") or support.get("facts") or receipt.get("support_facts") or receipt.get("facts")
    if direct:
        return _non_empty_strings(direct, limit=12)
    origin_facts: list[str] = []
    for row in support.get("origin_claims") or ():
        if isinstance(row, Mapping):
            origin_facts.append(str(row.get("support_fact") or ""))
    return _non_empty_strings(origin_facts, limit=12)


def _support_metadata(mf1_receipt: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    receipt = dict(mf1_receipt or {})
    support = _select_support(receipt)
    typed_unavailable = _typed_unavailable_from(support) or _typed_unavailable_from(receipt)
    facts = _support_fact_texts(support, receipt)
    source_paths = _safe_source_paths(support.get("source_paths") or receipt.get("source_paths") or ())
    support_status = "available" if source_paths and facts else "typed_unavailable" if typed_unavailable else "missing"
    node_taxonomy = _safe_node_taxonomy(support.get("node_taxonomy"))
    metadata = {
        "status": support_status,
        "support_schema_version": _first_text(support, ("schema_version",)),
        "support_facts": facts,
        "source_paths": source_paths,
        "source_ref": _first_text(support, ("source_ref", "support_bundle_ref", "canonical_note")),
        "community_id": _first_text(support, ("community_id", "ring_id", "topic_id")),
        "node_taxonomy": node_taxonomy,
        "continent": _first_text(support, ("continent",)) or (node_taxonomy or {}).get("continent"),
        "node_type": _first_text(support, ("node_type",)) or (node_taxonomy or {}).get("node_type"),
        "topography_level": _first_text(support, ("topography_level",)) or (node_taxonomy or {}).get("topography_level"),
        "community_role": _first_text(support, ("community_role",)) or (node_taxonomy or {}).get("community_role"),
        "currentness": _first_text(support, ("currentness", "current_authority", "lifecycle_state")),
        "topic_key": _first_text(support, ("topic_key",)),
        "ring_id": _first_text(support, ("ring_id",)),
        "origin_locator": _first_text(support, ("origin_locator",)),
        "provider_session_id": _first_text(support, ("provider_session_id",)),
        "message_index_range": support.get("message_index_range") if isinstance(support.get("message_index_range"), Mapping) else None,
        "source_line_range": support.get("source_line_range") if isinstance(support.get("source_line_range"), Mapping) else None,
        "anchor_hash_present": bool(support.get("anchor_hash")),
        "commit_watermark": _first_text(support, ("commit_watermark",)),
        "origin_claims_count": len(support.get("origin_claims") or []) if isinstance(support.get("origin_claims"), list) else 0,
        "recent_rings_count": len(support.get("recent_rings") or []) if isinstance(support.get("recent_rings"), list) else 0,
        "community_edges_count": len(support.get("community_edges") or []) if isinstance(support.get("community_edges"), list) else 0,
        "semantic_edges_count": len(support.get("semantic_edges") or []) if isinstance(support.get("semantic_edges"), list) else 0,
        "typed_unavailable": typed_unavailable,
    }
    korean_query_expansion = _korean_query_expansion_from(receipt, support)
    if korean_query_expansion:
        metadata["korean_query_expansion"] = korean_query_expansion
    recall_digest = _safe_recall_digest(support.get("recall_digest"))
    if recall_digest:
        metadata["recall_digest"] = recall_digest
    missing: list[str] = []
    if not receipt:
        missing.append("mf1_receipt")
    elif support_status == "missing":
        missing.append("mf1_support_metadata")
    return metadata, missing


def _mailbox_correlation(mf1_receipt: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    receipt = dict(mf1_receipt or {})
    correlation = {
        "mail_id": _first_text(receipt, ("mail_id", "query_mail_id", "source_mail_id", "message_id", "in_reply_to")),
        "delivery_id": _first_text(receipt, ("delivery_id", "postman_delivery_id")),
        "receipt_id": _first_text(receipt, ("receipt_id", "mf1_receipt_id", "consumer_receipt_id")),
        "mf1_query_receipt_id": _first_text(receipt, ("mf1_query_receipt_id", "query_receipt_id", "receipt_id")),
    }
    missing = [key for key, value in correlation.items() if not value and key != "delivery_id"]
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
    mf1_receipt: Mapping[str, Any] | None,
    engine_status: Mapping[str, Any] | None = None,
    postman_helper_status: Mapping[str, Any] | None = None,
    watcher_status: Mapping[str, Any] | None = None,
    mailbox_status: Mapping[str, Any] | None = None,
    receipt_registry: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the Engine Heartbeat CPR handoff for provider current-dialogue use.

    The Postman Heartbeat Coordinator owns liveness, delivery, Result Receipt,
    and inbox handoff surfaces. It does not validate the semantic quality of
    MS1/MF1 memory content.
    """

    generated_at = created_at or utc_now_iso()
    helper_status = postman_helper_status if postman_helper_status is not None else watcher_status
    live_report, live_missing = _live_group_report(dict(live_group))
    engine_report, engine_missing = _engine_bootstrap_report(
        engine_status=engine_status,
        postman_helper_status=helper_status,
        mailbox_status=mailbox_status,
        receipt_registry=receipt_registry,
    )
    correlation, correlation_missing = _mailbox_correlation(mf1_receipt)
    support_metadata, support_missing = _support_metadata(mf1_receipt)
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
        "display_roles": {
            "provider": ROLE_DISPLAY_NAMES["provider"],
            "ms1": ROLE_DISPLAY_NAMES["ms1"],
            "mf1": ROLE_DISPLAY_NAMES["mf1"],
            "delivery": POSTMAN_ROLE["display_name"],
        },
        "memory_worker_roles": {
            "ms1": "structured_long_term_memory_saver",
            "mf1": "evidence_backed_memory_finder",
        },
        "live_group": live_report,
        "engine_bootstrap": engine_report,
        "mailbox_correlation": correlation,
        "mf1_support_metadata": support_metadata,
        "provider_inbox_handoff": {
            "handoff_status": handoff_status,
            "packet_type": POSTMAN_CPR_PACKET_TYPE,
            "manual_prompt_injection_required": False,
            "provider_action": "evaluate_current_dialogue_with_engine_heartbeat_supplied_evidence_metadata",
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
    mf1_receipt: Mapping[str, Any] | None,
    engine_status: Mapping[str, Any] | None = None,
    postman_helper_status: Mapping[str, Any] | None = None,
    watcher_status: Mapping[str, Any] | None = None,
    mailbox_status: Mapping[str, Any] | None = None,
    receipt_registry: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    payload = build_postman_heartbeat_cpr_payload(
        live_group=live_group,
        mf1_receipt=mf1_receipt,
        engine_status=engine_status,
        postman_helper_status=postman_helper_status,
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
