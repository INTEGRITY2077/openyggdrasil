from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from admission.decision_contracts import validate_mailbox_support_result
from delivery.support_bundle import validate_support_bundle
from harness_common import utc_now_iso
from retrieval.graph_output_guard import build_graph_output_guard_result, validate_graph_output_guard_result
from retrieval.graphify_snapshot_manifest import validate_graphify_snapshot_manifest
from retrieval.origin_shortcut_roundtrip import (
    follow_origin_shortcut,
    validate_origin_shortcut_result,
)
from retrieval.pathfinder import validate_pathfinder_bundle


SCHEMA_VERSION = "graph_query_support_bundle_result.v1"
SOURCE_ROLE = "derived_graph_query_support_bundle"
CANONICALITY = "non_sot"
MAX_SUPPORT_FACTS = 5
MAX_FACT_CHARS = 240
MAX_SOURCE_PATHS = 8
MAILBOX_SOURCE_REF_KINDS = {
    "provider_session",
    "provider_session_source_ref",
    "provenance",
    "mailbox_packet",
    "support_bundle",
}


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _bounded_text(text: str, *, limit: int = MAX_FACT_CHARS) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _unique_texts(values: Sequence[Any], *, limit: int) -> list[str]:
    rows: list[str] = []
    for value in values:
        text = _non_empty(value)
        if not text:
            continue
        bounded = _bounded_text(text)
        if bounded not in rows:
            rows.append(bounded)
        if len(rows) >= limit:
            break
    return rows


def _workspace_relative(path_value: str, *, workspace_root: Path | None) -> str:
    normalized = str(path_value).replace("\\", "/")
    if workspace_root is None:
        return normalized
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except Exception:
        return normalized


