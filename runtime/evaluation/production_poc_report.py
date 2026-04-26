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
        "ux_trust_decision": str(ux_trust_report.get("decision") or "red_captured"),
        "foreground_live_comparison_decision": str(
            foreground_live_comparison.get("decision") or "red_captured"
        ),
        "failing_metrics": failing_metrics,
        "residual_risks": [str(risk) for risk in residual_risks],
        "checked_at": utc_now_iso(),
    }
    validate_production_poc_report(report)
    return report
