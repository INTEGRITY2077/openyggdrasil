from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCORE_FIELDS = (
    "source_declaration_score",
    "issue_absorption_score",
    "contract_score",
    "implementation_score",
    "executable_proof_score",
    "production_evidence_score",
    "boundary_hygiene_score",
)


def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_provider_job_alignment_event_schema() -> dict[str, Any]:
    return _load_schema("provider_job_alignment_event.v1.schema.json")


@lru_cache(maxsize=1)
def load_provider_job_alignment_report_schema() -> dict[str, Any]:
    return _load_schema("provider_job_alignment_report.v1.schema.json")


def validate_provider_job_alignment_event(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_provider_job_alignment_event_schema())


def validate_provider_job_alignment_report(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_provider_job_alignment_report_schema())


def _score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, round(numeric, 3)))


def _readiness(score: float, blocking_gaps: Sequence[str]) -> str:
    if score < 0.5:
        return "red"
    if blocking_gaps or score < 0.85:
        return "partial"
    return "aligned"


def build_provider_job_alignment_event(
    *,
    run_id: str,
    job_id: str,
    job_name: str,
    declaration_ref: str,
    provider_issue_refs: Sequence[str],
    implementation_refs: Sequence[str],
    proof_refs: Sequence[str],
    alignment_state: str,
    source_declaration_score: float,
    issue_absorption_score: float,
    contract_score: float,
    implementation_score: float,
    executable_proof_score: float,
    production_evidence_score: float,
    boundary_hygiene_score: float,
    blocking_gaps: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "schema_version": "provider_job_alignment_event.v1",
        "run_id": str(run_id),
        "event_id": f"{run_id}:{job_id}:alignment",
        "job_id": str(job_id),
        "job_name": str(job_name),
        "declaration_ref": str(declaration_ref),
        "provider_issue_refs": [str(ref) for ref in provider_issue_refs],
        "implementation_refs": [str(ref) for ref in implementation_refs],
        "proof_refs": [str(ref) for ref in proof_refs],
        "alignment_state": str(alignment_state),
        "source_declaration_score": _score(source_declaration_score),
        "issue_absorption_score": _score(issue_absorption_score),
        "contract_score": _score(contract_score),
        "implementation_score": _score(implementation_score),
        "executable_proof_score": _score(executable_proof_score),
        "production_evidence_score": _score(production_evidence_score),
        "boundary_hygiene_score": _score(boundary_hygiene_score),
        "blocking_gaps": sorted({str(gap) for gap in blocking_gaps if str(gap)}),
        "checked_at": utc_now_iso(),
    }
    payload["overall_alignment_score"] = round(
        sum(_score(payload[field]) for field in SCORE_FIELDS) / len(SCORE_FIELDS),
        3,
    )
    payload["readiness_state"] = _readiness(
        float(payload["overall_alignment_score"]),
        payload["blocking_gaps"],
    )
    validate_provider_job_alignment_event(payload)
    return payload


def build_provider_job_alignment_report(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checked_events = [dict(event) for event in events]
    for event in checked_events:
        validate_provider_job_alignment_event(event)

    run_ids = {str(event["run_id"]) for event in checked_events}
    run_id = sorted(run_ids)[0] if len(run_ids) == 1 else "mixed"
    average = 0.0
    if checked_events:
        average = round(
            sum(_score(event.get("overall_alignment_score")) for event in checked_events)
            / len(checked_events),
            3,
        )
    blocking_gaps = sorted(
        {
            str(gap)
            for event in checked_events
            for gap in event.get("blocking_gaps", [])
            if str(gap)
        }
    )
    aligned_count = sum(1 for event in checked_events if event["readiness_state"] == "aligned")
    partial_count = sum(1 for event in checked_events if event["readiness_state"] == "partial")
    red_count = sum(1 for event in checked_events if event["readiness_state"] == "red")
    production_evidence_gap_count = sum(
        1 for event in checked_events if _score(event.get("production_evidence_score")) < 1.0
    )

    readiness_state = "aligned"
    if red_count or average < 0.5:
        readiness_state = "red"
    elif partial_count or blocking_gaps or average < 0.85 or production_evidence_gap_count:
        readiness_state = "partial"

    report = {
        "schema_version": "provider_job_alignment_report.v1",
        "run_id": run_id,
        "evaluation_type": "north_star_provider_issue_alignment",
        "readiness_state": readiness_state,
        "event_count": len(checked_events),
        "average_overall_alignment_score": average,
        "aligned_count": aligned_count,
        "partial_count": partial_count,
        "red_count": red_count,
        "production_evidence_gap_count": production_evidence_gap_count,
        "blocking_gaps": blocking_gaps,
        "checked_at": utc_now_iso(),
    }
    validate_provider_job_alignment_report(report)
    return report
