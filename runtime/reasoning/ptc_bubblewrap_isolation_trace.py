from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso
from reasoning.process_sandbox_policy import validate_process_sandbox_runtime_decision
from reasoning.reasoning_lease_contracts import validate_reasoning_lease_request


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
TRACE_SCHEMA_PATH = CONTRACTS_ROOT / "reasoning_lease_ptc_bubblewrap_trace.v1.schema.json"
REQUIRED_INTRUSION_TYPES = {
    "workspace_escape",
    "network_escape",
    "process_escape",
}


@lru_cache(maxsize=1)
def load_reasoning_lease_ptc_bubblewrap_trace_schema() -> dict[str, Any]:
    return json.loads(TRACE_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_reasoning_lease_ptc_bubblewrap_trace(payload: Mapping[str, Any]) -> None:
    trace = dict(payload)
    jsonschema.validate(instance=trace, schema=load_reasoning_lease_ptc_bubblewrap_trace_schema())
    same_run_fields = {"same_run_id", "same_run_witness_ref", "same_run_source_kind"}
    present_same_run_fields = {field for field in same_run_fields if field in trace}
    if present_same_run_fields and present_same_run_fields != same_run_fields:
        raise ValueError("same-run Bubblewrap trace must include same_run_id, same_run_witness_ref, and same_run_source_kind")
    if trace.get("same_run_source_kind") not in (None, "physical_live_same_run"):
        raise ValueError("same-run source must be physical_live_same_run")
    attempt_types = {str(attempt["attempt_type"]) for attempt in trace["intrusion_attempts"]}
    if attempt_types != REQUIRED_INTRUSION_TYPES:
        raise ValueError("trace must include workspace, network, and process intrusion attempts")
    if trace["isolation_proven"]:
        if trace["isolation_status"] != "bubblewrap_isolation_proven":
            raise ValueError("isolation_proven requires bubblewrap_isolation_proven status")
        if trace["sandbox_backend"] != "bubblewrap":
            raise ValueError("isolation_proven requires bubblewrap backend")
        if trace["execution_decision"] != "allow_sandboxed":
            raise ValueError("isolation_proven requires allow_sandboxed execution decision")
        if trace["exit_code"] != 0:
            raise ValueError("isolation_proven requires zero exit code")
        if any(attempt["status"] != "blocked" for attempt in trace["intrusion_attempts"]):
            raise ValueError("isolation_proven requires every intrusion attempt to be blocked")
    elif trace["isolation_status"] == "bubblewrap_isolation_proven":
        raise ValueError("bubblewrap_isolation_proven status requires isolation_proven")


def _default_attempts(status: str, evidence_prefix: str) -> list[dict[str, str]]:
    return [
        {
            "attempt_type": attempt_type,
            "status": status,
            "evidence_ref": f"{evidence_prefix}#{attempt_type}",
        }
        for attempt_type in sorted(REQUIRED_INTRUSION_TYPES)
    ]


def _trace(
    *,
    lease_request: Mapping[str, Any],
    sandbox_decision: Mapping[str, Any],
    ptc_worker_ref: str,
    command: Sequence[str],
    exit_code: int | None,
    intrusion_attempts: Sequence[Mapping[str, Any]],
    safe_evidence_refs: Sequence[str],
    isolation_status: str,
    isolation_proven: bool,
    reason_codes: Sequence[str],
    started_at: str | None = None,
    completed_at: str | None = None,
    same_run_id: str | None = None,
    same_run_witness_ref: str | None = None,
    same_run_source_kind: str | None = None,
) -> dict[str, Any]:
    validate_reasoning_lease_request(lease_request)
    validate_process_sandbox_runtime_decision(sandbox_decision)
    same_run_values = [same_run_id, same_run_witness_ref, same_run_source_kind]
    if any(value is not None for value in same_run_values):
        if not all(value is not None for value in same_run_values):
            raise ValueError("same-run Bubblewrap trace requires same_run_id, same_run_witness_ref, and same_run_source_kind")
        if same_run_source_kind != "physical_live_same_run":
            raise ValueError("same-run source must be physical_live_same_run")
    timestamp = utc_now_iso()
    trace = {
        "schema_version": "reasoning_lease_ptc_bubblewrap_trace.v1",
        "trace_id": uuid.uuid4().hex,
        "lease_request_id": str(lease_request["lease_request_id"]),
        "ptc_worker_ref": str(ptc_worker_ref),
        "trace_scope": "e2e5b_ptc_bubblewrap_isolation",
        "platform": sandbox_decision["platform"],
        "sandbox_backend": sandbox_decision.get("sandbox_backend"),
        "execution_decision": sandbox_decision["execution_decision"],
        "isolation_status": isolation_status,
        "isolation_proven": isolation_proven,
        "command": [str(part) for part in command],
        "exit_code": exit_code,
        "intrusion_attempts": [dict(attempt) for attempt in intrusion_attempts],
        "safe_evidence_refs": [str(ref) for ref in safe_evidence_refs],
        "raw_transcript_copied": False,
        "foreground_context_appended": False,
        "live_provider_readiness_claimed": False,
        "reason_codes": [str(code) for code in reason_codes],
        "started_at": started_at or timestamp,
        "completed_at": completed_at or timestamp,
    }
    if same_run_id is not None and same_run_witness_ref is not None and same_run_source_kind is not None:
        trace.update(
            {
                "same_run_id": str(same_run_id),
                "same_run_witness_ref": str(same_run_witness_ref),
                "same_run_source_kind": str(same_run_source_kind),
            }
        )
        if "same_run_context_accepted_from_upstream" not in trace["reason_codes"]:
            trace["reason_codes"].append("same_run_context_accepted_from_upstream")
    validate_reasoning_lease_ptc_bubblewrap_trace(trace)
    return trace


def build_ptc_bubblewrap_typed_unavailable_trace(
    *,
    lease_request: Mapping[str, Any],
    sandbox_decision: Mapping[str, Any],
    ptc_worker_ref: str,
    evidence_ref: str,
    same_run_id: str | None = None,
    same_run_witness_ref: str | None = None,
    same_run_source_kind: str | None = None,
) -> dict[str, Any]:
    reason_code = str(sandbox_decision.get("reason_code") or "sandbox_unavailable")
    return _trace(
        lease_request=lease_request,
        sandbox_decision=sandbox_decision,
        ptc_worker_ref=ptc_worker_ref,
        command=[],
        exit_code=None,
        intrusion_attempts=_default_attempts("typed_unavailable", evidence_ref),
        safe_evidence_refs=[evidence_ref],
        isolation_status="typed_unavailable",
        isolation_proven=False,
        reason_codes=[
            "ptc_bubblewrap_trace_typed_unavailable",
            reason_code,
        ],
        same_run_id=same_run_id,
        same_run_witness_ref=same_run_witness_ref,
        same_run_source_kind=same_run_source_kind,
    )


def build_ptc_bubblewrap_isolation_trace(
    *,
    lease_request: Mapping[str, Any],
    sandbox_decision: Mapping[str, Any],
    ptc_worker_ref: str,
    command: Sequence[str],
    exit_code: int,
    intrusion_attempts: Sequence[Mapping[str, Any]],
    safe_evidence_refs: Sequence[str],
    same_run_id: str | None = None,
    same_run_witness_ref: str | None = None,
    same_run_source_kind: str | None = None,
) -> dict[str, Any]:
    return _trace(
        lease_request=lease_request,
        sandbox_decision=sandbox_decision,
        ptc_worker_ref=ptc_worker_ref,
        command=command,
        exit_code=exit_code,
        intrusion_attempts=intrusion_attempts,
        safe_evidence_refs=safe_evidence_refs,
        isolation_status="bubblewrap_isolation_proven",
        isolation_proven=True,
        reason_codes=[
            "ptc_bubblewrap_isolation_trace_recorded",
            "all_intrusion_attempts_blocked",
        ],
        same_run_id=same_run_id,
        same_run_witness_ref=same_run_witness_ref,
        same_run_source_kind=same_run_source_kind,
    )
