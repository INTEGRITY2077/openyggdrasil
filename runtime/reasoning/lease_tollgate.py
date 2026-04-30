from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any, Mapping

from delivery.mailbox_store import read_messages
from reasoning.chain_bundle_policy import normalize_module_id, select_chain_bundle_policy
from reasoning.process_sandbox_policy import validate_process_sandbox_runtime_decision
from reasoning.reasoning_lease_contracts import (
    REASONING_LEASE_MAILBOX_JOB_SCHEMA_VERSION,
    validate_reasoning_lease_request,
)


TRACE_SCHEMA_VERSION = "reasoning_tollgate_bundle_trace.v1"
JOB_SCHEMA_VERSION = REASONING_LEASE_MAILBOX_JOB_SCHEMA_VERSION
MESSAGE_TYPE = "execute_deep_search"
INGRESS_CHAIN_ID = "ingress_chain"
INGRESS_MODULES = {"distiller", "evaluator", "amundsen"}


def _is_pending_job(message: Mapping[str, Any]) -> bool:
    payload = message.get("payload")
    return (
        message.get("message_type") == MESSAGE_TYPE
        and message.get("kind") == "command"
        and message.get("status") == "new"
        and isinstance(payload, Mapping)
        and payload.get("schema_version") == JOB_SCHEMA_VERSION
        and payload.get("job_status") == "queued"
    )


def _sandbox_allows(sandbox_decision: Mapping[str, Any]) -> bool:
    validate_process_sandbox_runtime_decision(sandbox_decision)
    return sandbox_decision.get("execution_decision") == "allow_sandboxed"


def _safe_request_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lease_request_id": str(request["lease_request_id"]),
        "requested_by_role": normalize_module_id(request.get("requested_by_role")),
        "job_type": str(request.get("job_type") or ""),
        "priority": str(request.get("priority") or ""),
        "input_ref_count": len(dict(request.get("input_refs") or {})),
        "time_budget_seconds": int(request.get("time_budget_seconds") or 0),
    }


