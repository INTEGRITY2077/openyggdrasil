from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Mapping

from delivery.mailbox_schema import validate_message
from delivery.mailbox_store import append_message
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
ASYNC_MAILBOX_JOB_SCHEMA_VERSION = "reasoning_lease_mailbox_job.v1"
ASYNC_MAILBOX_ENQUEUE_SCHEMA_VERSION = "reasoning_lease_async_job_enqueue_result.v1"
ASYNC_MAILBOX_MESSAGE_TYPE = "execute_deep_search"


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


def _request_fingerprint(request: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(request), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_scope(request: Mapping[str, Any]) -> dict[str, Any]:
    scope = {"profile": str(request.get("provider_profile") or "default")}
    provider_id = request.get("provider_id")
    if provider_id:
        scope["provider_id"] = str(provider_id)
    session_id = request.get("provider_session_id")
    if session_id:
        scope["session_id"] = str(session_id)
    return scope


def build_reasoning_lease_mailbox_job(
    lease_request: Mapping[str, Any],
    *,
    job_id: str | None = None,
    created_at: str | None = None,
    producer_role: str = "reasoning_lease_executor",
) -> dict[str, Any]:
    """Build a mailbox command for async reasoning without calling a worker."""

    request = dict(lease_request)
    validate_reasoning_lease_request(request)
    module_id = _normalize_module_id(request.get("requested_by_role"))
    requirement = _requirement_for_module(module_id)
    if requirement is None:
        raise ValueError("unknown reasoning module cannot be queued")
    if not requirement["requires_reasoning"]:
        raise ValueError("deterministic modules cannot be queued for reasoning lease")
    if EFFORT_ORDER[_requested_depth(request)] < EFFORT_ORDER[str(requirement["min_effort"])]:
        raise ValueError("requested reasoning depth is below module minimum")

    fingerprint = _request_fingerprint(request)
    active_job_id = str(job_id or f"reasoning-lease-job-{uuid.uuid4().hex}")
    created = created_at or utc_now_iso()
    payload = {
        "schema_version": ASYNC_MAILBOX_JOB_SCHEMA_VERSION,
        "job_id": active_job_id,
        "job_status": "queued",
        "lease_request_id": request["lease_request_id"],
        "lease_request_ref": (
            "reasoning-lease-request-ref://openyggdrasil/async-mailbox/"
            f"{fingerprint[:32]}"
        ),
        "request_fingerprint_sha256": fingerprint,
        "requested_by_role": module_id,
        "job_type": request["job_type"],
        "priority": request["priority"],
        "inference_mode": request["inference_mode"],
        "required_effort": requirement["min_effort"],
        "preferred_effort": requirement["preferred_effort"],
        "lease_group": requirement["lease_group"],
        "sandbox_required": bool(requirement["sandbox_required"]),
        "sandbox_execution_status": "deferred_to_async_worker",
        "input_ref_count": len(dict(request.get("input_refs") or {})),
        "expected_output_schema": request.get("expected_output_schema"),
        "fallback_policy": request.get("fallback_policy"),
        "synchronous_worker_called": False,
        "callback_execution_status": "not_executed_async_mailbox_job",
        "lease_result_claimed": False,
        "reason_codes": [
            "reasoning_lease_async_mailbox_job_queued",
            "synchronous_callback_not_executed",
            "mailbox_backed_reasoning_job",
        ],
    }
    message = {
        "schema_version": "mailbox.v1",
        "message_id": active_job_id,
        "message_type": ASYNC_MAILBOX_MESSAGE_TYPE,
        "kind": "command",
        "producer": producer_role,
        "created_at": created,
        "status": "new",
        "priority": request["priority"],
        "scope": _safe_scope(request),
        "payload": payload,
        "delivery": {
            "mode": "push_ready",
            "channel": "hermes-inbox",
            "profile_target": str(request.get("provider_profile") or "default"),
        },
        "dedup_key": f"reasoning-lease:{request['lease_request_id']}:{fingerprint[:16]}",
        "human_summary": f"Reasoning lease job queued for {module_id}.",
    }
    if request.get("provider_session_id"):
        message["delivery"]["session_target"] = str(request["provider_session_id"])
    validate_reasoning_lease_mailbox_job(message)
    return message


def validate_reasoning_lease_mailbox_job(message: Mapping[str, Any]) -> None:
    validate_message(dict(message))
    if message.get("message_type") != ASYNC_MAILBOX_MESSAGE_TYPE:
        raise ValueError("reasoning lease async jobs must use execute_deep_search")
    if message.get("kind") != "command":
        raise ValueError("reasoning lease async jobs must be mailbox commands")
    payload = message.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("reasoning lease async job requires payload")
    if payload.get("schema_version") != ASYNC_MAILBOX_JOB_SCHEMA_VERSION:
        raise ValueError("invalid reasoning lease mailbox job schema_version")
    if payload.get("job_status") != "queued":
        raise ValueError("reasoning lease mailbox job must be queued")
    if payload.get("synchronous_worker_called") is not False:
        raise ValueError("async mailbox job must not call a synchronous worker")
    if payload.get("lease_result_claimed") is not False:
        raise ValueError("queued async job must not claim a lease result")
    if not str(payload.get("lease_request_ref") or "").startswith(
        "reasoning-lease-request-ref://openyggdrasil/async-mailbox/"
    ):
        raise ValueError("reasoning lease mailbox job requires a safe request ref")
    forbidden_payload_keys = {"objective", "input_refs", "query_text", "raw_transcript"}
    present_forbidden = forbidden_payload_keys & set(payload)
    if present_forbidden:
        raise ValueError(f"reasoning lease mailbox job copied forbidden keys: {sorted(present_forbidden)}")


def enqueue_reasoning_lease_mailbox_job(
    lease_request: Mapping[str, Any],
    *,
    messages_path: Path | None = None,
    namespace: str | None = None,
    job_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    message = build_reasoning_lease_mailbox_job(
        lease_request,
        job_id=job_id,
        created_at=created_at,
    )
    append_message(message, path=messages_path, namespace=namespace)
    payload = message["payload"]
    result = {
        "schema_version": ASYNC_MAILBOX_ENQUEUE_SCHEMA_VERSION,
        "lease_request_id": payload["lease_request_id"],
        "enqueue_status": "queued",
        "mailbox_backed": True,
        "mailbox_message_id": message["message_id"],
        "mailbox_message_type": message["message_type"],
        "mailbox_queue_ref": f"mailbox-message-ref://openyggdrasil/reasoning-lease/{message['message_id']}",
        "synchronous_worker_called": False,
        "callback_execution_status": "not_executed_async_mailbox_job",
        "lease_result_claimed": False,
        "message": message,
        "queued_at": message["created_at"],
    }
    validate_reasoning_lease_async_job_enqueue_result(result)
    return result


def validate_reasoning_lease_async_job_enqueue_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != ASYNC_MAILBOX_ENQUEUE_SCHEMA_VERSION:
        raise ValueError("invalid reasoning lease async enqueue schema_version")
    if payload.get("enqueue_status") != "queued":
        raise ValueError("reasoning lease async enqueue must be queued")
    if payload.get("mailbox_backed") is not True:
        raise ValueError("reasoning lease async enqueue must be mailbox-backed")
    if payload.get("synchronous_worker_called") is not False:
        raise ValueError("reasoning lease async enqueue must not call a worker")
    if payload.get("lease_result_claimed") is not False:
        raise ValueError("reasoning lease async enqueue must not claim a result")
    if payload.get("mailbox_message_type") != ASYNC_MAILBOX_MESSAGE_TYPE:
        raise ValueError("reasoning lease async enqueue uses the wrong mailbox type")
    message = payload.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("reasoning lease async enqueue requires a message")
    validate_reasoning_lease_mailbox_job(message)


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
