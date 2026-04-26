from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Mapping

from harness_common import utc_now_iso
from reasoning.module_effort_requirements import EFFORT_ORDER, build_module_effort_requirement
from reasoning.process_sandbox_policy import validate_process_sandbox_runtime_decision
from reasoning.reasoning_lease_contracts import (
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


EXECUTION_SCOPE = "executor_contract_only_not_bubblewrap_proof"
DEFAULT_TIME_BUDGET_SECONDS = 300
MAX_CONFIDENCE = 1.0
MIN_CONFIDENCE = 0.0

ReasoningLeaseWorker = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Clock = Callable[[], float]


def _normalize_module_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _time_budget_seconds(request: Mapping[str, Any]) -> int:
    value = request.get("time_budget_seconds", DEFAULT_TIME_BUDGET_SECONDS)
    return int(value)


def _confidence_from_worker_output(output: Mapping[str, Any]) -> float:
    try:
        value = float(output.get("confidence_score", MAX_CONFIDENCE))
    except (TypeError, ValueError):
        return MIN_CONFIDENCE
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, value))


def _base_output(
    *,
    request: Mapping[str, Any],
    module_id: str,
    requirement: Mapping[str, Any] | None,
    worker_ref: str | None,
    time_budget_seconds: int,
    elapsed_seconds: float | None = None,
    sandbox_decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "reasoning_lease_executor_event.v1",
        "execution_scope": EXECUTION_SCOPE,
        "isolation_proven": False,
        "lease_request_id": request["lease_request_id"],
        "module_id": module_id,
        "required_effort": requirement.get("min_effort") if requirement else None,
        "preferred_effort": requirement.get("preferred_effort") if requirement else None,
        "lease_group": requirement.get("lease_group") if requirement else None,
        "worker_ref": worker_ref,
        "time_budget_seconds": time_budget_seconds,
        "elapsed_seconds": elapsed_seconds,
        "sandbox_required": bool(requirement.get("sandbox_required")) if requirement else None,
        "sandbox_backend": sandbox_decision.get("sandbox_backend") if sandbox_decision else None,
        "sandbox_execution_decision": (
            sandbox_decision.get("execution_decision") if sandbox_decision else None
        ),
        "fallback_policy": request.get("fallback_policy"),
        "openyggdrasil_runtime_failure": False,
    }


def _result(
    *,
    request: Mapping[str, Any],
    lease_status: str,
    producer_role: str,
    worker_ref: str | None,
    output: Mapping[str, Any],
    confidence_score: float,
    failure_reason: str | None,
    fallback_used: bool = False,
) -> dict[str, Any]:
    result = {
        "schema_version": "reasoning_lease_result.v1",
        "lease_result_id": uuid.uuid4().hex,
        "lease_request_id": request["lease_request_id"],
        "lease_status": lease_status,
        "producer_role": producer_role,
        "provider_id": request.get("provider_id"),
        "provider_profile": request.get("provider_profile"),
        "provider_session_id": request.get("provider_session_id"),
        "worker_ref": worker_ref,
        "fallback_used": fallback_used,
        "output": dict(output),
        "confidence_score": confidence_score,
        "failure_reason": failure_reason,
        "completed_at": utc_now_iso(),
    }
    validate_reasoning_lease_result(result)
    return result


