from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Mapping

from delivery.mailbox_schema import validate_message
from delivery.mailbox_store import (
    append_claim,
    append_message,
    read_messages,
    record_mailbox_job_status_transition,
)
from harness_common import utc_now_iso
from reasoning.module_effort_requirements import EFFORT_ORDER, build_module_effort_requirement
from reasoning.process_sandbox_policy import validate_process_sandbox_runtime_decision
from reasoning.ptc_bubblewrap_isolation_trace import (
    build_ptc_bubblewrap_isolation_trace,
    build_ptc_bubblewrap_typed_unavailable_trace,
    validate_reasoning_lease_ptc_bubblewrap_trace,
)
from reasoning.reasoning_lease_contracts import (
    REASONING_LEASE_MAILBOX_JOB_SCHEMA_VERSION,
    validate_reasoning_lease_request,
    validate_reasoning_lease_result,
)


EXECUTION_SCOPE = "executor_contract_only_not_bubblewrap_proof"
DEFAULT_TIME_BUDGET_SECONDS = 300
MAX_CONFIDENCE = 1.0
MIN_CONFIDENCE = 0.0

ReasoningLeaseWorker = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ReasoningLeaseRequestResolver = Callable[[Mapping[str, Any]], Mapping[str, Any]]
PopenFactory = Callable[..., Any]
Clock = Callable[[], float]
ASYNC_MAILBOX_JOB_SCHEMA_VERSION = REASONING_LEASE_MAILBOX_JOB_SCHEMA_VERSION
ASYNC_MAILBOX_ENQUEUE_SCHEMA_VERSION = "reasoning_lease_async_job_enqueue_result.v1"
ASYNC_MAILBOX_CONSUMER_SCHEMA_VERSION = "reasoning_lease_async_consumer_result.v1"
ASYNC_MAILBOX_MESSAGE_TYPE = "execute_deep_search"
ASYNC_MAILBOX_CONSUMER = "reasoning_lease"
ASYNC_MAILBOX_CLAIM_TYPE = "reasoning_lease_job_claimed"
DEFAULT_PTC_WORKER_REF = "ptc-worker-ref://openyggdrasil/reasoning-lease/async-consumer"
DEFAULT_BWRAP_EVIDENCE_REF = (
    "private-evidence://Dev_history/phase2/reasoning-lease-async-consumer"
)
REQUIRED_BWRAP_INTRUSION_ATTEMPTS = (
    "network_escape",
    "process_escape",
    "workspace_escape",
)


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


def _is_pending_reasoning_lease_job(message: Mapping[str, Any]) -> bool:
    payload = message.get("payload")
    return (
        message.get("message_type") == ASYNC_MAILBOX_MESSAGE_TYPE
        and message.get("kind") == "command"
        and message.get("status") == "new"
        and isinstance(payload, Mapping)
        and payload.get("schema_version") == ASYNC_MAILBOX_JOB_SCHEMA_VERSION
        and payload.get("job_status") == "queued"
    )


def _message_with_job_status(
    message: Mapping[str, Any],
    *,
    mailbox_status: str,
    job_status: str,
    reason_code: str,
    lease_result_ref: str | None = None,
    bubblewrap_trace_ref: str | None = None,
) -> dict[str, Any]:
    updated = dict(message)
    payload = dict(updated.get("payload") or {})
    payload["job_status"] = job_status
    payload["last_status_reason_code"] = reason_code
    payload.setdefault("reason_codes", [])
    if reason_code not in payload["reason_codes"]:
        payload["reason_codes"].append(reason_code)
    if lease_result_ref is not None:
        payload["lease_result_ref"] = lease_result_ref
    if bubblewrap_trace_ref is not None:
        payload["bubblewrap_trace_ref"] = bubblewrap_trace_ref
    updated["status"] = mailbox_status
    updated["payload"] = payload
    validate_message(updated)
    return updated


def _record_job_transition(
    *,
    message: Mapping[str, Any],
    to_status: str,
    from_status: str | None,
    reason_code: str,
    namespace: str | None,
    db_path: Path | None,
) -> dict[str, Any]:
    payload = dict(message.get("payload") or {})
    return record_mailbox_job_status_transition(
        message_id=str(message["message_id"]),
        job_id=str(payload.get("job_id") or message["message_id"]),
        lease_request_id=str(payload.get("lease_request_id") or "") or None,
        from_status=from_status,
        to_status=to_status,
        reason_code=reason_code,
        namespace=namespace,
        db_path=db_path,
    )