def build_ingress_chain_tollgate_trace(
    *,
    lease_requests: Sequence[Mapping[str, Any]],
    sandbox_decision: Mapping[str, Any],
    bwrap_command: Sequence[str],
    job_ids: Sequence[str] = (),
    collection_window_ms: int | None = None,
    popen_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    requests = [dict(request) for request in lease_requests]
    for request in requests:
        validate_reasoning_lease_request(request)
    requested_modules = [normalize_module_id(request.get("requested_by_role")) for request in requests]
    policy = select_chain_bundle_policy(requested_modules)
    if policy is None or policy["chain_id"] != INGRESS_CHAIN_ID:
        raise ValueError("only active ingress chain lease requests can be bundled in Phase 4")

    ordered_modules = [module_id for module_id in policy["module_ids"] if module_id in set(requested_modules)]
    total_budget = sum(int(request.get("time_budget_seconds") or 0) for request in requests)
    max_budget = int(policy["max_time_budget_seconds"])
    budget_status = "within_budget" if total_budget <= max_budget else "exceeds_budget"
    reason_codes = ["ingress_chain_bundle_selected", f"budget_gate:{budget_status}"]
    started = time.monotonic()
    bundle_status, failure_reason = "ready_for_consumer", None
    spawn_attempted, bwrap_session_count = False, 0

    if budget_status != "within_budget":
        bundle_status, failure_reason = "rejected", "ingress_chain_budget_exceeded"
        reason_codes.append("ingress_chain_budget_exceeded")
    elif not _sandbox_allows(sandbox_decision):
        bundle_status = "typed_unavailable"
        failure_reason = str(sandbox_decision.get("typed_unavailable_status") or "lease_security_unavailable")
        reason_codes.append("bwrap_unavailable_typed_fail_closed")
    else:
        spawn_attempted, bwrap_session_count = True, 1
        process = (popen_factory or subprocess.Popen)(
            list(bwrap_command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        process.communicate(timeout=max(1, min(total_budget, max_budget)))
        bundle_status = "completed"
        reason_codes.append("single_bwrap_session_spawned")

    trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": f"tollgate-{uuid.uuid4().hex}",
        "chain_id": INGRESS_CHAIN_ID,
        "bundle_status": bundle_status,
        "jobs_bundled": len(requests),
        "job_ids": [str(job_id) for job_id in job_ids],
        "lease_request_ids": [str(request["lease_request_id"]) for request in requests],
        "sequential_module_order": ordered_modules,
        "collection_window_ms": int(collection_window_ms or policy["collection_window_ms"]),
        "combined_time_budget_seconds": total_budget,
        "max_time_budget_seconds": max_budget,
        "budget_gate_status": budget_status,
        "single_bwrap_session_required": True,
        "spawn_attempted": spawn_attempted,
        "bwrap_session_count": bwrap_session_count,
        "sandbox_execution_decision": sandbox_decision.get("execution_decision"),
        "failure_reason": failure_reason,
        "safe_request_summaries": [_safe_request_summary(request) for request in requests],
        "elapsed_ms": max(0, int((time.monotonic() - started) * 1000)),
        "reason_codes": reason_codes,
    }
    validate_ingress_chain_tollgate_trace(trace)
    return trace


def consume_ingress_chain_tollgate_mailbox_jobs(
    *,
    lease_request_resolver: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    sandbox_decision: Mapping[str, Any],
    bwrap_command: Sequence[str],
    namespace: str | None = None,
    db_path: Any = None,
    max_jobs: int = 3,
    popen_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    pending = [message for message in read_messages(namespace=namespace, db_path=db_path) if _is_pending_job(message)]
    selected_messages: list[Mapping[str, Any]] = []
    requests: list[dict[str, Any]] = []
    for message in pending:
        request = dict(lease_request_resolver(message))
        if normalize_module_id(request.get("requested_by_role")) in INGRESS_MODULES:
            selected_messages.append(message)
            requests.append(request)
        if len(requests) >= max_jobs:
            break

    trace = build_ingress_chain_tollgate_trace(
        lease_requests=requests,
        sandbox_decision=sandbox_decision,
        bwrap_command=bwrap_command,
        job_ids=[str(message.get("payload", {}).get("job_id") or message["message_id"]) for message in selected_messages],
        popen_factory=popen_factory,
    )
    return {
        "schema_version": "reasoning_tollgate_mailbox_result.v1",
        "mailbox_backed": True,
        "jobs_bundled": trace["jobs_bundled"],
        "chain_id": trace["chain_id"],
        "bundle_status": trace["bundle_status"],
        "spawn_attempted": trace["spawn_attempted"],
        "bwrap_session_count": trace["bwrap_session_count"],
        "bundle_trace": trace,
    }


def validate_ingress_chain_tollgate_trace(trace: Mapping[str, Any]) -> None:
    if trace.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise ValueError("invalid tollgate trace schema_version")
    if trace.get("chain_id") != INGRESS_CHAIN_ID or not trace.get("single_bwrap_session_required"):
        raise ValueError("invalid ingress chain tollgate trace")
    if int(trace.get("jobs_bundled") or 0) < 1:
        raise ValueError("ingress chain tollgate requires at least one bundled job")
    if trace.get("budget_gate_status") != "within_budget" and trace.get("bundle_status") != "rejected":
        raise ValueError("over-budget tollgate traces must be rejected")
    if trace.get("bundle_status") == "typed_unavailable" and trace.get("spawn_attempted") is not False:
        raise ValueError("typed unavailable tollgate traces must not spawn bwrap")
    if trace.get("bundle_status") == "completed" and int(trace.get("bwrap_session_count") or 0) != 1:
        raise ValueError("completed tollgate traces must use exactly one bwrap session")
