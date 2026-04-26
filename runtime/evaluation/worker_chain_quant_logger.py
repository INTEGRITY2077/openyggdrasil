from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

BASE_SCORE_FIELDS = ("contract_score", "test_score", "runtime_score", "live_score")
OPTIONAL_SCORE_FIELDS = {
    "sandbox_required": "sandbox_score",
    "mailbox_required": "mailbox_score",
    "graphify_required": "graphify_score",
}


def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_worker_chain_quant_logger_event_schema() -> dict[str, Any]:
    return _load_schema("worker_chain_quant_logger_event.v1.schema.json")


@lru_cache(maxsize=1)
def load_worker_chain_quant_checklist_schema() -> dict[str, Any]:
    return _load_schema("worker_chain_quant_checklist.v1.schema.json")


def validate_worker_chain_quant_logger_event(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_worker_chain_quant_logger_event_schema())


def validate_worker_chain_quant_checklist(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_worker_chain_quant_checklist_schema())


def _score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, round(numeric, 3)))


def _overall_score(payload: Mapping[str, Any]) -> float:
    score_fields = list(BASE_SCORE_FIELDS)
    for required_field, score_field in OPTIONAL_SCORE_FIELDS.items():
        if bool(payload.get(required_field)):
            score_fields.append(score_field)
    scores = [_score(payload.get(field)) for field in score_fields]
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def build_worker_chain_quant_logger_event(
    *,
    run_id: str,
    worker_id: str,
    job_chain_id: str,
    job_stage: str,
    owner_module: str,
    chain_role: str,
    implementation_state: str,
    reasoning_effort_required: str,
    reasoning_lease_required: bool,
    sandbox_required: bool,
    sandbox_runtime: str,
    mailbox_required: bool,
    graphify_required: bool,
    contract_score: float,
    test_score: float,
    runtime_score: float,
    live_score: float,
    sandbox_score: float = 0.0,
    mailbox_score: float = 0.0,
    graphify_score: float = 0.0,
    evidence_refs: Sequence[str] = (),
    blocking_gaps: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "schema_version": "worker_chain_quant_logger_event.v1",
        "run_id": str(run_id),
        "event_id": f"{run_id}:{worker_id}:quant",
        "worker_id": str(worker_id),
        "job_chain_id": str(job_chain_id),
        "job_stage": str(job_stage),
        "owner_module": str(owner_module),
        "chain_role": str(chain_role),
        "implementation_state": str(implementation_state),
        "reasoning_effort_required": str(reasoning_effort_required),
        "reasoning_lease_required": bool(reasoning_lease_required),
        "sandbox_required": bool(sandbox_required),
        "sandbox_runtime": str(sandbox_runtime),
        "mailbox_required": bool(mailbox_required),
        "graphify_required": bool(graphify_required),
        "contract_score": _score(contract_score),
        "test_score": _score(test_score),
        "runtime_score": _score(runtime_score),
        "live_score": _score(live_score),
        "sandbox_score": _score(sandbox_score),
        "mailbox_score": _score(mailbox_score),
        "graphify_score": _score(graphify_score),
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "blocking_gaps": sorted({str(gap) for gap in blocking_gaps if str(gap)}),
        "checked_at": utc_now_iso(),
    }
    payload["overall_score"] = _overall_score(payload)
    validate_worker_chain_quant_logger_event(payload)
    if not payload["reasoning_lease_required"] and payload["reasoning_effort_required"] != "none":
        raise ValueError("deterministic worker cannot require reasoning effort without lease")
    if payload["reasoning_effort_required"] == "none" and payload["reasoning_lease_required"]:
        raise ValueError("reasoning lease requires non-none effort")
    return payload


def _required_count(events: Sequence[Mapping[str, Any]], required_field: str) -> int:
    return sum(1 for event in events if bool(event.get(required_field)))


def _proven_count(events: Sequence[Mapping[str, Any]], required_field: str, score_field: str) -> int:
    return sum(
        1
        for event in events
        if bool(event.get(required_field)) and _score(event.get(score_field)) >= 1.0
    )