def _normalize_source_refs(source_refs: Sequence[Mapping[str, Any] | str] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for source_ref in source_refs or []:
        if isinstance(source_ref, Mapping):
            path_hint = _non_empty(
                source_ref.get("path_hint")
                or source_ref.get("path")
                or source_ref.get("ref")
                or source_ref.get("resolved_path")
            )
            if not path_hint:
                continue
            raw_kind = str(source_ref.get("kind") or "source_ref").strip() or "source_ref"
            kind = raw_kind if raw_kind in MAILBOX_SOURCE_REF_KINDS else "support_bundle"
            refs.append(
                {
                    "kind": kind,
                    "path_hint": path_hint,
                    "range_hint": source_ref.get("range_hint"),
                    "symlink_hint": source_ref.get("symlink_hint"),
                    "message_id": source_ref.get("message_id"),
                }
            )
        else:
            text = _non_empty(source_ref)
            if text:
                refs.append(
                    {
                        "kind": "support_bundle",
                        "path_hint": text,
                        "range_hint": None,
                        "symlink_hint": None,
                        "message_id": None,
                    }
                )
    return refs


def _source_paths(
    *,
    source_refs: Sequence[Mapping[str, Any] | str] | None,
    origin_shortcut: Mapping[str, Any] | None,
    workspace_root: Path | None,
) -> list[str]:
    rows: list[str] = []
    for ref in _normalize_source_refs(source_refs):
        path_hint = _non_empty(ref.get("path_hint"))
        if path_hint:
            rows.append(_workspace_relative(path_hint, workspace_root=workspace_root))
    if isinstance(origin_shortcut, Mapping):
        for key in ("resolved_path", "shortcut_path"):
            path_hint = _non_empty(origin_shortcut.get(key))
            if path_hint:
                rows.append(_workspace_relative(path_hint, workspace_root=workspace_root))
    return _unique_texts(rows, limit=MAX_SOURCE_PATHS)


def _source_ref_token(source_refs: Sequence[Mapping[str, Any] | str] | None) -> str | None:
    refs = _normalize_source_refs(source_refs)
    if not refs:
        return None
    first = refs[0]
    token = f"{first['kind']}:{first['path_hint']}"
    range_hint = _non_empty(first.get("range_hint"))
    return f"{token}#{range_hint}" if range_hint else token


def _first_matching_path(source_paths: Sequence[str], *, prefixes: tuple[str, ...]) -> str | None:
    for path in source_paths:
        lowered = path.lower().replace("\\", "/")
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return path
    return None


def _graph_facts(graph_result: Mapping[str, Any]) -> list[str]:
    facts: list[Any] = []
    facts.extend(graph_result.get("facts") or [])
    summary = graph_result.get("summary")
    if isinstance(summary, Mapping):
        counts = []
        for key in ("nodes", "edges", "communities"):
            if key in summary:
                counts.append(f"{key}={summary[key]}")
        if counts:
            facts.append("Derived graph summary: " + ", ".join(counts))
    for key in ("human_summary", "summary_text", "query_text", "query"):
        value = _non_empty(graph_result.get(key))
        if value:
            facts.append(value)
    facts.append("Graph output is a derived navigation hint only and requires SOT/provenance verification.")
    return _unique_texts(facts, limit=MAX_SUPPORT_FACTS)


def _freshness_for_support_bundle(guard_result: Mapping[str, Any]) -> dict[str, Any]:
    freshness = guard_result.get("freshness")
    if not isinstance(freshness, Mapping):
        freshness = {}
    status = str(freshness.get("status") or "unknown").strip()
    if status not in {"fresh", "stale", "missing", "unknown"}:
        status = "unknown"
    reasons = freshness.get("reasons")
    return {
        "status": status,
        "reasons": [str(reason) for reason in reasons] if isinstance(reasons, list) else [],
        "graph_query_used": guard_result.get("decision") == "allowed_hint",
    }


def _pathfinder_source_bundle(
    *,
    query_text: str,
    source_paths: list[str],
    facts: list[str],
    generated_at: str,
) -> dict[str, Any]:
    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": query_text,
        "anchor_type": "none",
        "anchor_id": None,
        "topic_id": None,
        "anchor_title": None,
        "episode_ids": [],
        "claim_ids": [],
        "page_ids": [],
        "source_paths": source_paths,
        "support_facts": facts,
        "bundle_mode": "unanchored",
        "generated_at": generated_at,
    }
    validate_pathfinder_bundle(bundle)
    return bundle