def _unavailable_result(
    *,
    request: Mapping[str, Any],
    module_id: str,
    requirement: Mapping[str, Any] | None,
    worker_ref: str | None,
    time_budget_seconds: int,
    reason_code: str,
    runner_outcome: str,
    failure_reason: str,
    elapsed_seconds: float | None = None,
    sandbox_decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output = _base_output(
        request=request,
        module_id=module_id,
        requirement=requirement,
        worker_ref=worker_ref,
        time_budget_seconds=time_budget_seconds,
        elapsed_seconds=elapsed_seconds,
        sandbox_decision=sandbox_decision,
    )
    output.update(
        {
            "decision": "typed_unavailable",
            "reason_code": reason_code,
            "runner_outcome": runner_outcome,
            "completed_output_claimed": False,
        }
    )
    return _result(
        request=request,
        lease_status="unavailable",
        producer_role="reasoning_lease_executor",
        worker_ref=worker_ref,
        output=output,
        confidence_score=0.0,
        failure_reason=failure_reason,
    )


def _declined_result(
    *,
    request: Mapping[str, Any],
    module_id: str,
    requirement: Mapping[str, Any] | None,
    worker_ref: str | None,
    time_budget_seconds: int,
    reason_code: str,
    runner_outcome: str,
) -> dict[str, Any]:
    output = _base_output(
        request=request,
        module_id=module_id,
        requirement=requirement,
        worker_ref=worker_ref,
        time_budget_seconds=time_budget_seconds,
    )
    output.update(
        {
            "decision": "declined",
            "reason_code": reason_code,
            "runner_outcome": runner_outcome,
            "completed_output_claimed": False,
        }
    )
    return _result(
        request=request,
        lease_status="declined",
        producer_role="reasoning_lease_executor",
        worker_ref=worker_ref,
        output=output,
        confidence_score=1.0,
        failure_reason=reason_code,
    )


def _requirement_for_module(module_id: str) -> dict[str, Any] | None:
    try:
        return build_module_effort_requirement(module_id)
    except ValueError:
        return None


def _requested_depth(request: Mapping[str, Any]) -> str:
    depth = request.get("reasoning_depth_requirement", {}).get("requested_depth")
    return str(depth or "none")


def _sandbox_allows_required_execution(sandbox_decision: Mapping[str, Any] | None) -> bool:
    if not sandbox_decision:
        return False
    validate_process_sandbox_runtime_decision(sandbox_decision)
    return sandbox_decision.get("execution_decision") == "allow_sandboxed"


def execute_reasoning_lease(
    lease_request: Mapping[str, Any],
    *,
    sandbox_decision: Mapping[str, Any] | None = None,
    worker: ReasoningLeaseWorker | None = None,
    worker_ref: str | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Execute the minimum E2E5a reasoning-lease contract boundary.

    This function proves request/result handling, module-effort gating, time
    budget enforcement, and fail-closed sandbox policy gating. It deliberately
    does not prove Bubblewrap isolation; that is E2E5b.
    """

    request = dict(lease_request)
    validate_reasoning_lease_request(request)
    module_id = _normalize_module_id(request.get("requested_by_role"))
    time_budget = _time_budget_seconds(request)
    requirement = _requirement_for_module(module_id)
    if requirement is None:
        return _unavailable_result(
            request=request,
            module_id=module_id,
            requirement=None,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code="unknown_reasoning_module",
            runner_outcome="module_unknown",
            failure_reason="unknown_reasoning_module",
        )

    if not requirement["requires_reasoning"]:
        return _declined_result(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code="deterministic_module_reasoning_lease_forbidden",
            runner_outcome="deterministic_module_forbidden",
        )

    if EFFORT_ORDER[_requested_depth(request)] < EFFORT_ORDER[str(requirement["min_effort"])]:
        return _unavailable_result(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code="reasoning_depth_below_module_minimum",
            runner_outcome="effort_below_minimum",
            failure_reason="reasoning_depth_below_module_minimum",
            sandbox_decision=sandbox_decision,
        )

    if requirement["sandbox_required"] and not _sandbox_allows_required_execution(sandbox_decision):
        typed_status = (
            str(sandbox_decision.get("typed_unavailable_status"))
            if sandbox_decision and sandbox_decision.get("typed_unavailable_status")
            else "lease_security_unavailable"
        )
        return _unavailable_result(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code=str(sandbox_decision.get("reason_code")) if sandbox_decision else "sandbox_decision_required",
            runner_outcome="lease_security_unavailable",
            failure_reason=typed_status,
            sandbox_decision=sandbox_decision,
        )

    if worker is None:
        return _unavailable_result(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code="reasoning_lease_worker_unavailable",
            runner_outcome="worker_unavailable",
            failure_reason="reasoning_lease_worker_unavailable",
            sandbox_decision=sandbox_decision,
        )

    now = clock or time.monotonic
    started = float(now())
    try:
        worker_output = dict(worker(request))
    except Exception as exc:
        output = _base_output(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            elapsed_seconds=None,
            sandbox_decision=sandbox_decision,
        )
        output.update(
            {
                "decision": "failed",
                "reason_code": "reasoning_lease_worker_failed",
                "runner_outcome": "worker_failed",
                "exception_type": exc.__class__.__name__,
                "completed_output_claimed": False,
            }
        )
        return _result(
            request=request,
            lease_status="failed",
            producer_role="reasoning_lease_executor",
            worker_ref=worker_ref,
            output=output,
            confidence_score=0.0,
            failure_reason="reasoning_lease_worker_failed",
        )

    elapsed = max(0.0, float(now()) - started)
    if elapsed > time_budget:
        return _unavailable_result(
            request=request,
            module_id=module_id,
            requirement=requirement,
            worker_ref=worker_ref,
            time_budget_seconds=time_budget,
            reason_code="reasoning_lease_time_budget_exceeded",
            runner_outcome="time_budget_exceeded",
            failure_reason="reasoning_lease_time_budget_exceeded",
            elapsed_seconds=elapsed,
            sandbox_decision=sandbox_decision,
        )

    output = _base_output(
        request=request,
        module_id=module_id,
        requirement=requirement,
        worker_ref=worker_ref,
        time_budget_seconds=time_budget,
        elapsed_seconds=elapsed,
        sandbox_decision=sandbox_decision,
    )
    output.update(
        {
            "decision": "completed",
            "runner_outcome": "completed",
            "completed_output_claimed": True,
            "worker_output": worker_output,
        }
    )
    return _result(
        request=request,
        lease_status="completed",
        producer_role="reasoning_lease_executor",
        worker_ref=worker_ref,
        output=output,
        confidence_score=_confidence_from_worker_output(worker_output),
        failure_reason=None,
    )
