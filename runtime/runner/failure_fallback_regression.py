from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema

from attachments.provider_attachment import build_session_uid
from delivery.mailbox_contamination_guard import (
    MailboxGuardPolicy,
    guard_mailbox_message,
)
from delivery.packet_factory import build_graph_hint_packet
from harness_common import WORKSPACE_ROOT, utc_now_iso
from reasoning.provider_resource_boundary import (
    build_provider_headless_lease_request,
    resolve_provider_resource_request,
)
from reasoning.reasoning_lease_contracts import validate_reasoning_lease_result
from retrieval.graphify_snapshot_adapter import (
    adapt_graphify_snapshot,
    validate_graphify_snapshot_adapter_payload,
)
from runner.session_signal_runner import run_session_signal_mailbox_support


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
REGRESSION_SCHEMA_PATH = CONTRACTS_ROOT / "failure_fallback_regression_result.v1.schema.json"
FORBIDDEN_PROVIDER_PAYLOAD_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "canonical_claim",
    "mailbox_mutation",
    "sot_write",
}


@lru_cache(maxsize=1)
def load_failure_fallback_regression_result_schema() -> dict[str, Any]:
    return json.loads(REGRESSION_SCHEMA_PATH.read_text(encoding="utf-8"))


def _reject_forbidden_provider_payload_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                raise ValueError(f"failure fallback regression forbids provider payload field {path}.{key}")
            _reject_forbidden_provider_payload_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_provider_payload_keys(child, path=f"{path}[{index}]")


def validate_failure_fallback_regression_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_failure_fallback_regression_result_schema(),
    )
    _reject_forbidden_provider_payload_keys(payload)


def _default_signal() -> dict[str, Any]:
    provider_id = "hermes"
    provider_profile = "s2-regression"
    provider_session_id = "session-fallback-regression"
    return {
        "schema_version": "session_structure_signal.v1",
        "signal_id": "signal-s2-fallback-regression",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": build_session_uid(
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        ),
        "turn_range": {
            "from": 3,
            "to": 5,
        },
        "trigger_type": "boundary_trigger",
        "reason_labels": ["decision_closed"],
        "surface_reason": "Accepted boundary signal for fallback regression",
        "priority": "review",
        "source_ref": {
            "kind": "provider_session",
            "path_hint": ".yggdrasil/providers/hermes/s2-regression/session-fallback-regression/turn_delta.v1.jsonl",
            "range_hint": "turns:3-5",
            "symlink_hint": None,
        },
        "anchor_hash": "s2-fallback-regression-anchor",
        "emitted_at": utc_now_iso(),
    }


def _detail_ref(kind: str, ref: Any) -> dict[str, str]:
    return {
        "kind": kind,
        "ref": str(ref),
    }


def _scenario_error(scenario: str, expected_outcome: str, exc: Exception) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "passed": False,
        "expected_outcome": expected_outcome,
        "observed_outcome": "uncaught_exception",
        "typed_contracts": ["exception"],
        "reason_codes": [f"uncaught_exception:{exc.__class__.__name__}"],
        "provider_facing_answer": "unsafe_uncaught_exception",
        "detail_refs": [_detail_ref("exception", exc.__class__.__name__)],
    }