def _valid_origin_shortcut_result(origin_shortcut: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(origin_shortcut, Mapping):
        return None
    try:
        validate_origin_shortcut_result(origin_shortcut)
    except Exception:
        return None
    return dict(origin_shortcut)


def _mailbox_support_result(
    *,
    graph_query_id: str,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    source_refs: list[dict[str, Any]],
    support_bundle: Mapping[str, Any] | None,
    origin_shortcut_result: Mapping[str, Any] | None,
    stop_reason: str | None,
    generated_at: str,
) -> dict[str, Any]:
    status = "completed" if support_bundle is not None and stop_reason is None else "stopped"
    fallback_used = status != "completed"
    active_source_refs = source_refs or [
        {
            "kind": "source_ref",
            "path_hint": "missing-source-ref",
            "range_hint": None,
            "symlink_hint": None,
            "message_id": None,
        }
    ]
    packet_ref = {
        "message_id": graph_query_id,
        "packet_type": "support_bundle",
        "path_hint": None,
    }
    result = {
        "schema_version": "mailbox_support_result.v1",
        "emission_result_id": f"graph-query-support:{graph_query_id}",
        "chain_result_id": "graph-query-support-bundle",
        "signal_id": graph_query_id,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": f"{provider_id}:{provider_profile}:{provider_session_id}",
        "status": status,
        "stop_reason": stop_reason,
        "source_refs": active_source_refs[:12],
        "mailbox_packet_refs": [packet_ref] if support_bundle is not None else [],
        "fallback_state": {
            "fallback_used": fallback_used,
            "fallback_reason": stop_reason,
            "quarantine": False,
        },
        "mailbox_message": {
            "message_id": graph_query_id,
            "message_type": "graph_hint",
        }
        if support_bundle is not None
        else None,
        "mailbox_guard_result": {
            "verdict": "accept" if support_bundle is not None else "reject",
            "reason_codes": ["graph_query_support_bundle_bounded"]
            if support_bundle is not None
            else ["graph_output_guard_blocked"],
        },
        "support_bundle": dict(support_bundle) if isinstance(support_bundle, Mapping) else None,
        "origin_shortcut_result": dict(origin_shortcut_result) if isinstance(origin_shortcut_result, Mapping) else None,
        "inbox_delivery": {
            "message_id": graph_query_id,
            "delivery_status": "not_mutated",
            "inbox_path": None,
        }
        if support_bundle is not None
        else None,
        "next_action": "same_session_answer_smoke" if support_bundle is not None else "stop",
        "created_at": generated_at,
    }
    validate_mailbox_support_result(result)
    return result


def build_graph_query_support_bundle_result(
    *,
    graph_result: Mapping[str, Any],
    snapshot_manifest: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any] | str] | None,
    origin_shortcut: Mapping[str, Any] | None = None,
    workspace_root: Path | None = None,
    provider_id: str = "hermes",
    provider_profile: str = "default",
    provider_session_id: str = "graph-query-support",
    graph_query_id: str | None = None,
    requested_use: str = "support_hint",
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_graphify_snapshot_manifest(snapshot_manifest)
    active_generated_at = generated_at or utc_now_iso()
    active_graph_query_id = graph_query_id or f"graph-query:{uuid.uuid4().hex}"
    normalized_refs = _normalize_source_refs(source_refs)
    guard_result = build_graph_output_guard_result(
        graph_result=graph_result,
        snapshot_manifest=snapshot_manifest,
        source_refs=source_refs,
        origin_shortcut=origin_shortcut,
        requested_use=requested_use,
        generated_at=active_generated_at,
    )
    validate_graph_output_guard_result(guard_result)
    if guard_result["decision"] != "allowed_hint":
        mailbox_result = _mailbox_support_result(
            graph_query_id=active_graph_query_id,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
            source_refs=normalized_refs,
            support_bundle=None,
            origin_shortcut_result=None,
            stop_reason="graph_output_guard_blocked",
            generated_at=active_generated_at,
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "stopped",
            "stop_reason": "graph_output_guard_blocked",
            "source_role": SOURCE_ROLE,
            "canonicality": CANONICALITY,
            "graph_query_id": active_graph_query_id,
            "guard_result": guard_result,
            "support_bundle": None,
            "mailbox_support_result": mailbox_result,
            "support_material_bounded": True,
            "graph_output_bypassed_provenance_gate": False,
            "final_answer_allowed": False,
            "canonical_output_allowed": False,
            "generated_at": active_generated_at,
        }
        validate_graph_query_support_bundle_result(payload)
        return payload

    query_text = str(graph_result.get("query_text") or graph_result.get("query") or "").strip() or "graph query"
    paths = _source_paths(source_refs=source_refs, origin_shortcut=origin_shortcut, workspace_root=workspace_root)
    facts = _graph_facts(graph_result)
    pathfinder_bundle = _pathfinder_source_bundle(
        query_text=query_text,
        source_paths=paths,
        facts=facts,
        generated_at=active_generated_at,
    )
    support_bundle = {
        "schema_version": "support_bundle.v1",
        "source_packet_id": active_graph_query_id,
        "source_packet_type": "graph_hint",
        "query_text": query_text,
        "topic": str(graph_result.get("topic") or query_text),
        "human_summary": str(graph_result.get("human_summary") or "Derived graph query support hint."),
        "facts": facts,
        "source_paths": paths,
        "graph_freshness": _freshness_for_support_bundle(guard_result),
        "pathfinder_bundle": pathfinder_bundle,
        "decision_key": None,
        "mailbox_location": None,
        "proof_token": None,
        "rationale_code": "derived_graph_query_support_hint_only",
        "canonical_note": _first_matching_path(paths, prefixes=("vault/topics/", "vault/queries/")),
        "community_note": None,
        "provenance_note": _first_matching_path(paths, prefixes=("vault/provenance/", "vault/_meta/provenance/")),
        "community_id": None,
        "source_ref": _source_ref_token(source_refs),
    }
    validate_support_bundle(support_bundle)
    origin_result = _valid_origin_shortcut_result(origin_shortcut)
    if origin_result is None and workspace_root is not None:
        origin_result = follow_origin_shortcut(support_bundle, workspace_root=workspace_root)
        validate_origin_shortcut_result(origin_result)
    mailbox_result = _mailbox_support_result(
        graph_query_id=active_graph_query_id,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        source_refs=normalized_refs,
        support_bundle=support_bundle,
        origin_shortcut_result=origin_result,
        stop_reason=None,
        generated_at=active_generated_at,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "stop_reason": None,
        "source_role": SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "graph_query_id": active_graph_query_id,
        "guard_result": guard_result,
        "support_bundle": support_bundle,
        "mailbox_support_result": mailbox_result,
        "support_material_bounded": len(facts) <= MAX_SUPPORT_FACTS and len(paths) <= MAX_SOURCE_PATHS,
        "graph_output_bypassed_provenance_gate": False,
        "final_answer_allowed": False,
        "canonical_output_allowed": False,
        "generated_at": active_generated_at,
    }
    validate_graph_query_support_bundle_result(payload)
    return payload


