from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from evaluation.why_remembered_answer import validate_product_visible_answer_feedback_item
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
UX_TRUST_REPORT_SCHEMA_PATH = CONTRACTS_ROOT / "ux_trust_report.v1.schema.json"
P9_PASS_FLOOR = 4.25
LIVE_FOREGROUND_STATUSES = {
    "live_proven",
    "typed_unavailable",
    "foreground_equivalent",
    "not_proven",
}
PROVIDER_ANSWER_FEEDBACK_EVIDENCE_KINDS = {
    "decision_candidate",
    "evaluator_verdict",
    "support_bundle",
    "answer_verdict",
}
UNSAFE_FEEDBACK_ROUTE_TOKENS = (
    "d:/",
    "c:/",
    "file://",
    "raw_transcript",
    "raw transcript",
    "transcript.txt",
    "api_key",
)


@lru_cache(maxsize=1)
def load_ux_trust_report_schema() -> dict[str, Any]:
    return json.loads(UX_TRUST_REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_ux_trust_report(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_ux_trust_report_schema())


def _int_metric(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _float_metric(payload: Mapping[str, Any], key: str) -> float | str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score_from_scorecard(payload: Mapping[str, Any]) -> int:
    if "score" in payload:
        return max(0, min(5, _int_metric(payload, "score")))
    failing_count = len(payload.get("failing_metrics") or [])
    if str(payload.get("decision") or "") == "green_passed" and failing_count == 0:
        return 5
    return max(0, 5 - failing_count)


def _coverage_fails(value: float | str) -> bool:
    return isinstance(value, float) and value < 1.0


def _subtract_for_counts(score: int, *counts: int) -> int:
    return max(0, score - sum(1 for count in counts if count > 0))


def _memory_visibility_score(
    *,
    mailbox_quality_scorecard: Mapping[str, Any],
    hermes_response_quality_scorecard: Mapping[str, Any],
) -> int:
    score = 5
    for metric in (
        _float_metric(mailbox_quality_scorecard, "provenance_coverage"),
        _float_metric(mailbox_quality_scorecard, "rejection_reason_coverage"),
        _float_metric(hermes_response_quality_scorecard, "provenance_coverage"),
        _float_metric(hermes_response_quality_scorecard, "rejection_reason_coverage"),
    ):
        if _coverage_fails(metric):
            score -= 1
    return _subtract_for_counts(
        score,
        _int_metric(mailbox_quality_scorecard, "stale_false_accept_count"),
        _int_metric(mailbox_quality_scorecard, "superseded_false_accept_count"),
        _int_metric(mailbox_quality_scorecard, "conflict_false_accept_count"),
        _int_metric(mailbox_quality_scorecard, "decoy_false_accept_count"),
        _int_metric(mailbox_quality_scorecard, "irrelevant_memory_citation_count"),
        _int_metric(mailbox_quality_scorecard, "derived_as_sot_count"),
        _int_metric(hermes_response_quality_scorecard, "derived_as_sot_count"),
    )


def _diagnosability_score(
    *,
    chain_health_scorecard: Mapping[str, Any],
    hermes_response_quality_scorecard: Mapping[str, Any],
    live_foreground_status: str,
) -> int:
    score = 5
    if _coverage_fails(_float_metric(chain_health_scorecard, "handoff_digest_coverage")):
        score -= 1
    if _coverage_fails(_float_metric(chain_health_scorecard, "typed_fallback_visibility")):
        score -= 1
    if _coverage_fails(_float_metric(hermes_response_quality_scorecard, "safe_evidence_pointer_coverage")):
        score -= 1
    if _coverage_fails(_float_metric(hermes_response_quality_scorecard, "typed_unavailable_coverage")):
        score -= 1
    if live_foreground_status not in LIVE_FOREGROUND_STATUSES:
        score -= 1
    return max(0, score)


def _zero_tolerance_failures(
    *,
    mailbox_quality_scorecard: Mapping[str, Any],
    hermes_response_quality_scorecard: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    count_metrics = {
        "raw_transcript_leak_count": hermes_response_quality_scorecard,
        "live_mislabel_count": hermes_response_quality_scorecard,
        "stale_false_accept_count": mailbox_quality_scorecard,
        "superseded_false_accept_count": mailbox_quality_scorecard,
        "silent_conflict_count": mailbox_quality_scorecard,
        "decoy_false_accept_count": mailbox_quality_scorecard,
        "derived_as_sot_count": hermes_response_quality_scorecard,
        "unsupported_claim_count": hermes_response_quality_scorecard,
    }
    for metric, payload in count_metrics.items():
        source_key = "conflict_false_accept_count" if metric == "silent_conflict_count" else metric
        if _int_metric(payload, source_key) > 0:
            failures.append(metric)
    if _coverage_fails(_float_metric(hermes_response_quality_scorecard, "typed_unavailable_coverage")):
        failures.append("typed_unavailable_coverage")
    if _int_metric(mailbox_quality_scorecard, "derived_as_sot_count") > 0:
        failures.append("derived_as_sot_count")
    return sorted(set(failures))


def _failing_metrics(
    *,
    chain_health_scorecard: Mapping[str, Any],
    mailbox_quality_scorecard: Mapping[str, Any],
    hermes_response_quality_scorecard: Mapping[str, Any],
    memory_visibility_score: int,
    diagnosability_score: int,
    zero_tolerance_failures: list[str],
) -> list[str]:
    failing = set(zero_tolerance_failures)
    for prefix, payload in (
        ("chain", chain_health_scorecard),
        ("mailbox", mailbox_quality_scorecard),
        ("hermes", hermes_response_quality_scorecard),
    ):
        if str(payload.get("decision") or "") != "green_passed":
            failing.add(f"{prefix}.decision")
        for metric in payload.get("failing_metrics") or []:
            if metric:
                failing.add(str(metric))
    if memory_visibility_score < 5:
        failing.add("memory_visibility_score")
    if diagnosability_score < 5:
        failing.add("diagnosability_score")
    return sorted(failing)


def build_ux_trust_report(
    *,
    chain_health_scorecard: Mapping[str, Any],
    mailbox_quality_scorecard: Mapping[str, Any],
    hermes_response_quality_scorecard: Mapping[str, Any],
    live_foreground_status: str,
) -> dict[str, Any]:
    """Aggregate P9 scorecards into one provider-side UX trust report."""

    live_status = str(live_foreground_status or "not_proven")
    if live_status not in LIVE_FOREGROUND_STATUSES:
        live_status = "not_proven"
    chain_score = _score_from_scorecard(chain_health_scorecard)
    mailbox_score = _score_from_scorecard(mailbox_quality_scorecard)
    hermes_score = _score_from_scorecard(hermes_response_quality_scorecard)
    memory_score = _memory_visibility_score(
        mailbox_quality_scorecard=mailbox_quality_scorecard,
        hermes_response_quality_scorecard=hermes_response_quality_scorecard,
    )
    diag_score = _diagnosability_score(
        chain_health_scorecard=chain_health_scorecard,
        hermes_response_quality_scorecard=hermes_response_quality_scorecard,
        live_foreground_status=live_status,
    )
    zero_tolerance = _zero_tolerance_failures(
        mailbox_quality_scorecard=mailbox_quality_scorecard,
        hermes_response_quality_scorecard=hermes_response_quality_scorecard,
    )
    failing = _failing_metrics(
        chain_health_scorecard=chain_health_scorecard,
        mailbox_quality_scorecard=mailbox_quality_scorecard,
        hermes_response_quality_scorecard=hermes_response_quality_scorecard,
        memory_visibility_score=memory_score,
        diagnosability_score=diag_score,
        zero_tolerance_failures=zero_tolerance,
    )
    ux_score = round(
        0.20 * chain_score
        + 0.20 * hermes_score
        + 0.20 * mailbox_score
        + 0.20 * memory_score
        + 0.20 * diag_score,
        2,
    )
    if zero_tolerance:
        ux_score = min(ux_score, 3.0)
    report = {
        "schema_version": "ux_trust_report.v1",
        "report_id": uuid.uuid4().hex,
        "decision": "green_passed" if ux_score >= P9_PASS_FLOOR and not failing else "red_captured",
        "ux_trust_score": ux_score,
        "chain_health_score": chain_score,
        "mailbox_quality_score": mailbox_score,
        "hermes_response_quality_score": hermes_score,
        "memory_visibility_score": memory_score,
        "diagnosability_score": diag_score,
        "live_foreground_status": live_status,
        "input_scorecard_ids": {
            "chain_health": str(chain_health_scorecard.get("scorecard_id") or ""),
            "mailbox_quality": str(mailbox_quality_scorecard.get("scorecard_id") or ""),
            "hermes_response_quality": str(hermes_response_quality_scorecard.get("scorecard_id") or ""),
        },
        "zero_tolerance_failures": zero_tolerance,
        "failing_metrics": failing,
        "checked_at": utc_now_iso(),
    }
    validate_ux_trust_report(report)
    return report


def _unsafe_feedback_route_tokens(payload: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True, default=str).replace("\\", "/").lower()
    return [token for token in UNSAFE_FEEDBACK_ROUTE_TOKENS if token in serialized]


def _downstream_evidence_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    evidence = dict(payload)
    if evidence.get("connection_status") != "downstream_decision_evidence_connected":
        raise ValueError("downstream evidence must be connected")
    if evidence.get("connected_downstream_decision_evidence") is not True:
        raise ValueError("downstream evidence must be connected")
    kinds = {
        str(kind)
        for kind in evidence.get("downstream_evidence_kinds") or []
        if str(kind).strip()
    }
    if not PROVIDER_ANSWER_FEEDBACK_EVIDENCE_KINDS.issubset(kinds):
        raise ValueError("downstream evidence is missing provider answer feedback evidence kinds")
    policy = dict(evidence.get("execution_policy") or {})
    if policy.get("raw_provider_material_included") is not False:
        raise ValueError("downstream evidence must not include raw provider material")
    if policy.get("local_filesystem_path_included") is not False:
        raise ValueError("downstream evidence must not include local filesystem paths")
    refs = [
        dict(ref)
        for ref in evidence.get("downstream_decision_evidence") or []
        if isinstance(ref, Mapping) and dict(ref)
    ]
    if not refs:
        raise ValueError("downstream evidence refs are required")
    return {
        "evidence_id": str(evidence.get("evidence_id") or ""),
        "connected_downstream_decision_evidence": True,
        "evidence_kind_count": len(kinds),
        "evidence_ref_count": len(refs),
        "raw_provider_material_included": False,
        "local_filesystem_path_included": False,
    }


def _ux_trust_summary(ux_trust_report: Mapping[str, Any]) -> dict[str, Any]:
    report = dict(ux_trust_report)
    validate_ux_trust_report(report)
    if report.get("decision") != "green_passed":
        raise ValueError("UX trust report must be green_passed for product-visible routing")
    if report.get("zero_tolerance_failures"):
        raise ValueError("UX trust report must not have zero-tolerance failures")
    return {
        "report_id": str(report["report_id"]),
        "decision": str(report["decision"]),
        "ux_trust_score": float(report["ux_trust_score"]),
        "memory_visibility_score": int(report["memory_visibility_score"]),
        "diagnosability_score": int(report["diagnosability_score"]),
        "live_foreground_status": str(report["live_foreground_status"]),
        "live_readiness_claimed": False,
    }


def validate_provider_answer_feedback_route(payload: Mapping[str, Any]) -> None:
    route = dict(payload)
    required = {
        "schema_version",
        "route_id",
        "route_status",
        "product_visible",
        "product_surface_id",
        "memory_evidence_workflow_connected",
        "feedback_item",
        "ux_trust_summary",
        "downstream_evidence_summary",
        "routing_policy",
        "reason_codes",
        "created_at",
    }
    missing = sorted(required - set(route))
    if missing:
        raise ValueError(f"provider answer feedback route is missing: {', '.join(missing)}")
    if route["schema_version"] != "provider_answer_feedback_route.v1":
        raise ValueError("invalid provider answer feedback route schema_version")
    if route["route_status"] != "product_visible_feedback_routed":
        raise ValueError("provider answer feedback route must be product visible")
    if route["product_visible"] is not True:
        raise ValueError("provider answer feedback route must be product visible")
    if route["memory_evidence_workflow_connected"] is not True:
        raise ValueError("memory evidence workflow must be connected")
    if not str(route["product_surface_id"]).strip():
        raise ValueError("product_surface_id is required")

    feedback_item = dict(route["feedback_item"])
    validate_product_visible_answer_feedback_item(feedback_item)
    if feedback_item.get("product_surface_id") != route["product_surface_id"]:
        raise ValueError("feedback item product surface mismatch")

    summary = dict(route["ux_trust_summary"])
    if summary.get("decision") != "green_passed":
        raise ValueError("UX trust summary must be green_passed")
    if summary.get("live_readiness_claimed") is not False:
        raise ValueError("live readiness must not be claimed")

    downstream = dict(route["downstream_evidence_summary"])
    if downstream.get("connected_downstream_decision_evidence") is not True:
        raise ValueError("downstream evidence must be connected")
    if downstream.get("raw_provider_material_included") is not False:
        raise ValueError("raw provider material is not allowed")
    if downstream.get("local_filesystem_path_included") is not False:
        raise ValueError("local filesystem paths are not allowed")

    policy = dict(route["routing_policy"])
    if policy.get("product_visible_feedback_required") is not True:
        raise ValueError("product visible feedback is required")
    if policy.get("memory_evidence_workflow_required") is not True:
        raise ValueError("memory evidence workflow is required")
    if policy.get("safe_evidence_pointers_required") is not True:
        raise ValueError("safe evidence pointers are required")
    if policy.get("selection_reasons_required") is not True:
        raise ValueError("selection reasons are required")
    if policy.get("raw_provider_material_included") is not False:
        raise ValueError("raw provider material is not allowed")
    if policy.get("local_filesystem_path_included") is not False:
        raise ValueError("local filesystem paths are not allowed")
    if policy.get("live_readiness_claimed") is not False:
        raise ValueError("live readiness must not be claimed")

    unsafe = _unsafe_feedback_route_tokens(route)
    if unsafe:
        raise ValueError(f"unsafe feedback route material included: {', '.join(unsafe)}")


def build_provider_answer_feedback_route(
    *,
    feedback_item: Mapping[str, Any],
    ux_trust_report: Mapping[str, Any],
    downstream_decision_evidence: Mapping[str, Any],
    product_surface_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Route safe answer feedback into a product-visible memory/evidence workflow."""

    item = dict(feedback_item)
    validate_product_visible_answer_feedback_item(item)
    product_surface = str(product_surface_id or "").strip()
    if not product_surface:
        raise ValueError("product_surface_id is required")
    if item.get("product_surface_id") != product_surface:
        raise ValueError("feedback item product surface mismatch")
    route = {
        "schema_version": "provider_answer_feedback_route.v1",
        "route_id": uuid.uuid4().hex,
        "route_status": "product_visible_feedback_routed",
        "product_visible": True,
        "product_surface_id": product_surface,
        "memory_evidence_workflow_connected": True,
        "feedback_item": item,
        "ux_trust_summary": _ux_trust_summary(ux_trust_report),
        "downstream_evidence_summary": _downstream_evidence_summary(downstream_decision_evidence),
        "routing_policy": {
            "product_visible_feedback_required": True,
            "memory_evidence_workflow_required": True,
            "safe_evidence_pointers_required": True,
            "selection_reasons_required": True,
            "raw_provider_material_included": False,
            "local_filesystem_path_included": False,
            "live_readiness_claimed": False,
        },
        "reason_codes": [
            "provider_answer_feedback_routed",
            "why_remembered_answer_product_visible",
            "memory_evidence_workflow_connected",
            "raw_provider_material_not_copied",
            "live_readiness_not_claimed",
        ],
        "created_at": created_at or utc_now_iso(),
    }
    validate_provider_answer_feedback_route(route)
    return route
