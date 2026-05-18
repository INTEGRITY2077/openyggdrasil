from __future__ import annotations

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
import re
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from admission.decision_contracts import validate_mailbox_support_result
from common.map_identity import build_page_id, build_topic_id
from delivery.support_bundle import validate_support_bundle
from harness_common import utc_now_iso
from retrieval.origin_shortcut_roundtrip import (
    follow_origin_shortcut,
    validate_origin_shortcut_result,
)
from retrieval.pathfinder_contracts import (
    OPENYGGDRASIL_ROOT,
    load_pathfinder_schema,
    validate_pathfinder_bundle,
    validate_pathfinder_retrieval_result,
)
from retrieval.pathfinder_lifecycle import filter_lifecycle_records_for_retrieval
from retrieval.pathfinder_product_route import build_pathfinder_product_route_result


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

def _non_empty_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    rows: list[str] = []
    for value in values:
        text = _non_empty(value)
        if text and text not in rows:
            rows.append(text)
    return rows

def _support_bundle_shortcuts(support_bundle: Mapping[str, Any]) -> dict[str, Any]:
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    pathfinder_source_paths: list[str] = []
    if isinstance(pathfinder_bundle, Mapping):
        pathfinder_source_paths = _non_empty_strings(pathfinder_bundle.get("source_paths"))
    return {
        "canonical_note": _non_empty(support_bundle.get("canonical_note")),
        "provenance_note": _non_empty(support_bundle.get("provenance_note")),
        "source_paths": _non_empty_strings(support_bundle.get("source_paths")),
        "pathfinder_source_paths": pathfinder_source_paths,
    }

