from __future__ import annotations

from typing import Any, Mapping

from harness_common import utc_now_iso
from retrieval.graphify_snapshot_manifest import validate_graphify_snapshot_manifest


SCHEMA_VERSION = "graph_snapshot_replacement_guard_result.v1"
SOURCE_ROLE = "derived_graph_snapshot_replacement_guard"
CANONICALITY = "non_sot"
COUNT_FIELDS = ("nodes", "edges", "communities")
DEFAULT_MAJOR_LOSS_RATIO = 0.5


def _summary_counts(manifest: Mapping[str, Any]) -> dict[str, int | None]:
    summary = manifest.get("summary")
    if not isinstance(summary, Mapping):
        return {field: None for field in COUNT_FIELDS}
    return {
        field: int(summary[field])
        if field in summary and isinstance(summary[field], int) and not isinstance(summary[field], bool)
        else None
        for field in COUNT_FIELDS
    }


def _lineage(previous_manifest: Mapping[str, Any], candidate_manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "previous_manifest_id": previous_manifest.get("manifest_id"),
        "candidate_manifest_id": candidate_manifest.get("manifest_id"),
        "previous_generated_at": previous_manifest.get("generated_at"),
        "candidate_generated_at": candidate_manifest.get("generated_at"),
        "previous_graph_path": previous_manifest.get("graph_path"),
        "candidate_graph_path": candidate_manifest.get("graph_path"),
        "previous_summary_path": previous_manifest.get("summary_path"),
        "candidate_summary_path": candidate_manifest.get("summary_path"),
    }


