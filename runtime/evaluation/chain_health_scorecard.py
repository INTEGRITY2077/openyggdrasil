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
CHAIN_HEALTH_SCORECARD_SCHEMA_PATH = CONTRACTS_ROOT / "chain_health_scorecard.v1.schema.json"

ENTRY_STEPS = (
    "provider_runtime_integrity",
    "session_admission_gate",
    "thin_worker_chain",
)
CHAIN_ROLES = (
    "distiller",
    "evaluator",
    "amundsen",
    "seedkeeper",
    "gardener",
    "map_maker",
    "postman",
)
FORBIDDEN_OWNERSHIP_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "canonical_claim",
    "canonical_path",
    "category_selection",
    "mailbox_mutation",
    "sot_write",
}


@lru_cache(maxsize=1)
def load_chain_health_scorecard_schema() -> dict[str, Any]:
    return json.loads(CHAIN_HEALTH_SCORECARD_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_chain_health_scorecard(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_chain_health_scorecard_schema())


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _reason_codes_present(row: Mapping[str, Any]) -> bool:
    return any(str(code).strip() for code in row.get("reason_codes") or [])


def _entry_step_rows(entrypoint_result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("step")): row
        for row in entrypoint_result.get("step_statuses") or []
        if isinstance(row, Mapping)
    }


def _role_step_rows(chain_result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("role")): row
        for row in chain_result.get("role_steps") or []
        if isinstance(row, Mapping)
    }


def _stage_artifact_counts(
    *,
    entrypoint_result: Mapping[str, Any],
    chain_result: Mapping[str, Any],
) -> tuple[int, int]:
    entry_rows = _entry_step_rows(entrypoint_result)
    role_rows = _role_step_rows(chain_result)
    completed = 0

    for step in ENTRY_STEPS:
        status = str(entry_rows.get(step, {}).get("status") or "")
        if status in {"completed", "ready"}:
            completed += 1

    for role in CHAIN_ROLES:
        status = str(role_rows.get(role, {}).get("status") or "")
        if status in {"completed", "ready"}:
            completed += 1

    return completed, len(ENTRY_STEPS) + len(CHAIN_ROLES)


def _role_handoff_digest_ok(
    *,
    role: str,
    row: Mapping[str, Any],
    chain_result: Mapping[str, Any],
) -> bool:
    status = str(row.get("status") or "")
    has_reason = _reason_codes_present(row)
    if not has_reason:
        return False
    if status == "completed":
        return bool(row.get("artifact_kind")) and bool(row.get("artifact_id"))
    if status == "ready" and role == "postman":
        postman_handoff = chain_result.get("postman_handoff")
        return isinstance(postman_handoff, Mapping) and bool(postman_handoff.get("handoff_id"))
    if status in {"fallback_used", "blocked"}:
        fallback_state = chain_result.get("fallback_state")
        fallback_reason = (
            fallback_state.get("fallback_reason")
            if isinstance(fallback_state, Mapping)
            else None
        )
        return bool(fallback_reason or chain_result.get("stop_reason"))
    return False


def _handoff_digest_counts(
    *,
    entrypoint_result: Mapping[str, Any],
    chain_result: Mapping[str, Any],
) -> tuple[int, int]:
    entry_rows = _entry_step_rows(entrypoint_result)
    role_rows = _role_step_rows(chain_result)
    ok = 0

    for step in ENTRY_STEPS:
        row = entry_rows.get(step, {})
        if _reason_codes_present(row):
            ok += 1

    for role in CHAIN_ROLES:
        row = role_rows.get(role, {})
        if _role_handoff_digest_ok(role=role, row=row, chain_result=chain_result):
            ok += 1

    return ok, len(ENTRY_STEPS) + len(CHAIN_ROLES)