def _safe_scenario(
    *,
    scenario: str,
    expected_outcome: str,
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return _scenario_error(scenario, expected_outcome, exc)


def _missing_provider_background_reasoning(signal: Mapping[str, Any]) -> dict[str, Any]:
    descriptor = {
        "provider_id": signal.get("provider_id"),
        "provider_profile": signal.get("provider_profile"),
        "provider_session_id": signal.get("provider_session_id"),
        "session_uid": signal.get("session_uid"),
        "capabilities": {
            "background_reasoning": False,
        },
    }
    request = build_provider_headless_lease_request(
        provider_descriptor=descriptor,
        requested_by_role="distiller",
        job_type="decision_distillation",
        objective="Prove missing provider background reasoning falls back deterministically.",
        input_refs={
            "signal_id": signal.get("signal_id"),
            "source_ref": dict(signal.get("source_ref") or {}),
        },
        expected_output_schema="decision_candidate.v1",
    )
    lease_result = resolve_provider_resource_request(
        provider_descriptor=descriptor,
        request=request,
        fallback_output={
            "fallback_surface": "thin_worker_chain",
            "provider_answer_policy": "typed_fallback_only",
        },
    )
    validate_reasoning_lease_result(lease_result)
    reason_code = str(dict(lease_result.get("output") or {}).get("reason_code") or "")
    passed = (
        lease_result.get("lease_status") == "fallback_used"
        and lease_result.get("fallback_used") is True
        and reason_code == "provider_background_reasoning_unavailable"
    )
    return {
        "scenario": "missing_provider_background_reasoning",
        "passed": passed,
        "expected_outcome": "fallback",
        "observed_outcome": str(lease_result.get("lease_status") or "unknown"),
        "typed_contracts": ["reasoning_lease_request.v1", "reasoning_lease_result.v1"],
        "reason_codes": [reason_code or "reason_code_missing"],
        "provider_facing_answer": "typed_fallback_only" if passed else "unsafe_uncaught_exception",
        "detail_refs": [_detail_ref("lease_request_id", request["lease_request_id"])],
    }


def _missing_graphify_snapshot(*, workspace_root: Path) -> dict[str, Any]:
    scratch_root = workspace_root / ".runtime" / "failure-fallback-regression" / uuid.uuid4().hex
    scratch_root.mkdir(parents=True, exist_ok=True)
    summary_path = scratch_root / "summary.json"
    graph_path = scratch_root / "missing-graph.json"
    manifest_path = scratch_root / "missing-manifest.json"
    summary_path.write_text(
        json.dumps({"nodes": 0, "edges": 0, "communities": 0}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if graph_path.exists():
        graph_path.unlink()

    adapter_payload = adapt_graphify_snapshot(
        graph_path=graph_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        vault_root=workspace_root / "vault",
        freshness={
            "status": "missing",
            "graph_is_trusted": False,
            "reasons": ["s2_missing_graphify_snapshot"],
        },
    )
    validate_graphify_snapshot_adapter_payload(adapter_payload)
    failure = dict(adapter_payload.get("failure") or {})
    reason_code = str(failure.get("reason_code") or "")
    passed = adapter_payload.get("status") == "unavailable" and reason_code == "graphify_graph_missing"
    return {
        "scenario": "missing_graphify_snapshot",
        "passed": passed,
        "expected_outcome": "unavailable",
        "observed_outcome": str(adapter_payload.get("status") or "unknown"),
        "typed_contracts": ["graphify_snapshot_adapter.v1"],
        "reason_codes": [reason_code or "reason_code_missing"],
        "provider_facing_answer": "blocked_before_answer" if passed else "unsafe_uncaught_exception",
        "detail_refs": [
            _detail_ref("graph_path", graph_path),
            _detail_ref("summary_path", summary_path),
        ],
    }


def _stale_mailbox_packet(signal: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = dict(signal.get("source_ref") or {})
    packet = build_graph_hint_packet(
        provider_id=str(signal.get("provider_id") or "hermes"),
        profile=str(signal.get("provider_profile") or "s2-regression"),
        session_id=str(signal.get("provider_session_id") or "session-fallback-regression"),
        parent_question_id=str(signal.get("signal_id") or "signal-s2-fallback-regression"),
        topic="s2-fallback-regression",
        source_paths=[str(source_ref.get("path_hint") or "missing-source-ref")],
        facts=["Graph freshness is stale and must not be consumed as provider answer evidence."],
        human_summary="S2 stale mailbox packet regression.",
        producer="openyggdrasil-s2-fallback-regression",
    )
    packet["payload"]["graph_freshness"] = {
        "status": "stale",
        "graph_is_trusted": False,
        "reasons": ["s2_stale_mailbox_packet"],
    }
    guard_result = guard_mailbox_message(
        packet,
        policy=MailboxGuardPolicy(
            expected_provider_id=str(signal.get("provider_id") or "hermes"),
            expected_profile=str(signal.get("provider_profile") or "s2-regression"),
            expected_session_id=str(signal.get("provider_session_id") or "session-fallback-regression"),
            allowed_message_types=("graph_hint",),
        ),
    )
    reason_codes = [str(code) for code in guard_result.get("reason_codes") or []]
    passed = guard_result.get("verdict") == "quarantine" and "graph_freshness_stale" in reason_codes
    return {
        "scenario": "stale_mailbox_packet",
        "passed": passed,
        "expected_outcome": "quarantine",
        "observed_outcome": str(guard_result.get("verdict") or "unknown"),
        "typed_contracts": ["mailbox.v1", "mailbox_guard_result.v1"],
        "reason_codes": reason_codes or ["reason_code_missing"],
        "provider_facing_answer": "quarantined_before_answer" if passed else "unsafe_uncaught_exception",
        "detail_refs": [_detail_ref("message_id", packet["message_id"])],
    }


def _unresolved_source_ref(signal: Mapping[str, Any], *, workspace_root: Path) -> dict[str, Any]:
    result = run_session_signal_mailbox_support(
        signal,
        source_ref_exists=False,
        workspace_root=workspace_root,
    )
    entrypoint = dict(result.get("entrypoint_result") or {})
    admission = dict(entrypoint.get("admission_verdict") or {})
    chain = dict(result.get("chain_result") or {})
    mailbox = dict(result.get("mailbox_support_result") or {})
    reason_codes = [str(code) for code in admission.get("reason_codes") or []]
    passed = (
        entrypoint.get("status") == "stopped"
        and entrypoint.get("admission_status") == "reject"
        and "source_ref_unresolved" in reason_codes
        and chain.get("status") == "stopped"
        and mailbox.get("status") == "stopped"
    )
    return {
        "scenario": "unresolved_source_ref",
        "passed": passed,
        "expected_outcome": "reject",
        "observed_outcome": str(entrypoint.get("admission_status") or "unknown"),
        "typed_contracts": [
            "session_signal_runner_result.v1",
            "thin_worker_chain_result.v1",
            "mailbox_support_result.v1",
        ],
        "reason_codes": reason_codes or ["reason_code_missing"],
        "provider_facing_answer": "rejected_before_answer" if passed else "unsafe_uncaught_exception",
        "detail_refs": [
            _detail_ref("runner_result_id", entrypoint.get("runner_result_id")),
            _detail_ref("chain_result_id", chain.get("chain_result_id")),
            _detail_ref("emission_result_id", mailbox.get("emission_result_id")),
        ],
    }


def run_failure_fallback_regression(
    *,
    signal: Mapping[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Run S2 failure probes and return a typed regression result.

    The result summarizes validated typed contracts only. It does not expose
    provider raw sessions or plain exception text as provider-facing output.
    """

    active_signal = dict(signal or _default_signal())
    active_workspace = (workspace_root or WORKSPACE_ROOT).resolve()
    scenario_results = [
        _safe_scenario(
            scenario="missing_provider_background_reasoning",
            expected_outcome="fallback",
            fn=lambda: _missing_provider_background_reasoning(active_signal),
        ),
        _safe_scenario(
            scenario="missing_graphify_snapshot",
            expected_outcome="unavailable",
            fn=lambda: _missing_graphify_snapshot(workspace_root=active_workspace),
        ),
        _safe_scenario(
            scenario="stale_mailbox_packet",
            expected_outcome="quarantine",
            fn=lambda: _stale_mailbox_packet(active_signal),
        ),
        _safe_scenario(
            scenario="unresolved_source_ref",
            expected_outcome="reject",
            fn=lambda: _unresolved_source_ref(active_signal, workspace_root=active_workspace),
        ),
    ]
    uncaught_exception_count = sum(
        1 for row in scenario_results if row.get("observed_outcome") == "uncaught_exception"
    )
    passed = all(bool(row.get("passed")) for row in scenario_results)
    result = {
        "schema_version": "failure_fallback_regression_result.v1",
        "regression_result_id": uuid.uuid4().hex,
        "status": "passed" if passed else "failed",
        "scenario_results": scenario_results,
        "uncaught_exception_count": uncaught_exception_count,
        "provider_facing_answer_policy": "never_emit_uncaught_exception_as_answer",
        "next_action": "same_session_answer_smoke" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_failure_fallback_regression_result(result)
    return result
