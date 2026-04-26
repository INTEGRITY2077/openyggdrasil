from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

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