def _loss_signals(
    *,
    previous_counts: Mapping[str, int | None],
    candidate_counts: Mapping[str, int | None],
    major_loss_ratio: float,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for field in COUNT_FIELDS:
        previous = previous_counts.get(field)
        candidate = candidate_counts.get(field)
        if previous is None or candidate is None:
            signals.append(
                {
                    "field": field,
                    "previous": previous,
                    "candidate": candidate,
                    "delta": None,
                    "loss_count": None,
                    "loss_ratio": None,
                    "major_loss": False,
                }
            )
            continue
        delta = candidate - previous
        loss_count = max(previous - candidate, 0)
        loss_ratio = (loss_count / previous) if previous > 0 else 0.0
        signals.append(
            {
                "field": field,
                "previous": previous,
                "candidate": candidate,
                "delta": delta,
                "loss_count": loss_count,
                "loss_ratio": loss_ratio,
                "major_loss": previous > 0 and loss_ratio >= major_loss_ratio,
            }
        )
    return signals


def _has_explanation(value: str | Mapping[str, Any] | None) -> bool:
    if isinstance(value, Mapping):
        return any(str(item or "").strip() for item in value.values())
    return bool(str(value or "").strip())


def _manifest_non_sot(manifest: Mapping[str, Any]) -> bool:
    policy = manifest.get("provenance_policy")
    if not isinstance(policy, Mapping):
        return False
    return (
        manifest.get("canonicality") == CANONICALITY
        and policy.get("graphify_is_sot") is False
        and policy.get("provider_may_answer_from_graphify_alone") is False
        and policy.get("must_verify_against_sot") is True
    )


def build_graph_snapshot_replacement_guard_result(
    *,
    previous_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
    replacement_explanation: str | Mapping[str, Any] | None = None,
    major_loss_ratio: float = DEFAULT_MAJOR_LOSS_RATIO,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_graphify_snapshot_manifest(previous_manifest)
    validate_graphify_snapshot_manifest(candidate_manifest)
    if major_loss_ratio <= 0 or major_loss_ratio > 1:
        raise ValueError("major_loss_ratio must be within (0, 1]")

    previous_counts = _summary_counts(previous_manifest)
    candidate_counts = _summary_counts(candidate_manifest)
    loss_signals = _loss_signals(
        previous_counts=previous_counts,
        candidate_counts=candidate_counts,
        major_loss_ratio=major_loss_ratio,
    )
    has_major_loss = any(signal["major_loss"] for signal in loss_signals)
    has_explanation = _has_explanation(replacement_explanation)

    reason_codes: list[str] = []
    if not _manifest_non_sot(previous_manifest) or not _manifest_non_sot(candidate_manifest):
        reason_codes.append("graph_snapshot_manifest_not_non_sot")
    if candidate_manifest.get("status") != "available":
        reason_codes.append("candidate_snapshot_unavailable")
    if previous_manifest.get("status") != "available":
        reason_codes.append("previous_snapshot_unavailable")
    if has_major_loss and not has_explanation:
        reason_codes.append("major_unexplained_snapshot_shrink")
    elif has_major_loss:
        reason_codes.append("major_snapshot_shrink_explained")

    if candidate_manifest.get("status") != "available":
        decision = "typed_unavailable"
        replacement_allowed = False
        review_required = False
    elif "graph_snapshot_manifest_not_non_sot" in reason_codes:
        decision = "review_required"
        replacement_allowed = False
        review_required = True
    elif "major_unexplained_snapshot_shrink" in reason_codes:
        decision = "review_required"
        replacement_allowed = False
        review_required = True
    else:
        decision = "allow_replace"
        replacement_allowed = True
        review_required = False

    payload = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "replacement_allowed": replacement_allowed,
        "review_required": review_required,
        "reason_codes": reason_codes,
        "source_role": SOURCE_ROLE,
        "canonicality": CANONICALITY,
        "major_loss_ratio": major_loss_ratio,
        "previous_manifest_status": previous_manifest.get("status"),
        "candidate_manifest_status": candidate_manifest.get("status"),
        "previous_counts": previous_counts,
        "candidate_counts": candidate_counts,
        "loss_signals": loss_signals,
        "lineage": _lineage(previous_manifest, candidate_manifest),
        "replacement_explanation": dict(replacement_explanation)
        if isinstance(replacement_explanation, Mapping)
        else str(replacement_explanation or ""),
        "silent_replacement_allowed": False,
        "canonical_output_allowed": False,
        "graphify_promoted_to_sot": False,
        "generated_at": generated_at or utc_now_iso(),
    }
    validate_graph_snapshot_replacement_guard_result(payload)
    return payload


def validate_graph_snapshot_replacement_guard_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Invalid graph snapshot replacement guard schema_version")
    if payload.get("source_role") != SOURCE_ROLE:
        raise ValueError("Graph snapshot replacement guard source_role changed")
    if payload.get("canonicality") != CANONICALITY:
        raise ValueError("Graph snapshot replacement guard must not be canonical")
    for flag in ("silent_replacement_allowed", "canonical_output_allowed", "graphify_promoted_to_sot"):
        if payload.get(flag) is not False:
            raise ValueError(f"Graph snapshot replacement guard flag must be false: {flag}")

    decision = payload.get("decision")
    if decision not in {"allow_replace", "review_required", "typed_unavailable"}:
        raise ValueError("Graph snapshot replacement guard decision is invalid")
    if not isinstance(payload.get("replacement_allowed"), bool):
        raise ValueError("Graph snapshot replacement guard requires replacement_allowed bool")
    if not isinstance(payload.get("review_required"), bool):
        raise ValueError("Graph snapshot replacement guard requires review_required bool")
    reason_codes = payload.get("reason_codes")
    if not isinstance(reason_codes, list):
        raise ValueError("Graph snapshot replacement guard requires reason_codes list")
    loss_signals = payload.get("loss_signals")
    if not isinstance(loss_signals, list) or len(loss_signals) != len(COUNT_FIELDS):
        raise ValueError("Graph snapshot replacement guard requires one loss signal per count field")
    lineage = payload.get("lineage")
    if not isinstance(lineage, Mapping):
        raise ValueError("Graph snapshot replacement guard requires lineage")
    if not lineage.get("previous_manifest_id") or not lineage.get("candidate_manifest_id"):
        raise ValueError("Graph snapshot replacement guard lineage requires both manifest IDs")

    if "major_unexplained_snapshot_shrink" in reason_codes and payload.get("replacement_allowed") is not False:
        raise ValueError("Major unexplained graph snapshot shrink must block replacement")
    if decision == "review_required":
        if payload.get("review_required") is not True or payload.get("replacement_allowed") is not False:
            raise ValueError("Review-required graph snapshot replacement must block replacement")
    if decision == "typed_unavailable" and payload.get("replacement_allowed") is not False:
        raise ValueError("Unavailable graph snapshot replacement must not be allowed")
    if decision == "allow_replace" and payload.get("replacement_allowed") is not True:
        raise ValueError("Allowed graph snapshot replacement requires replacement_allowed true")