def build_worker_chain_quant_checklist(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checked_events = [dict(event) for event in events]
    for event in checked_events:
        validate_worker_chain_quant_logger_event(event)

    run_ids = {str(event["run_id"]) for event in checked_events}
    chain_ids = {str(event["job_chain_id"]) for event in checked_events}
    run_id = sorted(run_ids)[0] if len(run_ids) == 1 else "mixed"
    job_chain_id = sorted(chain_ids)[0] if len(chain_ids) == 1 else "mixed"
    blocking_gaps = sorted(
        {
            str(gap)
            for event in checked_events
            for gap in event.get("blocking_gaps", [])
            if str(gap)
        }
    )
    average = 0.0
    if checked_events:
        average = round(sum(_score(event.get("overall_score")) for event in checked_events) / len(checked_events), 3)
    live_proven_count = sum(
        1 for event in checked_events if str(event.get("implementation_state")) == "live_proven"
    )
    readiness_state = "ready"
    if not checked_events or blocking_gaps or average < 1.0 or live_proven_count != len(checked_events):
        readiness_state = "not_ready"

    checklist = {
        "schema_version": "worker_chain_quant_checklist.v1",
        "run_id": run_id,
        "job_chain_id": job_chain_id,
        "readiness_state": readiness_state,
        "worker_count": len(checked_events),
        "average_overall_score": average,
        "live_proven_count": live_proven_count,
        "contract_only_or_below_count": sum(
            1
            for event in checked_events
            if str(event.get("implementation_state")) in {"missing", "contract_only"}
        ),
        "sandbox_required_count": _required_count(checked_events, "sandbox_required"),
        "sandbox_proven_count": _proven_count(checked_events, "sandbox_required", "sandbox_score"),
        "mailbox_required_count": _required_count(checked_events, "mailbox_required"),
        "mailbox_proven_count": _proven_count(checked_events, "mailbox_required", "mailbox_score"),
        "graphify_required_count": _required_count(checked_events, "graphify_required"),
        "graphify_proven_count": _proven_count(checked_events, "graphify_required", "graphify_score"),
        "blocking_gaps": blocking_gaps,
        "checked_at": utc_now_iso(),
    }
    validate_worker_chain_quant_checklist(checklist)
    return checklist


def build_default_p9_worker_chain_events(*, run_id: str = "p9-live-e2e-proof") -> list[dict[str, Any]]:
    job_chain_id = "p9_live_e2e_provider_chain"
    return [
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="distiller",
            job_chain_id=job_chain_id,
            job_stage="turn_memory_distillation",
            owner_module="capture.decision_distiller",
            chain_role="distiller",
            implementation_state="tested_contract",
            reasoning_effort_required="high",
            reasoning_lease_required=True,
            sandbox_required=True,
            sandbox_runtime="typed_unavailable",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            sandbox_score=0.0,
            evidence_refs=["contracts/module_effort_requirement.v1.schema.json"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_ptc_bubblewrap_reasoning_lease_isolation",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="evaluator",
            job_chain_id=job_chain_id,
            job_stage="response_quality_review",
            owner_module="evaluation.evaluator",
            chain_role="evaluator",
            implementation_state="tested_contract",
            reasoning_effort_required="high",
            reasoning_lease_required=True,
            sandbox_required=True,
            sandbox_runtime="typed_unavailable",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            sandbox_score=0.0,
            evidence_refs=["contracts/module_effort_requirement.v1.schema.json"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_ptc_bubblewrap_reasoning_lease_isolation",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="amundsen",
            job_chain_id=job_chain_id,
            job_stage="semantic_routing",
            owner_module="admission.amundsen_stub",
            chain_role="amundsen",
            implementation_state="tested_contract",
            reasoning_effort_required="medium",
            reasoning_lease_required=True,
            sandbox_required=True,
            sandbox_runtime="typed_unavailable",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            sandbox_score=0.0,
            evidence_refs=["contracts/module_effort_plan.v1.schema.json"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_ptc_bubblewrap_reasoning_lease_isolation",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="pathfinder",
            job_chain_id=job_chain_id,
            job_stage="memory_pathfinding",
            owner_module="retrieval.pathfinder",
            chain_role="pathfinder",
            implementation_state="tested_contract",
            reasoning_effort_required="medium",
            reasoning_lease_required=True,
            sandbox_required=True,
            sandbox_runtime="typed_unavailable",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            sandbox_score=0.0,
            evidence_refs=["contracts/module_effort_plan.v1.schema.json"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_ptc_bubblewrap_reasoning_lease_isolation",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="gardener",
            job_chain_id=job_chain_id,
            job_stage="knowledge_forest_cultivation",
            owner_module="cultivation.gardener_stub",
            chain_role="gardener",
            implementation_state="runtime_implemented",
            reasoning_effort_required="none",
            reasoning_lease_required=False,
            sandbox_required=False,
            sandbox_runtime="none",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=1.0,
            live_score=0.0,
            evidence_refs=["runtime/cultivation/gardener_stub.py"],
            blocking_gaps=["missing_physical_multiturn_provider_session"],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="postman_mailbox",
            job_chain_id=job_chain_id,
            job_stage="support_bundle_mailbox_delivery",
            owner_module="delivery.postman_gateway",
            chain_role="postman_mailbox",
            implementation_state="tested_contract",
            reasoning_effort_required="none",
            reasoning_lease_required=False,
            sandbox_required=False,
            sandbox_runtime="none",
            mailbox_required=True,
            graphify_required=False,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            mailbox_score=0.0,
            evidence_refs=["runtime/delivery/postman_gateway.py"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_mailbox_to_hermes_consumption_proof",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="graphify",
            job_chain_id=job_chain_id,
            job_stage="graph_snapshot_visibility",
            owner_module="retrieval.graphify_snapshot_adapter",
            chain_role="graphify",
            implementation_state="tested_contract",
            reasoning_effort_required="none",
            reasoning_lease_required=False,
            sandbox_required=False,
            sandbox_runtime="none",
            mailbox_required=False,
            graphify_required=True,
            contract_score=1.0,
            test_score=1.0,
            runtime_score=0.5,
            live_score=0.0,
            graphify_score=0.0,
            evidence_refs=["runtime/retrieval/graphify_snapshot_adapter.py"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_graphify_snapshot_delta_proof",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="hermes_consumer",
            job_chain_id=job_chain_id,
            job_stage="provider_mailbox_consumption",
            owner_module="attachments.hermes_provider_packaging_baseline",
            chain_role="hermes_consumer",
            implementation_state="contract_only",
            reasoning_effort_required="high",
            reasoning_lease_required=True,
            sandbox_required=False,
            sandbox_runtime="none",
            mailbox_required=True,
            graphify_required=True,
            contract_score=1.0,
            test_score=0.5,
            runtime_score=0.0,
            live_score=0.0,
            mailbox_score=0.0,
            graphify_score=0.0,
            evidence_refs=["contracts/provider_attachment_manifest.v1.schema.json"],
            blocking_gaps=[
                "missing_physical_multiturn_provider_session",
                "missing_mailbox_to_hermes_consumption_proof",
                "missing_graphify_snapshot_delta_proof",
            ],
        ),
        build_worker_chain_quant_logger_event(
            run_id=run_id,
            worker_id="reasoning_lease_ptc_bubblewrap",
            job_chain_id=job_chain_id,
            job_stage="sandboxed_reasoning_lease_execution",
            owner_module="reasoning.reasoning_lease_contracts",
            chain_role="reasoning_lease_worker",
            implementation_state="contract_only",
            reasoning_effort_required="high",
            reasoning_lease_required=True,
            sandbox_required=True,
            sandbox_runtime="typed_unavailable",
            mailbox_required=False,
            graphify_required=False,
            contract_score=1.0,
            test_score=0.5,
            runtime_score=0.0,
            live_score=0.0,
            sandbox_score=0.0,
            evidence_refs=["contracts/reasoning_lease_request.v1.schema.json"],
            blocking_gaps=["missing_ptc_bubblewrap_reasoning_lease_isolation"],
        ),
    ]
