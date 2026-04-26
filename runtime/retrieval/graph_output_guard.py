from __future__ import annotations

from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from reasoning.typed_availability_metrics import measure_typed_availability_ux_metrics
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


def _first_graph_unavailable_reason(reason_codes: Sequence[Any]) -> str:
    preferred = (
        "graph_snapshot_unavailable",
        "graph_freshness_not_trusted",
        "sot_provenance_shortcut_missing",
        "graph_manifest_not_non_sot",
    )
    normalized = [str(code).strip() for code in reason_codes if str(code).strip()]
    for code in preferred:
        if code in normalized:
            return code
    return normalized[0] if normalized else "graph_output_unavailable"


def build_graph_unavailable_typed_fallback(
    *,
    graph_guard_result: Mapping[str, Any],
    provider_comment: str | None = None,
    user_help: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Convert unavailable graph output into a typed non-SOT fallback payload."""

    validate_graph_output_guard_result(graph_guard_result)
    reason_codes = [str(code) for code in graph_guard_result.get("reason_codes") or []]
    reason_code = _first_graph_unavailable_reason(reason_codes)
    payload = {
        "schema_version": "graph_unavailable_typed_fallback.v1",
        "status": "unavailable",
        "unavailable_kind": "graph_output_unavailable",
        "check_id": "graph_output_guard",
        "reason_code": reason_code,
        "failed_check_ids": reason_codes or [reason_code],
        "runner_outcome": "typed_unavailable",
        "fault_domain": "derived_graph_visibility",
        "category": "graph_unavailable_fallback",
        "provider_comment": provider_comment
        or "Graph output is unavailable or not trustworthy enough to use as an answer source.",
        "user_help": user_help
        or "Regenerate the Graphify snapshot or continue with vault/mailbox evidence only.",
        "derived_as_sot_count": 0,
        "graph_only_answer_allowed": False,
        "canonical_output_allowed": False,
        "authoritative_use_allowed": False,
        "source_role": SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "manifest_id": graph_guard_result.get("manifest_id"),
        "manifest_status": graph_guard_result.get("manifest_status"),
        "created_at": generated_at or utc_now_iso(),
    }
    validate_graph_unavailable_typed_fallback(payload)
    return payload


def validate_graph_unavailable_typed_fallback(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "graph_unavailable_typed_fallback.v1":
        raise ValueError("Invalid graph unavailable fallback schema_version")
    if payload.get("status") != "unavailable":
        raise ValueError("Graph fallback status must be unavailable")
    if payload.get("unavailable_kind") != "graph_output_unavailable":
        raise ValueError("Graph fallback unavailable_kind is invalid")
    for key in ("reason_code", "runner_outcome", "fault_domain", "provider_comment", "user_help"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"Graph fallback missing typed field: {key}")
    failed_check_ids = payload.get("failed_check_ids")
    if not isinstance(failed_check_ids, list) or not failed_check_ids:
        raise ValueError("Graph fallback requires failed_check_ids")
    for flag in ("graph_only_answer_allowed", "canonical_output_allowed", "authoritative_use_allowed"):
        if payload.get(flag) is not False:
            raise ValueError(f"Graph fallback flag must be false: {flag}")
    if int(payload.get("derived_as_sot_count") or 0) < 0:
        raise ValueError("Graph fallback derived_as_sot_count must be non-negative")


def measure_graph_unavailable_typed_fallback_metrics(
    fallback_payload: Mapping[str, Any],
    *,
    unsupported_claim_count: int = 0,
) -> dict[str, Any]:
    """Measure UX-FS-03/09 graph unavailable fallback visibility."""

    validate_graph_unavailable_typed_fallback(fallback_payload)
    typed_metrics = measure_typed_availability_ux_metrics(
        expected_surfaces=["graph_output"],
        surface_payloads={"graph_output": fallback_payload},
        unsupported_claim_count=unsupported_claim_count,
    )
    derived_as_sot_count = int(fallback_payload.get("derived_as_sot_count") or 0)
    graph_only_answer_allowed = bool(fallback_payload.get("graph_only_answer_allowed"))
    failing_metrics: list[str] = []
    if typed_metrics["typed_unavailable_coverage"] != 1.0:
        failing_metrics.append("typed_unavailable_coverage")
    if unsupported_claim_count:
        failing_metrics.append("unsupported_claim_count")
    if derived_as_sot_count:
        failing_metrics.append("derived_as_sot_count")
    if graph_only_answer_allowed:
        failing_metrics.append("graph_only_answer_allowed")

    return {
        "surface_id": "UX-FS-03",
        "secondary_surface_id": "UX-FS-09",
        "scenario_id": "P9-S10",
        "typed_unavailable_coverage": typed_metrics["typed_unavailable_coverage"],
        "unsupported_claim_count": int(unsupported_claim_count),
        "derived_as_sot_count": derived_as_sot_count,
        "graph_only_answer_allowed": graph_only_answer_allowed,
        "provider_comment_present": bool(str(fallback_payload.get("provider_comment") or "").strip()),
        "user_help_present": bool(str(fallback_payload.get("user_help") or "").strip()),
        "failing_metrics": failing_metrics,
        "decision": "green_passed" if not failing_metrics else "red_captured",
    }
