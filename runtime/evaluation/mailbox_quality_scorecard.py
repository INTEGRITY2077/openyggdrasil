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
MAILBOX_QUALITY_SCORECARD_SCHEMA_PATH = (
    CONTRACTS_ROOT / "mailbox_quality_scorecard.v1.schema.json"
)

NOISY_LIFECYCLE_STATES = {"stale", "superseded", "conflict", "conflicting"}


@lru_cache(maxsize=1)
def load_mailbox_quality_scorecard_schema() -> dict[str, Any]:
    return json.loads(MAILBOX_QUALITY_SCORECARD_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_mailbox_quality_scorecard(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_mailbox_quality_scorecard_schema())


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


def _reason_codes_present(row: Mapping[str, Any]) -> bool:
    return bool(_non_empty_list(row.get("reason_codes")))


def _is_accepted(row: Mapping[str, Any]) -> bool:
    return str(row.get("decision") or "").strip().lower() == "accepted"


def _is_rejected(row: Mapping[str, Any]) -> bool:
    return str(row.get("decision") or "").strip().lower() == "rejected"


def _lifecycle(row: Mapping[str, Any]) -> str:
    return str(row.get("lifecycle_status") or "").strip().lower()


def _accepted_rows(selection_trace: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in selection_trace if _is_accepted(row)]


def _rejected_rows(selection_trace: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in selection_trace if _is_rejected(row)]


def _bad_accepted(row: Mapping[str, Any]) -> bool:
    return (
        bool(row.get("is_decoy"))
        or bool(row.get("is_irrelevant"))
        or bool(row.get("derived_as_sot"))
        or bool(row.get("has_conflict"))
        or _lifecycle(row) in NOISY_LIFECYCLE_STATES
    )


def _count_accepted(
    accepted_rows: Sequence[Mapping[str, Any]],
    predicate_key: str,
) -> int:
    return sum(1 for row in accepted_rows if bool(row.get(predicate_key)))


def _count_lifecycle(
    accepted_rows: Sequence[Mapping[str, Any]],
    lifecycle_state: str,
) -> int:
    return sum(1 for row in accepted_rows if _lifecycle(row) == lifecycle_state)


def _relevance_rationale_coverage(support_bundle: Mapping[str, Any]) -> float:
    has_facts = bool(_non_empty_list(support_bundle.get("facts")))
    has_rationale = _non_empty(support_bundle.get("rationale_code")) or _non_empty(
        support_bundle.get("human_summary")
    )
    return 1.0 if has_facts and has_rationale else 0.0


def _provenance_coverage(support_bundle: Mapping[str, Any]) -> float:
    has_packet_id = _non_empty(support_bundle.get("source_packet_id"))
    has_source_paths = bool(_non_empty_list(support_bundle.get("source_paths")))
    return 1.0 if has_packet_id and has_source_paths else 0.0


def _rejection_reason_coverage(rejected_rows: Sequence[Mapping[str, Any]]) -> float | str:
    if not rejected_rows:
        return "not_applicable"
    return _ratio(sum(1 for row in rejected_rows if _reason_codes_present(row)), len(rejected_rows))


def _failing_metrics(
    *,
    bundle_size: int,
    declared_limit: int,
    mailbox_noise_ratio: float,
    relevance_rationale_coverage: float,
    provenance_coverage: float,
    rejection_reason_coverage: float | str,
    stale_false_accept_count: int,
    superseded_false_accept_count: int,
    conflict_false_accept_count: int,
    decoy_false_accept_count: int,
    irrelevant_memory_citation_count: int,
    derived_as_sot_count: int,
) -> list[str]:
    failing: list[str] = []
    if bundle_size > declared_limit:
        failing.append("bundle_size")
    if mailbox_noise_ratio > 0.20:
        failing.append("mailbox_noise_ratio")
    if relevance_rationale_coverage < 1.0:
        failing.append("relevance_rationale_coverage")
    if provenance_coverage < 1.0:
        failing.append("provenance_coverage")
    if isinstance(rejection_reason_coverage, float) and rejection_reason_coverage < 1.0:
        failing.append("rejection_reason_coverage")
    if stale_false_accept_count > 0:
        failing.append("stale_false_accept_count")
    if superseded_false_accept_count > 0:
        failing.append("superseded_false_accept_count")
    if conflict_false_accept_count > 0:
        failing.append("conflict_false_accept_count")
    if decoy_false_accept_count > 0:
        failing.append("decoy_false_accept_count")
    if irrelevant_memory_citation_count > 0:
        failing.append("irrelevant_memory_citation_count")
    if derived_as_sot_count > 0:
        failing.append("derived_as_sot_count")
    return failing


def _score(failing_metrics: Sequence[str]) -> int:
    score = max(0, 5 - len(failing_metrics))
    zero_tolerance_failures = {
        "stale_false_accept_count",
        "superseded_false_accept_count",
        "conflict_false_accept_count",
        "decoy_false_accept_count",
        "irrelevant_memory_citation_count",
        "derived_as_sot_count",
    }
    if zero_tolerance_failures.intersection(failing_metrics):
        score = min(score, 3)
    return score


def build_mailbox_quality_scorecard(
    *,
    support_bundle: Mapping[str, Any],
    selection_trace: Sequence[Mapping[str, Any]],
    declared_limit: int,
) -> dict[str, Any]:
    """Build the P9 mailbox-quality scorecard from provider mailbox artifacts."""

    accepted = _accepted_rows(selection_trace)
    rejected = _rejected_rows(selection_trace)
    bundle_size = len(_non_empty_list(support_bundle.get("facts")))
    accepted_count = len(accepted)
    noisy_accepted_count = sum(1 for row in accepted if _bad_accepted(row))
    noise_ratio = _ratio(noisy_accepted_count, accepted_count)
    rationale_coverage = _relevance_rationale_coverage(support_bundle)
    provenance_coverage = _provenance_coverage(support_bundle)
    rejection_coverage = _rejection_reason_coverage(rejected)
    stale_count = _count_lifecycle(accepted, "stale")
    superseded_count = _count_lifecycle(accepted, "superseded")
    conflict_count = (
        _count_lifecycle(accepted, "conflict")
        + _count_lifecycle(accepted, "conflicting")
        + _count_accepted(accepted, "has_conflict")
    )
    decoy_count = _count_accepted(accepted, "is_decoy")
    irrelevant_count = _count_accepted(accepted, "is_irrelevant")
    derived_count = _count_accepted(accepted, "derived_as_sot")
    failing = _failing_metrics(
        bundle_size=bundle_size,
        declared_limit=declared_limit,
        mailbox_noise_ratio=noise_ratio,
        relevance_rationale_coverage=rationale_coverage,
        provenance_coverage=provenance_coverage,
        rejection_reason_coverage=rejection_coverage,
        stale_false_accept_count=stale_count,
        superseded_false_accept_count=superseded_count,
        conflict_false_accept_count=conflict_count,
        decoy_false_accept_count=decoy_count,
        irrelevant_memory_citation_count=irrelevant_count,
        derived_as_sot_count=derived_count,
    )
    scorecard = {
        "schema_version": "mailbox_quality_scorecard.v1",
        "scorecard_id": uuid.uuid4().hex,
        "decision": "green_passed" if not failing else "red_captured",
        "score": _score(failing),
        "bundle_size": bundle_size,
        "declared_limit": int(declared_limit),
        "candidate_count": len(selection_trace),
        "accepted_count": accepted_count,
        "rejected_count": len(rejected),
        "mailbox_noise_ratio": noise_ratio,
        "relevance_rationale_coverage": rationale_coverage,
        "provenance_coverage": provenance_coverage,
        "rejection_reason_coverage": rejection_coverage,
        "stale_false_accept_count": stale_count,
        "superseded_false_accept_count": superseded_count,
        "conflict_false_accept_count": conflict_count,
        "decoy_false_accept_count": decoy_count,
        "irrelevant_memory_citation_count": irrelevant_count,
        "derived_as_sot_count": derived_count,
        "failing_metrics": failing,
        "checked_at": utc_now_iso(),
    }
    validate_mailbox_quality_scorecard(scorecard)
    return scorecard
