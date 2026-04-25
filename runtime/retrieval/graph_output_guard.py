from __future__ import annotations

from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from retrieval.graphify_snapshot_manifest import validate_graphify_snapshot_manifest


SCHEMA_VERSION = "graph_output_guard_result.v1"
SOURCE_ROLE = "derived_graph_output_guard"
CANONICALITY = "non_sot"
ALLOWED_HINT_USE = "support_bundle_hint_only"
BLOCKED_USE = "none"
OUTPUT_ROLE = "derived_navigation_and_reporting_only"
ANSWER_REQUESTED_USES = {
    "answer",
    "final_answer",
    "authoritative_answer",
    "canonical_answer",
    "canonical_output",
}
MAX_GRAPH_PREVIEW_CHARS = 512


def _normalize_source_refs(source_refs: Sequence[Mapping[str, Any] | str] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for source_ref in source_refs or []:
        if isinstance(source_ref, Mapping):
            clean = {str(key): value for key, value in source_ref.items() if value not in (None, "")}
            if clean:
                normalized.append(clean)
        else:
            text = str(source_ref or "").strip()
            if text:
                normalized.append({"ref": text})
    return normalized


def _valid_origin_shortcut(origin_shortcut: Mapping[str, Any] | None) -> bool:
    if not isinstance(origin_shortcut, Mapping):
        return False
    shortcut_kind = str(origin_shortcut.get("shortcut_kind") or "").strip()
    return bool(origin_shortcut.get("exists") is True and shortcut_kind and shortcut_kind != "none")


def _graph_preview(graph_result: Mapping[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key in ("query", "query_text", "output_type", "output_role", "graph_path", "summary_path"):
        value = graph_result.get(key)
        if value not in (None, ""):
            preview[key] = value
    summary = graph_result.get("summary")
    if isinstance(summary, Mapping):
        preview["summary"] = dict(summary)
    text = str(preview)[:MAX_GRAPH_PREVIEW_CHARS]
    return {"fields": preview, "text": text}


def _freshness_from(
    *,
    freshness: Mapping[str, Any] | None,
    snapshot_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source = freshness if isinstance(freshness, Mapping) else snapshot_manifest.get("freshness")
    return dict(source) if isinstance(source, Mapping) else {}


def _manifest_is_non_sot(snapshot_manifest: Mapping[str, Any]) -> bool:
    provenance_policy = snapshot_manifest.get("provenance_policy")
    if not isinstance(provenance_policy, Mapping):
        return False
    return (
        snapshot_manifest.get("canonicality") == CANONICALITY
        and provenance_policy.get("graphify_is_sot") is False
        and provenance_policy.get("must_verify_against_sot") is True
        and provenance_policy.get("provider_may_answer_from_graphify_alone") is False
    )


def build_graph_output_guard_result(
    *,
    graph_result: Mapping[str, Any],
    snapshot_manifest: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
    source_refs: Sequence[Mapping[str, Any] | str] | None = None,
    origin_shortcut: Mapping[str, Any] | None = None,
    requested_use: str = "support_hint",
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_graphify_snapshot_manifest(snapshot_manifest)
    active_freshness = _freshness_from(freshness=freshness, snapshot_manifest=snapshot_manifest)
    normalized_source_refs = _normalize_source_refs(source_refs)
    origin_shortcut_valid = _valid_origin_shortcut(origin_shortcut)
    source_backed = bool(normalized_source_refs or origin_shortcut_valid)

    reason_codes: list[str] = []
    if snapshot_manifest.get("status") != "available":
        reason_codes.append("graph_snapshot_unavailable")
    if not _manifest_is_non_sot(snapshot_manifest):
        reason_codes.append("graph_manifest_not_non_sot")
    if active_freshness.get("status") != "fresh" or active_freshness.get("graph_is_trusted") is not True:
        reason_codes.append("graph_freshness_not_trusted")
    if not source_backed:
        reason_codes.append("sot_provenance_shortcut_missing")

    requested = str(requested_use or "").strip() or "support_hint"
    if requested in ANSWER_REQUESTED_USES:
        reason_codes.append("graph_only_answer_forbidden")

    support_hint_allowed = (
        snapshot_manifest.get("status") == "available"
        and _manifest_is_non_sot(snapshot_manifest)
        and active_freshness.get("status") == "fresh"
        and active_freshness.get("graph_is_trusted") is True
        and source_backed
    )
    decision = "allowed_hint" if support_hint_allowed and requested not in ANSWER_REQUESTED_USES else "blocked"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "reason_codes": reason_codes,
        "source_role": SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "requested_use": requested,
        "allowed_use": ALLOWED_HINT_USE if support_hint_allowed else BLOCKED_USE,
        "output_role": OUTPUT_ROLE,
        "canonical_output_allowed": False,
        "final_answer_allowed": False,
        "authoritative_use_allowed": False,
        "support_bundle_hint_allowed": support_hint_allowed,
        "stale_graph_authoritative": False,
        "graph_only_answer_allowed": False,
        "wiki_index_output_allowed_use": "navigation_and_reporting_only",
        "source_refs": normalized_source_refs,
        "origin_shortcut": dict(origin_shortcut) if isinstance(origin_shortcut, Mapping) else None,
        "origin_shortcut_valid": origin_shortcut_valid,
        "manifest_id": snapshot_manifest.get("manifest_id"),
        "manifest_status": snapshot_manifest.get("status"),
        "freshness": active_freshness,
        "graph_result_preview": _graph_preview(graph_result),
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graph_output_guard_result(payload)
    return payload


def validate_graph_output_guard_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Invalid graph output guard schema_version")
    if payload.get("source_role") != SOURCE_ROLE:
        raise ValueError("Graph output guard must remain a derived guard result")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graph output guard must not be canonical")
    if payload.get("output_role") != OUTPUT_ROLE:
        raise ValueError("Graph output guard output_role must remain navigation/reporting only")

    required_false_flags = (
        "canonical_output_allowed",
        "final_answer_allowed",
        "authoritative_use_allowed",
        "stale_graph_authoritative",
        "graph_only_answer_allowed",
    )
    for flag in required_false_flags:
        if payload.get(flag) is not False:
            raise ValueError(f"Graph output guard flag must be false: {flag}")

    decision = payload.get("decision")
    if decision not in {"allowed_hint", "blocked"}:
        raise ValueError("Graph output guard decision must be allowed_hint or blocked")
    if payload.get("allowed_use") not in {ALLOWED_HINT_USE, BLOCKED_USE}:
        raise ValueError("Graph output guard allowed_use is invalid")

    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list):
        raise ValueError("Graph output guard requires source_refs list")
    reason_codes = payload.get("reason_codes")
    if not isinstance(reason_codes, list):
        raise ValueError("Graph output guard requires reason_codes list")
    support_hint_allowed = payload.get("support_bundle_hint_allowed")
    if not isinstance(support_hint_allowed, bool):
        raise ValueError("Graph output guard requires support_bundle_hint_allowed bool")

    if decision == "allowed_hint":
        if not support_hint_allowed:
            raise ValueError("Allowed graph output must be a support-bundle hint")
        if payload.get("allowed_use") != ALLOWED_HINT_USE:
            raise ValueError("Allowed graph output use must be support_bundle_hint_only")
        if not source_refs and payload.get("origin_shortcut_valid") is not True:
            raise ValueError("Allowed graph output requires SOT source refs or a provenance shortcut")
        freshness = payload.get("freshness")
        if not isinstance(freshness, Mapping):
            raise ValueError("Allowed graph output requires freshness")
        if freshness.get("status") != "fresh" or freshness.get("graph_is_trusted") is not True:
            raise ValueError("Allowed graph output requires trusted fresh graph")
        if reason_codes:
            raise ValueError("Allowed graph output must not carry blocking reasons")

    requested_use = str(payload.get("requested_use") or "")
    if requested_use in ANSWER_REQUESTED_USES and "graph_only_answer_forbidden" not in reason_codes:
        raise ValueError("Answer requests must be blocked from graph-only output")
