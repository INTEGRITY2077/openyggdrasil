from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.decision_contracts import validate_session_signal_runner_result
from capture.provider_runtime_integrity import evaluate_integrity_then_admission
from harness_common import utc_now_iso


RUNNER_STEPS = (
    "provider_runtime_integrity",
    "session_admission_gate",
    "thin_worker_chain",
)


def _string_field(payload: Mapping[str, Any], key: str, fallback: str = "unknown") -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def _stop_reason(
    *,
    integrity_result: Mapping[str, Any],
    admission_verdict: Mapping[str, Any] | None,
) -> str | None:
    if not integrity_result.get("admission_allowed"):
        return str(integrity_result.get("status") or "integrity_stopped")
    if admission_verdict is None:
        return "admission_missing"
    verdict = str(admission_verdict.get("verdict") or "").strip()
    if verdict == "accept":
        return None
    return verdict or "admission_stopped"


def _runner_plan(
    *,
    signal: Mapping[str, Any],
    integrity_result: Mapping[str, Any],
    admission_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "plan_version": "thin_worker_chain.plan.v0",
        "signal_id": str(signal["signal_id"]),
        "integrity_id": str(integrity_result["integrity_id"]),
        "admission_verdict_id": str(admission_verdict["verdict_id"]),
        "next_step": "thin_worker_chain",
        "role_boundaries": [
            "distiller",
            "evaluator",
            "amundsen",
            "map_maker",
            "gardener",
            "postman",
        ],
        "source_ref": signal.get("source_ref"),
        "constraints": [
            "do_not_copy_raw_provider_session",
            "use_source_refs_only",
            "do_not_mutate_mailbox_before_postman",
            "do_not_write_canonical_claim_from_provider_signal",
        ],
    }


def _source_refs(signal: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_ref = signal.get("source_ref")
    if isinstance(source_ref, Mapping):
        return [
            {
                "kind": str(source_ref.get("kind") or "provider_session"),
                "path_hint": str(source_ref.get("path_hint") or "").strip(),
                "range_hint": source_ref.get("range_hint"),
                "symlink_hint": source_ref.get("symlink_hint"),
                "message_id": None,
            }
        ]
    return [
        {
            "kind": "provider_session",
            "path_hint": "missing-source-ref",
            "range_hint": None,
            "symlink_hint": None,
            "message_id": None,
        }
    ]


def _admission_status(admission_verdict: Mapping[str, Any] | None) -> str:
    if admission_verdict is None:
        return "not_run"
    return str(admission_verdict.get("verdict") or "not_run").strip() or "not_run"


def _step_statuses(
    *,
    integrity_result: Mapping[str, Any],
    admission_verdict: Mapping[str, Any] | None,
    accepted: bool,
) -> list[dict[str, Any]]:
    integrity_allowed = bool(integrity_result.get("admission_allowed"))
    return [
        {
            "step": "provider_runtime_integrity",
            "status": "completed",
            "reason_codes": list(integrity_result.get("reason_codes") or []),
        },
        {
            "step": "session_admission_gate",
            "status": "completed" if integrity_allowed else "skipped",
            "reason_codes": list(admission_verdict.get("reason_codes") or [])
            if admission_verdict
            else [str(integrity_result.get("status") or "integrity_stopped")],
        },
        {
            "step": "thin_worker_chain",
            "status": "ready" if accepted else "blocked",
            "reason_codes": ["runner_plan_ready"] if accepted else ["runner_stopped"],
        },
    ]


def _fallback_state(
    *,
    stop_reason: str | None,
    integrity_result: Mapping[str, Any],
) -> dict[str, Any]:
    quarantine = str(integrity_result.get("status") or "") == "quarantine"
    return {
        "fallback_used": stop_reason is not None,
        "fallback_reason": stop_reason,
        "quarantine": quarantine,
    }


def run_session_signal_entrypoint(
    signal: Mapping[str, Any],
    *,
    runtime_event_labels: list[str] | tuple[str, ...] | None = None,
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    source_ref_exists: bool = True,
    duplicate_signal: bool = False,
    privacy_risk_detected: bool = False,
) -> dict[str, Any]:
    """Run R1: provider signal integrity then admission, no worker chain yet."""

    outcome = evaluate_integrity_then_admission(
        signal,
        runtime_event_labels=runtime_event_labels,
        evidence_refs=evidence_refs,
        source_ref_exists=source_ref_exists,
        duplicate_signal=duplicate_signal,
        privacy_risk_detected=privacy_risk_detected,
    )
    integrity_result = outcome["integrity_result"]
    admission_verdict = outcome["admission_verdict"]
    stop_reason = _stop_reason(
        integrity_result=integrity_result,
        admission_verdict=admission_verdict,
    )
    accepted = stop_reason is None and admission_verdict is not None
    result = {
        "schema_version": "session_signal_runner_result.v1",
        "runner_result_id": uuid.uuid4().hex,
        "signal_id": _string_field(signal, "signal_id", "invalid-signal"),
        "provider_id": _string_field(signal, "provider_id"),
        "provider_profile": _string_field(signal, "provider_profile"),
        "provider_session_id": _string_field(signal, "provider_session_id"),
        "session_uid": _string_field(signal, "session_uid"),
        "status": "runner_plan_ready" if accepted else "stopped",
        "admission_status": _admission_status(admission_verdict),
        "stop_reason": stop_reason,
        "step_statuses": _step_statuses(
            integrity_result=integrity_result,
            admission_verdict=admission_verdict,
            accepted=accepted,
        ),
        "source_refs": _source_refs(signal),
        "mailbox_packet_refs": [],
        "fallback_state": _fallback_state(
            stop_reason=stop_reason,
            integrity_result=integrity_result,
        ),
        "integrity_result": integrity_result,
        "admission_verdict": admission_verdict,
        "runner_plan": _runner_plan(
            signal=signal,
            integrity_result=integrity_result,
            admission_verdict=admission_verdict,
        )
        if accepted
        else None,
        "next_action": "run_thin_worker_chain" if accepted else "stop",
        "created_at": utc_now_iso(),
    }
    validate_session_signal_runner_result(result)
    return result


def run_session_signal_thin_chain(
    signal: Mapping[str, Any],
    *,
    runtime_event_labels: list[str] | tuple[str, ...] | None = None,
    evidence_refs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    source_ref_exists: bool = True,
    duplicate_signal: bool = False,
    privacy_risk_detected: bool = False,
    candidate_renderer: Any = None,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """Run R1 plus R2 and return both typed results."""

    from runner.thin_worker_chain import run_thin_worker_chain

    entrypoint_result = run_session_signal_entrypoint(
        signal,
        runtime_event_labels=runtime_event_labels,
        evidence_refs=evidence_refs,
        source_ref_exists=source_ref_exists,
        duplicate_signal=duplicate_signal,
        privacy_risk_detected=privacy_risk_detected,
    )
    chain_result = run_thin_worker_chain(
        signal=signal,
        runner_result=entrypoint_result,
        candidate_renderer=candidate_renderer,
        vault_root=vault_root,
    )
    return {
        "entrypoint_result": entrypoint_result,
        "chain_result": chain_result,
    }