def _mailbox_packet_refs(mailbox_support_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in mailbox_support_result.get("mailbox_packet_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        refs.append(
            {
                "message_id": str(ref.get("message_id") or "").strip(),
                "packet_type": str(ref.get("packet_type") or "").strip(),
                "path_hint": _non_empty(ref.get("path_hint")),
            }
        )
    return [ref for ref in refs if ref["message_id"] and ref["packet_type"]]

def _source_refs(mailbox_support_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in mailbox_support_result.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        refs.append(
            {
                "kind": str(ref.get("kind") or "provider_session").strip() or "provider_session",
                "path_hint": str(ref.get("path_hint") or "missing-source-ref").strip() or "missing-source-ref",
                "range_hint": ref.get("range_hint"),
                "symlink_hint": ref.get("symlink_hint"),
                "message_id": ref.get("message_id"),
            }
        )
    return refs or [{"kind": "provider_session", "path_hint": "missing-source-ref"}]

def _has_forwarded_source_ref(source_refs: list[dict[str, Any]]) -> bool:
    for ref in source_refs:
        path_hint = str(ref.get("path_hint") or "").strip()
        if path_hint and path_hint != "missing-source-ref":
            return True
    return False

def _topic_key_from_source_path(path_value: str) -> str | None:
    normalized = path_value.replace("\\", "/")
    match = re.search(r"(?:^|/)queries/(?P<topic_key>[^/]+)\.md$", normalized)
    if match:
        return match.group("topic_key")
    return None

def _first_topic_key_from_shortcuts(shortcuts: Mapping[str, Any]) -> str | None:
    candidate_paths = []
    for key in ("canonical_note", "provenance_note"):
        value = _non_empty(shortcuts.get(key))
        if value:
            candidate_paths.append(value)
    candidate_paths.extend(str(item) for item in shortcuts.get("source_paths") or [])
    candidate_paths.extend(str(item) for item in shortcuts.get("pathfinder_source_paths") or [])
    for path_value in candidate_paths:
        topic_key = _topic_key_from_source_path(path_value)
        if topic_key:
            return topic_key
    return None

def _merged_pathfinder_source_paths(
    *,
    support_bundle: Mapping[str, Any],
    shortcuts: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> list[str]:
    merged: list[str] = []
    for key in ("canonical_note", "provenance_note"):
        value = _non_empty(shortcuts.get(key))
        if value and value not in merged:
            merged.append(value)
    for key in ("source_paths", "pathfinder_source_paths"):
        for value in shortcuts.get(key) or []:
            text = _non_empty(value)
            if text and text not in merged:
                merged.append(text)
    if isinstance(origin_shortcut_result, Mapping):
        resolved_path = _non_empty(origin_shortcut_result.get("resolved_path"))
        if resolved_path and resolved_path not in merged:
            merged.append(resolved_path)
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(pathfinder_bundle, Mapping):
        for value in pathfinder_bundle.get("source_paths") or []:
            text = _non_empty(value)
            if text and text not in merged:
                merged.append(text)
    return merged

def _support_facts_from_mailbox_support(
    *,
    support_bundle: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> list[str]:
    facts = _non_empty_strings(support_bundle.get("facts"))
    pathfinder_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(pathfinder_bundle, Mapping):
        for fact in _non_empty_strings(pathfinder_bundle.get("support_facts")):
            if fact not in facts:
                facts.append(fact)
    if isinstance(origin_shortcut_result, Mapping):
        preview = _non_empty(origin_shortcut_result.get("evidence_preview"))
        if preview and preview not in facts:
            facts.append(preview)
    return facts

def _pathfinder_bundle_from_mailbox_support(
    *,
    support_bundle: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    nested_bundle = support_bundle.get("pathfinder_bundle")
    if isinstance(nested_bundle, Mapping):
        nested = dict(nested_bundle)
        required_keys = set(load_pathfinder_schema().get("required") or [])
        if required_keys <= set(nested):
            validate_pathfinder_bundle(nested)
            return nested

    shortcuts = _support_bundle_shortcuts(support_bundle)
    source_paths = _merged_pathfinder_source_paths(
        support_bundle=support_bundle,
        shortcuts=shortcuts,
        origin_shortcut_result=origin_shortcut_result,
    )
    topic_key = _first_topic_key_from_shortcuts(shortcuts)
    topic_id = build_topic_id(topic_key) if topic_key else None
    page_id = build_page_id(f"queries/{topic_key}.md") if topic_key else None
    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": str(support_bundle["query_text"]),
        "anchor_type": "topic" if topic_id else "none",
        "anchor_id": topic_id,
        "topic_id": topic_id,
        "anchor_title": topic_key.replace("-", " ").title() if topic_key else None,
        "episode_ids": [],
        "claim_ids": [],
        "page_ids": [page_id] if page_id else [],
        "source_paths": source_paths,
        "support_facts": _support_facts_from_mailbox_support(
            support_bundle=support_bundle,
            origin_shortcut_result=origin_shortcut_result,
        ),
        "bundle_mode": "topic-page-recent-origin" if topic_id else "unanchored",
        "generated_at": utc_now_iso(),
    }
    validate_pathfinder_bundle(bundle)
    return bundle

def _pathfinder_retrieval_result(
    *,
    query_text: str,
    status: str,
    stop_reason: str | None,
    source_refs: list[dict[str, Any]],
    mailbox_packet_refs: list[dict[str, Any]],
    support_bundle_shortcuts: Mapping[str, Any],
    origin_shortcut_result: Mapping[str, Any] | None,
    pathfinder_bundle: Mapping[str, Any] | None,
    default_product_route: Mapping[str, Any] | None = None,
    lifecycle_records: list[dict[str, Any]],
    lifecycle_filter_mode: str,
    lifecycle_inactive_records_filtered: int,
    reason_codes: list[str],
) -> dict[str, Any]:
    active_reason_codes = list(reason_codes)
    if lifecycle_inactive_records_filtered:
        active_reason_codes.append("inactive_lifecycle_records_filtered")
    if lifecycle_filter_mode == "historical_including_inactive":
        active_reason_codes.append("historical_lifecycle_requested")
    result = {
        "schema_version": "pathfinder_retrieval_result.v1",
        "retrieval_result_id": uuid.uuid4().hex,
        "query_text": query_text,
        "status": status,
        "stop_reason": stop_reason,
        "source_refs": source_refs,
        "mailbox_packet_refs": mailbox_packet_refs,
        "support_bundle_shortcuts": dict(support_bundle_shortcuts),
        "origin_shortcut_result": dict(origin_shortcut_result) if isinstance(origin_shortcut_result, Mapping) else None,
        "pathfinder_bundle": dict(pathfinder_bundle) if isinstance(pathfinder_bundle, Mapping) else None,
        "default_product_route": (
            dict(default_product_route) if isinstance(default_product_route, Mapping) else None
        ),
        "lifecycle_filter_mode": lifecycle_filter_mode,
        "lifecycle_records": lifecycle_records,
        "lifecycle_inactive_records_filtered": lifecycle_inactive_records_filtered,
        "retrieval_authority": "mailbox_support_and_shortcut_consumption_only",
        "source_ref_authority": "required_forward_only",
        "bypassed_source_refs": False,
        "reason_codes": active_reason_codes,
        "created_at": utc_now_iso(),
    }
    validate_pathfinder_retrieval_result(result)
    return result

def build_pathfinder_retrieval_result(
    *,
    mailbox_support_result: Mapping[str, Any],
    workspace_root: Path | None = None,
    lifecycle_records: Sequence[Mapping[str, Any]] | None = None,
    include_historical_lifecycle: bool = False,
) -> dict[str, Any]:
    """Consume mailbox support without allowing source-less Pathfinder retrieval."""

    lifecycle_filter_mode = "historical_including_inactive" if include_historical_lifecycle else "active_only"
    selected_lifecycle_records, inactive_filtered = filter_lifecycle_records_for_retrieval(
        lifecycle_records,
        include_historical=include_historical_lifecycle,
    )
    source_refs = _source_refs(mailbox_support_result)
    mailbox_refs = _mailbox_packet_refs(mailbox_support_result)
    support_bundle = dict(mailbox_support_result.get("support_bundle") or {})
    shortcuts = _support_bundle_shortcuts(support_bundle) if support_bundle else {
        "canonical_note": None,
        "provenance_note": None,
        "source_paths": [],
        "pathfinder_source_paths": [],
    }
    query_text = str(mailbox_support_result.get("query_text") or support_bundle.get("query_text") or "").strip()
    if not query_text:
        query_text = str(mailbox_support_result.get("signal_id") or "unknown-query")

    try:
        validate_mailbox_support_result(mailbox_support_result)
    except RECOVERABLE_RUNTIME_ERRORS as exc:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=f"mailbox_support_result_invalid:{exc.__class__.__name__}",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["mailbox_support_result_invalid"],
        )

    if mailbox_support_result.get("status") != "completed":
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=str(mailbox_support_result.get("stop_reason") or "mailbox_support_not_completed"),
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["mailbox_support_not_completed"],
        )

    if not support_bundle:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason="support_bundle_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["support_bundle_missing"],
        )

    try:
        validate_support_bundle(support_bundle)
    except RECOVERABLE_RUNTIME_ERRORS as exc:
        return _pathfinder_retrieval_result(
            query_text=query_text,
            status="stopped",
            stop_reason=f"support_bundle_invalid:{exc.__class__.__name__}",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["support_bundle_invalid"],
        )

    if not _has_forwarded_source_ref(source_refs):
        return _pathfinder_retrieval_result(
            query_text=str(support_bundle["query_text"]),
            status="stopped",
            stop_reason="source_ref_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=None,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["source_ref_missing"],
        )

    active_workspace = (workspace_root or OPENYGGDRASIL_ROOT).resolve()
    origin_result = mailbox_support_result.get("origin_shortcut_result")
    if isinstance(origin_result, Mapping):
        origin_result = dict(origin_result)
        validate_origin_shortcut_result(origin_result)
    else:
        origin_result = follow_origin_shortcut(support_bundle, workspace_root=active_workspace)
    if not bool(origin_result.get("exists")):
        return _pathfinder_retrieval_result(
            query_text=str(support_bundle["query_text"]),
            status="stopped",
            stop_reason="origin_shortcut_missing",
            source_refs=source_refs,
            mailbox_packet_refs=mailbox_refs,
            support_bundle_shortcuts=shortcuts,
            origin_shortcut_result=origin_result,
            pathfinder_bundle=None,
            lifecycle_records=selected_lifecycle_records,
            lifecycle_filter_mode=lifecycle_filter_mode,
            lifecycle_inactive_records_filtered=inactive_filtered,
            reason_codes=["origin_shortcut_missing"],
        )

    bundle = _pathfinder_bundle_from_mailbox_support(
        support_bundle=support_bundle,
        origin_shortcut_result=origin_result,
    )
    default_product_route = build_pathfinder_product_route_result(
        query_text=str(support_bundle["query_text"]),
    )
    return _pathfinder_retrieval_result(
        query_text=str(support_bundle["query_text"]),
        status="completed",
        stop_reason=None,
        source_refs=source_refs,
        mailbox_packet_refs=mailbox_refs,
        support_bundle_shortcuts=shortcuts,
        origin_shortcut_result=origin_result,
        pathfinder_bundle=bundle,
        default_product_route=default_product_route,
        lifecycle_records=selected_lifecycle_records,
        lifecycle_filter_mode=lifecycle_filter_mode,
        lifecycle_inactive_records_filtered=inactive_filtered,
        reason_codes=[
            "mailbox_support_consumed",
            "origin_shortcut_resolved",
            "source_refs_forwarded",
            "pathfinder_product_route_default_connected",
        ],
    )
