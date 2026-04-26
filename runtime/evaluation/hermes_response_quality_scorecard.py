from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
HERMES_RESPONSE_QUALITY_SCORECARD_SCHEMA_PATH = (
    CONTRACTS_ROOT / "hermes_response_quality_scorecard.v1.schema.json"
)

RAW_LEAK_MARKERS = (
    "raw_transcript",
    "raw transcript",
    "raw_session",
    "raw session",
    "provider transcript",
)
LIVE_MISLABEL_MARKERS = (
    "complete live foreground proof",
    "real live foreground proof",
    "live foreground confirmed",
)
CONFLICT_VISIBILITY_MARKERS = (
    "conflict",
    "conflicting",
    "contradiction",
    "contradictory",
    "correction",
    "corrected",
    "superseded",
)
SUPPORTED_CONFIDENCE_VALUES = {"supported", "confident", "asserted"}


@lru_cache(maxsize=1)
def load_hermes_response_quality_scorecard_schema() -> dict[str, Any]:
    return json.loads(
        HERMES_RESPONSE_QUALITY_SCORECARD_SCHEMA_PATH.read_text(encoding="utf-8")
    )


def validate_hermes_response_quality_scorecard(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_response_quality_scorecard_schema(),
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _non_empty_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if _non_empty(item)]


def _claims(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in response.get("claims") or [] if isinstance(row, Mapping)]


def _rejected_memory(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in response.get("rejected_memory") or [] if isinstance(row, Mapping)]


def _conflicting_memory(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in response.get("conflicting_memory") or [] if isinstance(row, Mapping)]


def _claim_text(claim: Mapping[str, Any]) -> str:
    return str(claim.get("text") or "")


def _claim_is_supported(claim: Mapping[str, Any]) -> bool:
    return str(claim.get("confidence") or "").strip().lower() in SUPPORTED_CONFIDENCE_VALUES


def _claim_has_evidence(claim: Mapping[str, Any]) -> bool:
    return bool(_non_empty_list(claim.get("evidence_refs")))


def _unsupported_claim_count(claims: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for claim in claims if _claim_is_supported(claim) and not _claim_has_evidence(claim))