def _trace_ref_for(job_id: str, trace: Mapping[str, Any]) -> str:
    return f"ptc-trace-ref://openyggdrasil/reasoning-lease/{job_id}/{trace['trace_id']}"


def _result_ref_for(job_id: str, result: Mapping[str, Any]) -> str:
    return f"reasoning-lease-result-ref://openyggdrasil/{job_id}/{result['lease_result_id']}"


def _safe_probe_payload_from_stdout(stdout: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("bubblewrap probe stdout must be JSON") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError("bubblewrap probe stdout must be an object")
    return parsed


def _safe_attempts_from_probe_payload(
    parsed: Mapping[str, Any],
    evidence_ref_prefix: str,
) -> list[dict[str, str]]:
    raw_attempts = parsed.get("attempts") if isinstance(parsed, Mapping) else None
    if not isinstance(raw_attempts, Sequence) or isinstance(raw_attempts, (str, bytes)):
        raise ValueError("bubblewrap probe stdout must include attempts")

    attempts_by_type: dict[str, Mapping[str, Any]] = {}
    for raw_attempt in raw_attempts:
        if not isinstance(raw_attempt, Mapping):
            continue
        attempt_type = str(raw_attempt.get("attempt_type") or "")
        if attempt_type in REQUIRED_BWRAP_INTRUSION_ATTEMPTS:
            attempts_by_type[attempt_type] = raw_attempt

    missing = sorted(set(REQUIRED_BWRAP_INTRUSION_ATTEMPTS) - set(attempts_by_type))
    if missing:
        raise ValueError(f"bubblewrap probe missing intrusion attempts: {missing}")

    attempts: list[dict[str, str]] = []
    for attempt_type in sorted(REQUIRED_BWRAP_INTRUSION_ATTEMPTS):
        raw_attempt = attempts_by_type[attempt_type]
        status = str(raw_attempt.get("status") or "")
        if status != "blocked":
            raise ValueError(f"bubblewrap probe did not block {attempt_type}")
        evidence_ref = str(
            raw_attempt.get("evidence_ref")
            or f"{evidence_ref_prefix}#{attempt_type}:blocked"
        )
        attempts.append(
            {
                "attempt_type": attempt_type,
                "status": status,
                "evidence_ref": evidence_ref,
            }
        )
    return attempts


def _safe_ptc_tool_plan_from_probe_payload(parsed: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    raw_plan = parsed.get("ptc_tool_plan")
    if raw_plan is None:
        return None
    if not isinstance(raw_plan, Sequence) or isinstance(raw_plan, (str, bytes)):
        raise ValueError("ptc_tool_plan must be a bounded JSON array")
    plan: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_plan, start=1):
        if not isinstance(raw_step, Mapping):
            raise ValueError("ptc_tool_plan steps must be objects")
        step = {
            "step_id": str(raw_step.get("step_id") or "").strip(),
            "capability_id": str(raw_step.get("capability_id") or "").strip(),
            "input": dict(raw_step.get("input") or {}),
        }
        if not step["step_id"] or not step["capability_id"]:
            raise ValueError(f"ptc_tool_plan step {index} requires step_id and capability_id")
        plan.append(step)
    return plan


def _run_bubblewrap_probe(
    *,
    lease_request: Mapping[str, Any],
    sandbox_decision: Mapping[str, Any],
    command: Sequence[str],
    time_budget_seconds: int,
    ptc_worker_ref: str,
    evidence_ref_prefix: str,
    popen_factory: PopenFactory,
    scratch_root: Path | None,
    clock: Clock,
) -> dict[str, Any]:
    validate_reasoning_lease_request(lease_request)
    validate_process_sandbox_runtime_decision(sandbox_decision)
    mount_root_parent = scratch_root
    if mount_root_parent is not None:
        mount_root_parent.mkdir(parents=True, exist_ok=True)
    mount_root = Path(
        tempfile.mkdtemp(
            prefix="openyggdrasil-lease-bwrap-",
            dir=str(mount_root_parent) if mount_root_parent else None,
        )
    )
    started = float(clock())
    process = None
    stdout = ""
    stderr = ""
    killed = False
    try:
        process = popen_factory(
            [str(part) for part in command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(mount_root),
        )
        try:
            stdout, stderr = process.communicate(timeout=time_budget_seconds)
        except subprocess.TimeoutExpired:
            killed = True
            if hasattr(process, "kill"):
                process.kill()
            try:
                stdout, stderr = process.communicate(timeout=1)
            except Exception:
                stdout, stderr = "", ""
            elapsed = max(0.0, float(clock()) - started)
            return {
                "runner_outcome": "time_budget_exceeded",
                "exit_code": getattr(process, "returncode", None),
                "stdout": stdout,
                "stderr": stderr,
                "elapsed_seconds": elapsed,
                "process_killed": killed,
            }
        elapsed = max(0.0, float(clock()) - started)
        exit_code = int(getattr(process, "returncode", 0))
        if exit_code != 0:
            return {
                "runner_outcome": "bubblewrap_probe_failed",
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "elapsed_seconds": elapsed,
                "process_killed": killed,
            }
        probe_payload = _safe_probe_payload_from_stdout(stdout)
        attempts = _safe_attempts_from_probe_payload(probe_payload, evidence_ref_prefix)
        ptc_tool_plan = _safe_ptc_tool_plan_from_probe_payload(probe_payload)
        trace = build_ptc_bubblewrap_isolation_trace(
            lease_request=lease_request,
            sandbox_decision=sandbox_decision,
            ptc_worker_ref=ptc_worker_ref,
            command=[str(part) for part in command],
            exit_code=exit_code,
            intrusion_attempts=attempts,
            safe_evidence_refs=[
                f"{evidence_ref_prefix}#stdout-json",
                f"{evidence_ref_prefix}#bwrap-command",
            ],
        )
        if ptc_tool_plan is not None:
            trace["reason_codes"].append("ptc_plan_generation_recorded")
            validate_reasoning_lease_ptc_bubblewrap_trace(trace)
        return {
            "runner_outcome": "bubblewrap_probe_completed",
            "exit_code": exit_code,
            "trace": trace,
            "ptc_tool_plan": ptc_tool_plan,
            "elapsed_seconds": elapsed,
            "process_killed": killed,
        }
    finally:
        shutil.rmtree(mount_root, ignore_errors=True)


def consume_reasoning_lease_mailbox_jobs(
    *,
    lease_request_resolver: ReasoningLeaseRequestResolver,
    sandbox_decision: Mapping[str, Any],
    bwrap_command: Sequence[str],
    namespace: str | None = None,
    db_path: Path | None = None,
    max_jobs: int = 1,
    ptc_worker_ref: str = DEFAULT_PTC_WORKER_REF,
    evidence_ref_prefix: str = DEFAULT_BWRAP_EVIDENCE_REF,
    popen_factory: PopenFactory | None = None,
    scratch_root: Path | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Consume queued async Reasoning Lease mailbox jobs through the PTC sandbox path."""

    validate_process_sandbox_runtime_decision(sandbox_decision)
    active_popen_factory = popen_factory or subprocess.Popen
    now = clock or time.monotonic
    pending = [
        message
        for message in read_messages(namespace=namespace, db_path=db_path)
        if _is_pending_reasoning_lease_job(message)
    ]
    selected = pending[: max(0, int(max_jobs))]
    job_results: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    spawn_attempted = False
    cleanup_verified = True

    for message in selected:
        payload = dict(message.get("payload") or {})
        job_id = str(payload.get("job_id") or message["message_id"])
        transition = _record_job_transition(
            message=message,
            to_status="queued",
            from_status=None,
            reason_code="reasoning_lease_async_job_observed",
            namespace=namespace,
            db_path=db_path,
        )
        transitions.append(transition)
        running_message = _message_with_job_status(
            message,
            mailbox_status="claimed",
            job_status="running",
            reason_code="reasoning_lease_async_consumer_started",
        )
        append_message(running_message, namespace=namespace, db_path=db_path)
        append_claim(
            message_id=str(message["message_id"]),
            consumer=ASYNC_MAILBOX_CONSUMER,
            claim_type=ASYNC_MAILBOX_CLAIM_TYPE,
            scope={"job_id": job_id},
            namespace=namespace,
            db_path=db_path,
        )
        transitions.append(
            _record_job_transition(
                message=running_message,
                to_status="running",
                from_status="queued",
                reason_code="reasoning_lease_async_consumer_started",
                namespace=namespace,
                db_path=db_path,
            )
        )

        request = dict(lease_request_resolver(message))
        validate_reasoning_lease_request(request)
        module_id = _normalize_module_id(request.get("requested_by_role"))
        requirement = _requirement_for_module(module_id)
        time_budget = _time_budget_seconds(request)
        result: dict[str, Any]
        trace_ref: str | None = None
        final_job_status = "completed"
        final_mailbox_status = "done"
        final_reason_code = "reasoning_lease_async_job_completed"

        if not _sandbox_allows_required_execution(sandbox_decision):
            trace = build_ptc_bubblewrap_typed_unavailable_trace(
                lease_request=request,
                sandbox_decision=sandbox_decision,
                ptc_worker_ref=ptc_worker_ref,
                evidence_ref=f"{evidence_ref_prefix}#typed-unavailable",
            )
            trace_ref = _trace_ref_for(job_id, trace)
            result = _unavailable_result(
                request=request,
                module_id=module_id,
                requirement=requirement,
                worker_ref=ptc_worker_ref,
                time_budget_seconds=time_budget,
                reason_code=str(sandbox_decision.get("reason_code") or "sandbox_unavailable"),
                runner_outcome="lease_security_unavailable",
                failure_reason=str(
                    sandbox_decision.get("typed_unavailable_status")
                    or "lease_security_unavailable"
                ),
                sandbox_decision=sandbox_decision,
            )
            result["output"]["execution_scope"] = "async_consumer_ptc_bubblewrap_probe"
            result["output"]["bubblewrap_trace_ref"] = trace_ref
            result["output"]["bubblewrap_trace"] = trace
            validate_reasoning_lease_result(result)
            final_job_status = "unavailable"
            final_mailbox_status = "failed"
            final_reason_code = "sandbox_unavailable_typed_unavailable"
        else:
            spawn_attempted = True
            try:
                probe = _run_bubblewrap_probe(
                    lease_request=request,
                    sandbox_decision=sandbox_decision,
                    command=bwrap_command,
                    time_budget_seconds=time_budget,
                    ptc_worker_ref=ptc_worker_ref,
                    evidence_ref_prefix=evidence_ref_prefix,
                    popen_factory=active_popen_factory,
                    scratch_root=scratch_root,
                    clock=now,
                )
            except Exception as exc:
                result = _unavailable_result(
                    request=request,
                    module_id=module_id,
                    requirement=requirement,
                    worker_ref=ptc_worker_ref,
                    time_budget_seconds=time_budget,
                    reason_code="bubblewrap_probe_spawn_or_trace_failed",
                    runner_outcome="bubblewrap_probe_spawn_or_trace_failed",
                    failure_reason=exc.__class__.__name__,
                    sandbox_decision=sandbox_decision,
                )
                result["output"]["execution_scope"] = "async_consumer_ptc_bubblewrap_probe"
                validate_reasoning_lease_result(result)
                final_job_status = "failed"
                final_mailbox_status = "failed"
                final_reason_code = "bubblewrap_probe_spawn_or_trace_failed"
            else:
                if scratch_root is not None:
                    cleanup_verified = cleanup_verified and not any(
                        scratch_root.glob("openyggdrasil-lease-bwrap-*")
                    )
                if probe["runner_outcome"] == "bubblewrap_probe_completed":
                    trace = dict(probe["trace"])
                    trace_ref = _trace_ref_for(job_id, trace)
                    output = _base_output(
                        request=request,
                        module_id=module_id,
                        requirement=requirement,
                        worker_ref=ptc_worker_ref,
                        time_budget_seconds=time_budget,
                        elapsed_seconds=float(probe["elapsed_seconds"]),
                        sandbox_decision=sandbox_decision,
                    )
                    output.update(
                        {
                            "decision": "completed",
                            "execution_scope": "async_consumer_ptc_bubblewrap_probe",
                            "runner_outcome": "bubblewrap_probe_completed",
                            "completed_output_claimed": True,
                            "isolation_proven": True,
                            "bubblewrap_trace_ref": trace_ref,
                            "bubblewrap_trace": trace,
                            "ptc_tool_plan": probe.get("ptc_tool_plan"),
                            "ptc_plan_generation_status": (
                                "generated_inside_bwrap_probe"
                                if probe.get("ptc_tool_plan") is not None
                                else "not_provided_by_probe"
                            ),
                            "mount_point_cleanup_verified": cleanup_verified,
                        }
                    )
                    result = _result(
                        request=request,
                        lease_status="completed",
                        producer_role="reasoning_lease_executor",
                        worker_ref=ptc_worker_ref,
                        output=output,
                        confidence_score=1.0,
                        failure_reason=None,
                    )
                elif probe["runner_outcome"] == "time_budget_exceeded":
                    result = _unavailable_result(
                        request=request,
                        module_id=module_id,
                        requirement=requirement,
                        worker_ref=ptc_worker_ref,
                        time_budget_seconds=time_budget,
                        reason_code="reasoning_lease_time_budget_exceeded",
                        runner_outcome="time_budget_exceeded",
                        failure_reason="reasoning_lease_time_budget_exceeded",
                        elapsed_seconds=float(probe["elapsed_seconds"]),
                        sandbox_decision=sandbox_decision,
                    )
                    result["output"]["execution_scope"] = "async_consumer_ptc_bubblewrap_probe"
                    result["output"]["process_killed"] = bool(probe["process_killed"])
                    result["output"]["mount_point_cleanup_verified"] = cleanup_verified
                    validate_reasoning_lease_result(result)
                    final_job_status = "timed_out"
                    final_mailbox_status = "failed"
                    final_reason_code = "reasoning_lease_time_budget_exceeded"
                else:
                    result = _unavailable_result(
                        request=request,
                        module_id=module_id,
                        requirement=requirement,
                        worker_ref=ptc_worker_ref,
                        time_budget_seconds=time_budget,
                        reason_code=str(probe["runner_outcome"]),
                        runner_outcome=str(probe["runner_outcome"]),
                        failure_reason=str(probe["runner_outcome"]),
                        elapsed_seconds=float(probe["elapsed_seconds"]),
                        sandbox_decision=sandbox_decision,
                    )
                    result["output"]["execution_scope"] = "async_consumer_ptc_bubblewrap_probe"
                    result["output"]["mount_point_cleanup_verified"] = cleanup_verified
                    validate_reasoning_lease_result(result)
                    final_job_status = "failed"
                    final_mailbox_status = "failed"
                    final_reason_code = str(probe["runner_outcome"])

        result_ref = _result_ref_for(job_id, result)
        final_message = _message_with_job_status(
            running_message,
            mailbox_status=final_mailbox_status,
            job_status=final_job_status,
            reason_code=final_reason_code,
            lease_result_ref=result_ref,
            bubblewrap_trace_ref=trace_ref,
        )
        append_message(final_message, namespace=namespace, db_path=db_path)
        transitions.append(
            _record_job_transition(
                message=final_message,
                to_status=final_job_status,
                from_status="running",
                reason_code=final_reason_code,
                namespace=namespace,
                db_path=db_path,
            )
        )
        job_results.append(
            {
                "job_id": job_id,
                "message_id": message["message_id"],
                "lease_request_id": result["lease_request_id"],
                "job_status": final_job_status,
                "mailbox_status": final_mailbox_status,
                "lease_result_ref": result_ref,
                "bubblewrap_trace_ref": trace_ref,
                "lease_result": result,
            }
        )

    completed = sum(1 for job in job_results if job["job_status"] == "completed")
    unavailable = sum(1 for job in job_results if job["job_status"] == "unavailable")
    timed_out = sum(1 for job in job_results if job["job_status"] == "timed_out")
    failed = sum(1 for job in job_results if job["job_status"] == "failed")
    return {
        "schema_version": ASYNC_MAILBOX_CONSUMER_SCHEMA_VERSION,
        "consumer_status": "completed",
        "mailbox_backed": True,
        "sqlite_wal_engine_required": True,
        "jobs_seen": len(pending),
        "jobs_consumed": len(job_results),
        "jobs_completed": completed,
        "jobs_unavailable": unavailable,
        "jobs_timed_out": timed_out,
        "jobs_failed": failed,
        "spawn_attempted": spawn_attempted,
        "mount_point_cleanup_verified": cleanup_verified,
        "transition_count": len(transitions),
        "transition_ids": [transition["transition_id"] for transition in transitions],
        "job_results": job_results,
    }


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
