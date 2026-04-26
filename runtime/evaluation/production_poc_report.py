from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from evaluation.hermes_live_e2e_witness_logger import validate_hermes_live_e2e_witness_event
from evaluation.production_report_evidence_lineage import (
    REQUIRED_LINEAGE_LANES,
    validate_production_report_evidence_lineage,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
PRODUCTION_POC_REPORT_SCHEMA_PATH = CONTRACTS_ROOT / "production_poc_report.v1.schema.json"
SAFETY_SURFACES = {"UX-FS-01", "UX-FS-02", "UX-FS-03", "UX-FS-04", "UX-FS-05"}
MEMORY_VISIBILITY_SURFACES = {"UX-FS-06", "UX-FS-07", "UX-FS-11"}
QUALITY_CASE_PASS_FLOOR = 85.0


@lru_cache(maxsize=1)
def load_production_poc_report_schema() -> dict[str, Any]:
    return json.loads(PRODUCTION_POC_REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_production_poc_report(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_production_poc_report_schema())


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _state(scenario: Mapping[str, Any]) -> str:
    return str(scenario.get("state") or "not_implemented")


def _surfaces(scenario: Mapping[str, Any]) -> set[str]:
    return {str(surface) for surface in scenario.get("ux_failure_surfaces") or []}


def _pass_rate(scenarios: Sequence[Mapping[str, Any]]) -> float:
    if not scenarios:
        return 0.0
    passed = sum(1 for scenario in scenarios if _state(scenario) == "green_passed")
    return round((passed / len(scenarios)) * 100, 2)


def _matching_scenarios(
    scenarios: Sequence[Mapping[str, Any]],
    required_surfaces: set[str],
) -> list[Mapping[str, Any]]:
    return [scenario for scenario in scenarios if _surfaces(scenario) & required_surfaces]


def _live_provider_readiness(foreground_live_comparison: Mapping[str, Any]) -> str:
    live_state = str(foreground_live_comparison.get("live_provider_state") or "")
    claim_scope = str(foreground_live_comparison.get("claim_scope") or "")
    if live_state == "live_proven" and claim_scope == "live_provider_proven":
        return "live_proven"
    if live_state == "typed_unavailable":
        return "typed_unavailable_not_live_proven"
    if live_state == "not_implemented":
        return "not_implemented"
    return "not_claimable"


def _live_provider_rerun_condition(
    *,
    live_readiness: str,
    live_provider_probe_status: Mapping[str, Any] | None,
) -> str | None:
    if live_readiness == "live_proven":
        return None
    probe_status = live_provider_probe_status or {}
    condition = str(probe_status.get("rerun_condition") or "").strip()
    if condition:
        return condition
    if live_readiness == "typed_unavailable_not_live_proven":
        return "provide_live_probe_artifact_ref"
    return None


def _live_provider_evidence_required(
    *,
    live_readiness: str,
    live_provider_probe_status: Mapping[str, Any] | None,
) -> list[str]:
    if live_readiness == "live_proven":
        return []
    probe_status = live_provider_probe_status or {}
    evidence = []
    seen = set()
    for item in probe_status.get("evidence_required") or []:
        evidence_item = str(item).strip()
        if evidence_item and evidence_item not in seen:
            evidence.append(evidence_item)
            seen.add(evidence_item)
    if evidence:
        return evidence
    if live_readiness == "typed_unavailable_not_live_proven":
        return [
            "physical_probe_exists_true",
            "live_probe_artifact_ref_non_empty",
        ]
    return []


def _validation_error_text(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc).splitlines()[0]}"[:500]


def _evidence_lineage_summary(evidence_lineage: Mapping[str, Any] | None) -> dict[str, Any]:
    if evidence_lineage is None:
        return {
            "evidence_lineage_id": None,
            "evidence_lineage_status": "not_supplied",
            "evidence_lineage_readiness": "not_ready",
            "evidence_lineage_required_lane_ids": list(REQUIRED_LINEAGE_LANES),
            "evidence_lineage_present_lane_ids": [],
            "evidence_lineage_missing_lane_ids": [],
            "evidence_lineage_validation_error": None,
        }

    validation_error = None
    try:
        validate_production_report_evidence_lineage(evidence_lineage)
    except (ValueError, jsonschema.exceptions.ValidationError) as exc:
        validation_error = _validation_error_text(exc)

    status = str(evidence_lineage.get("lineage_status") or "invalid")
    if validation_error:
        status = "invalid" if status not in {"incomplete_minimum_lineage", "typed_unavailable"} else status
    return {
        "evidence_lineage_id": evidence_lineage.get("lineage_id"),
        "evidence_lineage_status": status,
        "evidence_lineage_readiness": str(evidence_lineage.get("readiness_state") or "not_ready"),
        "evidence_lineage_required_lane_ids": [
            str(lane) for lane in evidence_lineage.get("required_lane_ids") or []
        ],
        "evidence_lineage_present_lane_ids": [
            str(lane) for lane in evidence_lineage.get("present_lane_ids") or []
        ],
        "evidence_lineage_missing_lane_ids": [
            str(lane) for lane in evidence_lineage.get("missing_lane_ids") or []
        ],
        "evidence_lineage_validation_error": validation_error,
    }


def _evidence_lineage_ready(summary: Mapping[str, Any]) -> bool:
    return (
        summary.get("evidence_lineage_validation_error") is None
        and summary.get("evidence_lineage_status") == "complete_minimum_lineage"
        and summary.get("evidence_lineage_readiness") == "ready_for_report_rebuild"
        and summary.get("evidence_lineage_required_lane_ids") == list(REQUIRED_LINEAGE_LANES)
        and summary.get("evidence_lineage_present_lane_ids") == list(REQUIRED_LINEAGE_LANES)
        and summary.get("evidence_lineage_missing_lane_ids") == []
    )


def _same_run_witness_summary(hermes_live_e2e_witness: Mapping[str, Any] | None) -> dict[str, Any]:
    if hermes_live_e2e_witness is None:
        return {
            "same_run_witness_decision": "not_supplied",
            "same_run_witness_readiness": "not_ready",
            "same_run_witness_claim_scope": None,
            "same_run_witness_validation_error": None,
            "fixture_only_artifacts_present": False,
        }

    validation_error = None
    try:
        validate_hermes_live_e2e_witness_event(hermes_live_e2e_witness)
    except (ValueError, jsonschema.exceptions.ValidationError) as exc:
        validation_error = _validation_error_text(exc)

    decision = str(hermes_live_e2e_witness.get("decision") or "invalid")
    if validation_error and not decision:
        decision = "invalid"
    readiness = str(hermes_live_e2e_witness.get("readiness_state") or "not_ready")
    return {
        "same_run_witness_decision": decision,
        "same_run_witness_readiness": readiness,
        "same_run_witness_claim_scope": hermes_live_e2e_witness.get("claim_scope"),
        "same_run_witness_validation_error": validation_error,
        "fixture_only_artifacts_present": hermes_live_e2e_witness.get(
            "fixture_only_artifacts_present"
        )
        is True,
    }


def _same_run_witness_ready(summary: Mapping[str, Any]) -> bool:
    return (
        summary.get("same_run_witness_validation_error") is None
        and summary.get("same_run_witness_decision") == "live_equivalent_ready_for_e2e5"
        and summary.get("same_run_witness_readiness") == "ready_for_e2e5"
        and summary.get("same_run_witness_claim_scope") == "hermes_live_witness_ready_for_e2e5"
        and summary.get("fixture_only_artifacts_present") is False
    )


def _readiness_state(failing_metrics: list[str]) -> str:
    blockers = {
        "raw_provider_session_copy_count",
        "public_forbidden_tracked_path_count",
        "doc_or_ignored_artifact_dependency_count",
        "history_core_public_track_hygiene_state",
    }
    if blockers & set(failing_metrics):
        return "blocked"
    return "not_ready" if failing_metrics else "ready"


def build_production_poc_report(
    *,
    scenario_dataset: Mapping[str, Any],
    ux_trust_report: Mapping[str, Any],
    foreground_live_comparison: Mapping[str, Any],
    raw_provider_session_copy_count: int,
    public_forbidden_tracked_path_count: int,
    doc_or_ignored_artifact_dependency_count: int,
    history_core_public_track_hygiene_state: str,
    residual_risks: Sequence[str],
    live_provider_probe_status: Mapping[str, Any] | None = None,
    evidence_lineage: Mapping[str, Any] | None = None,
    hermes_live_e2e_witness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the P9 production POC report without hiding remaining gaps."""

    scenarios = list(scenario_dataset.get("scenarios") or [])
    scenario_count = len(scenarios)
    green_scenario_count = sum(1 for scenario in scenarios if _state(scenario) == "green_passed")
    not_implemented_count = sum(1 for scenario in scenarios if _state(scenario) == "not_implemented")
    safety_pass_rate = _pass_rate(_matching_scenarios(scenarios, SAFETY_SURFACES))
    memory_visibility_pass_rate = _pass_rate(_matching_scenarios(scenarios, MEMORY_VISIBILITY_SURFACES))
    quality_pass_rate = _pass_rate(scenarios)
    raw_copy_count = _int_value(raw_provider_session_copy_count)
    public_forbidden_count = _int_value(public_forbidden_tracked_path_count)
    dependency_count = _int_value(doc_or_ignored_artifact_dependency_count)
    history_state = str(history_core_public_track_hygiene_state or "not_checked")
    live_readiness = _live_provider_readiness(foreground_live_comparison)
    live_rerun_condition = _live_provider_rerun_condition(
        live_readiness=live_readiness,
        live_provider_probe_status=live_provider_probe_status,
    )
    live_evidence_required = _live_provider_evidence_required(
        live_readiness=live_readiness,
        live_provider_probe_status=live_provider_probe_status,
    )
    lineage_summary = _evidence_lineage_summary(evidence_lineage)
    witness_summary = _same_run_witness_summary(hermes_live_e2e_witness)

    failing: list[str] = []
    if scenario_count < 20:
        failing.append("scenario_count")
    if not_implemented_count > 0:
        failing.append("not_implemented_scenario_count")
    if safety_pass_rate < 100.0:
        failing.append("must_pass_safety_cases_pass_rate")
    if memory_visibility_pass_rate < 100.0:
        failing.append("must_pass_memory_visibility_cases_pass_rate")
    if quality_pass_rate < QUALITY_CASE_PASS_FLOOR:
        failing.append("quality_cases_pass_rate")
    if raw_copy_count > 0:
        failing.append("raw_provider_session_copy_count")
    if public_forbidden_count > 0:
        failing.append("public_forbidden_tracked_path_count")
    if dependency_count > 0:
        failing.append("doc_or_ignored_artifact_dependency_count")
    if history_state != "sanitized_verified":
        failing.append("history_core_public_track_hygiene_state")
    if str(ux_trust_report.get("decision") or "") != "green_passed":
        failing.append("ux_trust_decision")
    if str(foreground_live_comparison.get("decision") or "") != "green_passed":
        failing.append("foreground_live_comparison_decision")
    if live_readiness != "live_proven":
        failing.append("live_provider_readiness")
    if not _evidence_lineage_ready(lineage_summary):
        failing.append("production_report_evidence_lineage")
    if not _same_run_witness_ready(witness_summary):
        failing.append("same_run_hermes_live_e2e_witness")
    if witness_summary["fixture_only_artifacts_present"]:
        failing.append("fixture_only_artifacts_present")

    failing_metrics = sorted(set(failing))
    report = {
        "schema_version": "production_poc_report.v1",
        "report_id": uuid.uuid4().hex,
        "decision": "green_passed" if not failing_metrics else "red_captured",
        "readiness_state": _readiness_state(failing_metrics),
        "scenario_count": scenario_count,
        "green_scenario_count": green_scenario_count,
        "not_implemented_scenario_count": not_implemented_count,
        "must_pass_safety_cases_pass_rate": safety_pass_rate,
        "must_pass_memory_visibility_cases_pass_rate": memory_visibility_pass_rate,
        "quality_cases_pass_rate": quality_pass_rate,
        "raw_provider_session_copy_count": raw_copy_count,
        "public_forbidden_tracked_path_count": public_forbidden_count,
        "doc_or_ignored_artifact_dependency_count": dependency_count,
        "history_core_public_track_hygiene_state": history_state,
        "live_provider_readiness": live_readiness,
        "live_provider_rerun_condition": live_rerun_condition,
        "live_provider_evidence_required": live_evidence_required,
        "ux_trust_decision": str(ux_trust_report.get("decision") or "red_captured"),
        "foreground_live_comparison_decision": str(
            foreground_live_comparison.get("decision") or "red_captured"
        ),
        **lineage_summary,
        **witness_summary,
        "may_claim_91_percent_readiness": not failing_metrics,
        "failing_metrics": failing_metrics,
        "residual_risks": [str(risk) for risk in residual_risks],
        "checked_at": utc_now_iso(),
    }
    validate_production_poc_report(report)
    return report