def _count_forbidden_keys(value: Any) -> int:
    if isinstance(value, Mapping):
        count = sum(1 for key in value if str(key) in FORBIDDEN_OWNERSHIP_KEYS)
        return count + sum(_count_forbidden_keys(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_forbidden_keys(child) for child in value)
    return 0


def _role_ownership_violation_count(chain_result: Mapping[str, Any]) -> int:
    count = 0
    for row in chain_result.get("role_steps") or []:
        if not isinstance(row, Mapping) or str(row.get("role") or "") not in CHAIN_ROLES:
            count += 1
    count += _count_forbidden_keys(chain_result.get("artifacts"))
    count += _count_forbidden_keys(chain_result.get("postman_handoff"))
    return count


def _typed_fallback_visibility(chain_result: Mapping[str, Any]) -> float | str:
    fallback_state = chain_result.get("fallback_state")
    fallback_used = False
    fallback_reason = None
    if isinstance(fallback_state, Mapping):
        fallback_used = bool(fallback_state.get("fallback_used"))
        fallback_reason = fallback_state.get("fallback_reason")
    if not fallback_used and not chain_result.get("stop_reason"):
        return "not_applicable"
    return 1.0 if str(fallback_reason or chain_result.get("stop_reason") or "").strip() else 0.0


def _valid_path_hints(source_refs: Any) -> set[str]:
    paths: set[str] = set()
    if not isinstance(source_refs, list):
        return paths
    for row in source_refs:
        if not isinstance(row, Mapping):
            continue
        path_hint = str(row.get("path_hint") or "").strip()
        if path_hint and path_hint != "missing-source-ref":
            paths.add(path_hint)
    return paths


def _source_ref_preservation(
    *,
    entrypoint_result: Mapping[str, Any],
    chain_result: Mapping[str, Any],
) -> float:
    entry_paths = _valid_path_hints(entrypoint_result.get("source_refs"))
    chain_paths = _valid_path_hints(chain_result.get("source_refs"))
    if not entry_paths:
        return 0.0
    return _ratio(len(entry_paths & chain_paths), len(entry_paths))


def _latency_budget_status(runtime_budget: Mapping[str, Any] | None) -> str:
    if not isinstance(runtime_budget, Mapping):
        return "not_provided"
    try:
        latency_ms = float(runtime_budget["latency_ms"])
        latency_budget_ms = float(runtime_budget["latency_budget_ms"])
    except (KeyError, TypeError, ValueError):
        return "not_provided"
    return "within_budget" if latency_ms <= latency_budget_ms else "exceeded"


def _retry_error_budget_status(runtime_budget: Mapping[str, Any] | None) -> str:
    if not isinstance(runtime_budget, Mapping):
        return "not_provided"
    try:
        retry_count = int(runtime_budget["retry_count"])
        retry_budget = int(runtime_budget["retry_budget"])
        error_count = int(runtime_budget["error_count"])
        error_budget = int(runtime_budget["error_budget"])
    except (KeyError, TypeError, ValueError):
        return "not_provided"
    if retry_count <= retry_budget and error_count <= error_budget:
        return "within_budget"
    return "exceeded"


def _last_known_good_comparison(last_known_good: Mapping[str, Any] | None) -> str:
    if not isinstance(last_known_good, Mapping):
        return "not_provided"
    comparison = str(last_known_good.get("comparison") or "").strip()
    if comparison in {"same_or_better", "regressed", "not_available"}:
        return comparison
    return "not_provided"


def _failing_metrics(
    *,
    stage_artifact_coverage: float,
    handoff_digest_coverage: float,
    role_ownership_violation_count: int,
    typed_fallback_visibility: float | str,
    source_ref_preservation: float,
    latency_budget_status: str,
    retry_error_budget_status: str,
    last_known_good_comparison: str,
) -> list[str]:
    failing: list[str] = []
    if stage_artifact_coverage < 1.0:
        failing.append("stage_artifact_coverage")
    if handoff_digest_coverage < 1.0:
        failing.append("handoff_digest_coverage")
    if role_ownership_violation_count > 0:
        failing.append("role_ownership_violation_count")
    if isinstance(typed_fallback_visibility, float) and typed_fallback_visibility < 1.0:
        failing.append("typed_fallback_visibility")
    if source_ref_preservation < 1.0:
        failing.append("source_ref_preservation")
    if latency_budget_status != "within_budget":
        failing.append("latency_budget_status")
    if retry_error_budget_status != "within_budget":
        failing.append("retry_error_budget_status")
    if last_known_good_comparison != "same_or_better":
        failing.append("last_known_good_comparison")
    return failing


def build_chain_health_scorecard(
    *,
    entrypoint_result: Mapping[str, Any],
    chain_result: Mapping[str, Any],
    runtime_budget: Mapping[str, Any] | None = None,
    last_known_good: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the P9 chain-health scorecard from typed runner artifacts."""

    completed_stage_count, total_stage_count = _stage_artifact_counts(
        entrypoint_result=entrypoint_result,
        chain_result=chain_result,
    )
    handoff_digest_count, total_handoff_count = _handoff_digest_counts(
        entrypoint_result=entrypoint_result,
        chain_result=chain_result,
    )
    stage_artifact_coverage = _ratio(completed_stage_count, total_stage_count)
    handoff_digest_coverage = _ratio(handoff_digest_count, total_handoff_count)
    role_violations = _role_ownership_violation_count(chain_result)
    typed_fallback = _typed_fallback_visibility(chain_result)
    source_ref = _source_ref_preservation(
        entrypoint_result=entrypoint_result,
        chain_result=chain_result,
    )
    latency_status = _latency_budget_status(runtime_budget)
    retry_error_status = _retry_error_budget_status(runtime_budget)
    lkg_comparison = _last_known_good_comparison(last_known_good)
    failing_metrics = _failing_metrics(
        stage_artifact_coverage=stage_artifact_coverage,
        handoff_digest_coverage=handoff_digest_coverage,
        role_ownership_violation_count=role_violations,
        typed_fallback_visibility=typed_fallback,
        source_ref_preservation=source_ref,
        latency_budget_status=latency_status,
        retry_error_budget_status=retry_error_status,
        last_known_good_comparison=lkg_comparison,
    )
    scorecard = {
        "schema_version": "chain_health_scorecard.v1",
        "scorecard_id": uuid.uuid4().hex,
        "runner_result_id": str(entrypoint_result.get("runner_result_id") or ""),
        "chain_result_id": str(chain_result.get("chain_result_id") or ""),
        "decision": "green_passed" if not failing_metrics else "red_captured",
        "stage_artifact_coverage": stage_artifact_coverage,
        "completed_stage_count": completed_stage_count,
        "total_stage_count": total_stage_count,
        "handoff_digest_coverage": handoff_digest_coverage,
        "handoff_digest_count": handoff_digest_count,
        "total_handoff_count": total_handoff_count,
        "role_ownership_violation_count": role_violations,
        "typed_fallback_visibility": typed_fallback,
        "source_ref_preservation": source_ref,
        "latency_budget_status": latency_status,
        "retry_error_budget_status": retry_error_status,
        "last_known_good_comparison": lkg_comparison,
        "failing_metrics": failing_metrics,
        "checked_at": utc_now_iso(),
    }
    validate_chain_health_scorecard(scorecard)
    return scorecard