def _silent_conflict_count(
    *,
    response: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> int:
    conflicting_rows = _conflicting_memory(response)
    if not conflicting_rows:
        return 0
    visible_text = " ".join(
        [
            str(response.get("answer_text") or ""),
            *[_claim_text(claim) for claim in claims],
        ]
    ).lower()
    has_visible_conflict_signal = any(marker in visible_text for marker in CONFLICT_VISIBILITY_MARKERS)
    silent = 0
    for row in conflicting_rows:
        has_reason = bool(_non_empty_list(row.get("reason_codes")))
        if not has_reason or not has_visible_conflict_signal:
            silent += 1
    return silent


def _raw_transcript_leak_count(response: Mapping[str, Any]) -> int:
    text = str(response.get("answer_text") or "").lower()
    return 1 if any(marker in text for marker in RAW_LEAK_MARKERS) else 0


def _live_mislabel_count(
    *,
    response: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    expected_unavailable_surfaces: Sequence[str],
) -> int:
    expects_live_unavailable = any(
        str(surface).strip() == "live_foreground_unavailable"
        for surface in expected_unavailable_surfaces
    )
    if not expects_live_unavailable:
        return 0
    text = " ".join([str(response.get("answer_text") or ""), *[_claim_text(claim) for claim in claims]]).lower()
    reports_unavailable = "live_foreground_unavailable" in text or "live foreground is unavailable" in text
    if reports_unavailable:
        return 0
    return 1 if any(marker in text for marker in LIVE_MISLABEL_MARKERS) else 0


def _coverage_for_expected(
    *,
    expected: Sequence[str],
    observed: Sequence[str],
) -> float | str:
    expected_set = {str(item).strip() for item in expected if str(item).strip()}
    if not expected_set:
        return "not_applicable"
    observed_set = {str(item).strip() for item in observed if str(item).strip()}
    return _ratio(len(expected_set & observed_set), len(expected_set))


def _provenance_coverage(response: Mapping[str, Any]) -> float | str:
    used_memory_refs = _non_empty_list(response.get("used_memory_refs"))
    if not used_memory_refs:
        return "not_applicable"
    safe_pointers = _non_empty_list(response.get("safe_evidence_pointers"))
    return 1.0 if safe_pointers else 0.0


def _safe_evidence_pointer_coverage(
    *,
    claims: Sequence[Mapping[str, Any]],
    response: Mapping[str, Any],
) -> float | str:
    supported_claims = [claim for claim in claims if _claim_is_supported(claim)]
    if not supported_claims:
        return "not_applicable"
    safe_pointers = _non_empty_list(response.get("safe_evidence_pointers"))
    return _ratio(len(safe_pointers), len(supported_claims))


def _rejection_reason_coverage(response: Mapping[str, Any]) -> float | str:
    rejected_rows = _rejected_memory(response)
    if not rejected_rows:
        return "not_applicable"
    with_reason = sum(1 for row in rejected_rows if _non_empty_list(row.get("reason_codes")))
    return _ratio(with_reason, len(rejected_rows))


def _failing_metrics(
    *,
    unsupported_claim_count: int,
    silent_conflict_count: int,
    raw_transcript_leak_count: int,
    live_mislabel_count: int,
    derived_as_sot_count: int,
    provenance_coverage: float | str,
    safe_evidence_pointer_coverage: float | str,
    typed_unavailable_coverage: float | str,
    rejection_reason_coverage: float | str,
) -> list[str]:
    failing: list[str] = []
    if unsupported_claim_count > 0:
        failing.append("unsupported_claim_count")
    if silent_conflict_count > 0:
        failing.append("silent_conflict_count")
    if raw_transcript_leak_count > 0:
        failing.append("raw_transcript_leak_count")
    if live_mislabel_count > 0:
        failing.append("live_mislabel_count")
    if derived_as_sot_count > 0:
        failing.append("derived_as_sot_count")
    if isinstance(provenance_coverage, float) and provenance_coverage < 1.0:
        failing.append("provenance_coverage")
    if isinstance(safe_evidence_pointer_coverage, float) and safe_evidence_pointer_coverage < 1.0:
        failing.append("safe_evidence_pointer_coverage")
    if isinstance(typed_unavailable_coverage, float) and typed_unavailable_coverage < 1.0:
        failing.append("typed_unavailable_coverage")
    if isinstance(rejection_reason_coverage, float) and rejection_reason_coverage < 1.0:
        failing.append("rejection_reason_coverage")
    return failing


def _score(failing_metrics: Sequence[str]) -> int:
    score = max(0, 5 - len(failing_metrics))
    zero_tolerance = {
        "unsupported_claim_count",
        "silent_conflict_count",
        "raw_transcript_leak_count",
        "live_mislabel_count",
        "derived_as_sot_count",
    }
    if zero_tolerance.intersection(failing_metrics):
        score = min(score, 3)
    return score


def build_hermes_response_quality_scorecard(
    *,
    response: Mapping[str, Any],
    expected_unavailable_surfaces: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the P9 Hermes response-quality scorecard from response artifacts."""

    claims = _claims(response)
    unsupported = _unsupported_claim_count(claims)
    silent_conflicts = _silent_conflict_count(response=response, claims=claims)
    raw_leaks = _raw_transcript_leak_count(response)
    live_mislabels = _live_mislabel_count(
        response=response,
        claims=claims,
        expected_unavailable_surfaces=expected_unavailable_surfaces,
    )
    derived_count = len(_non_empty_list(response.get("derived_outputs_used_as_sot")))
    provenance = _provenance_coverage(response)
    evidence_pointers = _safe_evidence_pointer_coverage(claims=claims, response=response)
    typed_unavailable = _coverage_for_expected(
        expected=expected_unavailable_surfaces,
        observed=_non_empty_list(response.get("typed_unavailable_surfaces")),
    )
    rejection_coverage = _rejection_reason_coverage(response)
    failing = _failing_metrics(
        unsupported_claim_count=unsupported,
        silent_conflict_count=silent_conflicts,
        raw_transcript_leak_count=raw_leaks,
        live_mislabel_count=live_mislabels,
        derived_as_sot_count=derived_count,
        provenance_coverage=provenance,
        safe_evidence_pointer_coverage=evidence_pointers,
        typed_unavailable_coverage=typed_unavailable,
        rejection_reason_coverage=rejection_coverage,
    )
    scorecard = {
        "schema_version": "hermes_response_quality_scorecard.v1",
        "scorecard_id": uuid.uuid4().hex,
        "decision": "green_passed" if not failing else "red_captured",
        "score": _score(failing),
        "claim_count": len(claims),
        "supported_claim_count": sum(1 for claim in claims if _claim_is_supported(claim)),
        "unsupported_claim_count": unsupported,
        "silent_conflict_count": silent_conflicts,
        "raw_transcript_leak_count": raw_leaks,
        "live_mislabel_count": live_mislabels,
        "derived_as_sot_count": derived_count,
        "provenance_coverage": provenance,
        "safe_evidence_pointer_coverage": evidence_pointers,
        "typed_unavailable_coverage": typed_unavailable,
        "rejection_reason_coverage": rejection_coverage,
        "failing_metrics": failing,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_response_quality_scorecard(scorecard)
    return scorecard