def validate_graph_query_support_bundle_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Invalid graph query support bundle result schema_version")
    if payload.get("source_role") != SOURCE_ROLE:
        raise ValueError("Graph query support bundle source_role changed")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graph query support bundle must not be canonical")
    for flag in ("graph_output_bypassed_provenance_gate", "final_answer_allowed", "canonical_output_allowed"):
        if payload.get(flag) is not False:
            raise ValueError(f"Graph query support bundle flag must be false: {flag}")
    if payload.get("support_material_bounded") is not True:
        raise ValueError("Graph query support bundle material must remain bounded")

    guard_result = payload.get("guard_result")
    if not isinstance(guard_result, Mapping):
        raise ValueError("Graph query support bundle requires guard_result")
    validate_graph_output_guard_result(guard_result)

    mailbox_result = payload.get("mailbox_support_result")
    if not isinstance(mailbox_result, Mapping):
        raise ValueError("Graph query support bundle requires mailbox_support_result")
    validate_mailbox_support_result(mailbox_result)

    status = payload.get("status")
    if status == "completed":
        if guard_result.get("decision") != "allowed_hint":
            raise ValueError("Completed graph query support bundle requires allowed graph hint")
        support_bundle = payload.get("support_bundle")
        if not isinstance(support_bundle, Mapping):
            raise ValueError("Completed graph query support bundle requires support_bundle")
        validate_support_bundle(support_bundle)
        if not support_bundle.get("source_paths"):
            raise ValueError("Graph query support bundle requires source_paths")
        graph_freshness = support_bundle.get("graph_freshness")
        if not isinstance(graph_freshness, Mapping) or graph_freshness.get("graph_query_used") is not True:
            raise ValueError("Graph query support bundle requires graph freshness metadata")
        if mailbox_result.get("status") != "completed":
            raise ValueError("Completed graph query support bundle requires completed mailbox support result")
    elif status == "stopped":
        if payload.get("support_bundle") is not None:
            raise ValueError("Stopped graph query support bundle must not include support_bundle")
        if mailbox_result.get("status") != "stopped":
            raise ValueError("Stopped graph query support bundle requires stopped mailbox support result")
    else:
        raise ValueError("Graph query support bundle status must be completed or stopped")
