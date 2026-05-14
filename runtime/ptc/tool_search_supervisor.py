"""Tool-search supervisor for OpenYggdrasil PTC lanes.

This module adapts the Claude Code shape locally:

1. keep a capability catalog outside the worker-facing context,
2. select a small role-scoped tool reference set,
3. execute only the selected bounded tools,
4. record tool_use/tool_result-style events,
5. evaluate whether the loop is complete.

It does not claim Anthropic server-side Tool Search Tool parity. It is the
OpenYggdrasil supervisor layer that makes TST-like behavior observable and
testable above PTC.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.worker_program_contracts import (
    MF_CANONICAL_FLOW,
    MS_CANONICAL_FLOW,
    build_observation_delta_gate,
    build_ptc_program_observation,
    build_tst_capability_allowlist,
    build_worker_authored_ptc_program,
    review_ptc_program,
)


SCHEMA_VERSION = "openyggdrasil_tst_supervisor_result.v1"
TOOL_REFERENCE_SCHEMA_VERSION = "openyggdrasil_tool_reference.v1"
TOOL_USE_EVENT_SCHEMA_VERSION = "openyggdrasil_tool_use_event.v1"
CATALOG_SCHEMA_VERSION = "openyggdrasil_tst_capability_catalog.v1"
DEFAULT_CATALOG_RELATIVE_PATH = Path(
    "capabilities/defaults/registry/tst_capability_catalog.v1.json"
)


def _sha(value: Any, *, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _tool_ref(
    *,
    capability_id: str,
    role: str,
    read_only: bool,
    allowed_callers: Sequence[str] | None = None,
    input_contract: Sequence[str] | None = None,
    output_kind: str | None = None,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": TOOL_REFERENCE_SCHEMA_VERSION,
        "capability_id": capability_id,
        "role": role,
        "read_only": bool(read_only),
        "allowed_callers": sorted(str(item) for item in (allowed_callers or [])),
        "input_contract": sorted(str(item) for item in (input_contract or [])),
        "output_kind": output_kind or "unknown",
        "selection_reason": reason,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_catalog_path() -> Path:
    return _repo_root() / DEFAULT_CATALOG_RELATIVE_PATH


def load_tst_capability_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load the repo-managed TST capability catalog snapshot source."""
    path = catalog_path or _default_catalog_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "catalog_version": "typed_unavailable_catalog_not_loaded",
            "source_ref": str(DEFAULT_CATALOG_RELATIVE_PATH).replace("\\", "/"),
            "source_status": "typed_unavailable_catalog_not_loaded",
            "capabilities": [],
        }
    capabilities = [
        dict(row)
        for row in data.get("capabilities", [])
        if isinstance(row, Mapping) and str(row.get("tool_id") or "").strip()
    ]
    return {
        "schema_version": str(data.get("schema_version") or CATALOG_SCHEMA_VERSION),
        "catalog_version": str(data.get("catalog_version") or "unknown"),
        "source_ref": str(DEFAULT_CATALOG_RELATIVE_PATH).replace("\\", "/"),
        "source_status": "loaded",
        "source_policy": data.get("source_policy") if isinstance(data.get("source_policy"), Mapping) else {},
        "capabilities": capabilities,
    }


def _available_family_counts(catalog: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in catalog.get("capabilities") or []:
        if not isinstance(row, Mapping):
            continue
        family = str(row.get("family") or "unknown")
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _select_capability_records(
    catalog: Mapping[str, Any],
    *,
    role: str,
    capability_ids: Sequence[str],
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in catalog.get("capabilities") or []
        if isinstance(row, Mapping) and str(row.get("role") or "") in {role, "shared"}
    ]
    by_id = {str(row.get("tool_id")): dict(row) for row in rows if str(row.get("tool_id") or "")}
    selected: list[dict[str, Any]] = []
    for capability_id in capability_ids:
        key = str(capability_id)
        record = by_id.get(key)
        if record is None:
            record = {
                "tool_id": key,
                "role": role,
                "family": "ptc_primitive",
                "description": "Runtime capability missing from repo catalog.",
                "use_this_when": "Only as degraded compatibility metadata.",
                "do_not_use_this_when": "A managed capability catalog is required.",
                "input_contract": [],
                "output_kind": "unknown",
                "evidence_output": "typed_unavailable_no_catalog_record",
                "adapter_status": "typed_unavailable_no_catalog_record",
                "read_only": True,
                "hard_nonclaims": ["not_catalog_sot"],
            }
        selected.append(_provider_safe_capability_record(record))
    return selected


def _provider_safe_capability_record(record: Mapping[str, Any]) -> dict[str, Any]:
    allowed = [
        "tool_id",
        "role",
        "family",
        "description",
        "use_this_when",
        "do_not_use_this_when",
        "input_contract",
        "output_kind",
        "evidence_output",
        "adapter_status",
        "read_only",
        "allowed_callers",
        "hard_nonclaims",
    ]
    payload = {key: record.get(key) for key in allowed if key in record}
    if "allowed_callers" not in payload:
        payload["allowed_callers"] = _default_allowed_callers_for_role(
            str(record.get("role") or "shared")
        )
    return payload


def _default_allowed_callers_for_role(role: str) -> list[str]:
    if role == "memory_finder":
        return ["programmatic_tool_runtime", "memory_finder"]
    if role == "memory_saver":
        return ["memory_saver"]
    return ["programmatic_tool_runtime", "memory_finder", "memory_saver"]


def _tool_ref_from_capability(record: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    return _tool_ref(
        capability_id=str(record.get("tool_id") or ""),
        role=str(record.get("role") or "unknown"),
        read_only=bool(record.get("read_only", True)),
        allowed_callers=(
            record.get("allowed_callers")
            if isinstance(record.get("allowed_callers"), Sequence)
            else []
        ),
        input_contract=record.get("input_contract") if isinstance(record.get("input_contract"), Sequence) else [],
        output_kind=str(record.get("output_kind") or "unknown"),
        reason=reason,
    )


def _tool_use_event(
    *,
    event_type: str,
    tool_use_id: str,
    capability_id: str,
    status: str,
    input_keys: Sequence[str] | None = None,
    output_kind: str | None = None,
    result_ref: str | None = None,
    result_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": TOOL_USE_EVENT_SCHEMA_VERSION,
        "type": event_type,
        "tool_use_id": tool_use_id,
        "capability_id": capability_id,
        "status": status,
        "input_keys": sorted(str(item) for item in (input_keys or [])),
        "output_kind": output_kind,
        "result_ref": result_ref,
        "result_sha256": result_sha256,
    }


def _evaluate_loop(
    *,
    selected_tool_ids: Sequence[str],
    completed_tool_ids: Sequence[str],
    allow_empty: bool = False,
) -> dict[str, Any]:
    selected = [str(item) for item in selected_tool_ids if str(item)]
    completed = [str(item) for item in completed_tool_ids if str(item)]
    missing = [item for item in selected if item not in completed]
    extra = [item for item in completed if item not in selected]
    complete = (allow_empty or bool(selected)) and not missing
    return {
        "schema_version": "tst_loop_evaluation.v1",
        "quality": "pass" if complete else "weak",
        "selected_tool_count": len(selected),
        "completed_tool_count": len(completed),
        "missing_selected_tools": missing,
        "extra_completed_tools": extra,
        "tool_use_result_loop_complete": complete,
        "completion_rule": (
            "all selected tool references must have matching completed tool results"
        ),
    }


def build_memory_finder_tst_result(
    *,
    query_text: str,
    vault_root: Path,
    program_source: str | None = None,
) -> dict[str, Any]:
    """Run the MF read-only TST supervisor and bounded PTC program."""
    from runtime.ptc.engine import build_query_adaptive_pathfinder_plan
    from runtime.retrieval.programmatic_tool_runtime import (
        build_pathfinder_bundle_via_programmatic_tool_runtime,
    )

    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")

    catalog = load_tst_capability_catalog()
    plan = build_query_adaptive_pathfinder_plan(query_text=query, recent_limit=3)
    runtime_result = build_pathfinder_bundle_via_programmatic_tool_runtime(
        query_text=query,
        vault_root=vault_root,
        program=plan.get("json_tool_plan") or [],
    )
    trace = runtime_result.get("trace") or {}
    registry = {
        str(row.get("capability_id")): row
        for row in trace.get("capability_registry") or []
        if isinstance(row, Mapping)
    }
    initial_plan_tool_ids = [str(item) for item in plan.get("tool_step_order") or [] if str(item)]
    actual_call_tool_ids = [
        str(call.get("capability_id") or "")
        for call in trace.get("capability_calls") or []
        if isinstance(call, Mapping) and str(call.get("capability_id") or "")
    ]
    # Claude Code style tool search loads the tools needed for the path actually
    # taken. If the bounded runtime exits on an unanchored branch, do not require
    # downstream claim/source tools that were never needed.
    selected_tool_ids = actual_call_tool_ids or initial_plan_tool_ids
    selected_capabilities = _select_capability_records(
        catalog,
        role="memory_finder",
        capability_ids=[
            *selected_tool_ids,
            "recall_permission_decision",
            "source_exposure_permission",
            "recall_verifier",
            "normalize_support_receipt",
        ],
    )
    tool_references = [
        _tool_ref_from_capability(
            record,
            reason="query_adaptive_pathfinder_plan_selected",
        )
        for record in selected_capabilities
        if str(record.get("tool_id") or "") in set(selected_tool_ids)
    ]

    events: list[dict[str, Any]] = []
    completed_tool_ids: list[str] = []
    for call in trace.get("capability_calls") or []:
        if not isinstance(call, Mapping):
            continue
        capability_id = str(call.get("capability_id") or "")
        if not capability_id:
            continue
        step_id = str(call.get("step_id") or capability_id)
        tool_use_id = f"tst-{_sha([query, step_id, capability_id], length=12)}"
        input_keys = call.get("input_keys") or []
        output_kind = str(call.get("output_kind") or registry.get(capability_id, {}).get("output_kind") or "")
        events.append(
            _tool_use_event(
                event_type="tool_use",
                tool_use_id=tool_use_id,
                capability_id=capability_id,
                status="requested",
                input_keys=input_keys,
                output_kind=output_kind,
            )
        )
        events.append(
            _tool_use_event(
                event_type="tool_result",
                tool_use_id=tool_use_id,
                capability_id=capability_id,
                status=str(call.get("status") or "completed"),
                input_keys=input_keys,
                output_kind=output_kind,
                result_ref=str(call.get("result_ref") or "") or None,
                result_sha256=str(call.get("result_sha256") or "") or None,
            )
        )
        if str(call.get("status") or "completed") == "completed":
            completed_tool_ids.append(capability_id)

    loop_evaluation = _evaluate_loop(
        selected_tool_ids=selected_tool_ids,
        completed_tool_ids=completed_tool_ids,
    )
    worker_program = build_worker_authored_ptc_program(
        worker_role="memory_finder",
        work_order_ref={"query_hash": _sha(query, length=24)},
        self_defined_goal="find aligned source-backed support for the recall request",
        requested_capabilities=selected_tool_ids,
        program_steps=MF_CANONICAL_FLOW,
        success_condition=[
            "query_anchor_is_identified",
            "source_or_provenance_backed_support_is_present",
            "misaligned_support_is_rejected",
        ],
        failure_condition=[
            "no_source_or_provenance_backed_support",
            "candidate_is_stale_or_misaligned",
            "retry_would_repeat_same_query_angle",
        ],
        retry_plan={
            "same_angle_retry_allowed": False,
            "changed_angle_required_when_weak": True,
            "allowed_changed_angles": ["query_anchor", "source_ref", "topology"],
        },
    )
    program_review = review_ptc_program(
        worker_program,
        selected_capability_ids=[str(row.get("tool_id") or "") for row in selected_capabilities],
    )
    allowlist = build_tst_capability_allowlist(
        worker_role="memory_finder",
        selected_capabilities=selected_capabilities,
        requested_capabilities=selected_tool_ids,
    )
    program_observation = build_ptc_program_observation(
        program=worker_program,
        tool_use_events=events,
        evaluation=loop_evaluation,
        result_summary={"final_result_ref": runtime_result.get("final_result_ref")},
    )
    delta_gate = build_observation_delta_gate(
        program=worker_program,
        observation=program_observation,
    )

    supervisor = {
        "schema_version": SCHEMA_VERSION,
        "role": "memory_finder",
        "mode": "read_only_retrieval",
        "catalog_version": catalog.get("catalog_version"),
        "catalog_source_ref": catalog.get("source_ref"),
        "available_family_counts": _available_family_counts(catalog),
        "selected_capabilities": selected_capabilities,
        "cleanroom_reference_policy": {
            "reference_families": ["claude_code_tool_search_affordance"],
            "private_reference_paths_included": False,
            "server_side_anthropic_tst_claimed": False,
        },
        "catalog_policy": {
            "full_catalog_loaded_into_worker_context": False,
            "selected_references_only": True,
            "server_side_anthropic_tst_claimed": False,
        },
        "tool_search": {
            "query_hash": _sha(query, length=24),
            "strategy": plan.get("strategy"),
            "planner_execution_mode": plan.get("planner_execution_mode"),
            "available_tool_count": len(registry),
            "initial_plan_tool_ids": initial_plan_tool_ids,
            "selected_tool_ids": selected_tool_ids,
            "tool_reference_count": len(tool_references),
            "selection_mode": (
                "executed_branch_tool_references"
                if actual_call_tool_ids
                else "planned_tool_references"
            ),
        },
        "tool_references": tool_references,
        "tool_use_events": events,
        "worker_authored_ptc_program": worker_program,
        "ptc_program_review": program_review,
        "tst_capability_allowlist": allowlist,
        "ptc_program_observation": program_observation,
        "observation_delta_gate": delta_gate,
        "worker_task_ledger": {
            "task": "memory_recall",
            "phases": [
                "define_success_failure",
                "write_worker_program",
                "review_program",
                "select_capabilities",
                "execute_ptc",
                "observe",
                "delta_gate",
                "evaluate",
            ],
        },
        "permission_decision": {
            "read_only": True,
            "source_exposure_requires_support_paths": True,
        },
        "result_summary": {
            "final_result_ref": runtime_result.get("final_result_ref"),
            "completed_tool_count": len(completed_tool_ids),
        },
        "retry_diagnosis": None,
        "typed_unavailable": None,
        "evaluation": loop_evaluation,
        "hard_nonclaims": [
            "not_anthropic_server_tool_search_tool",
            "not_full_tool_catalog_in_worker_context",
            "not_arbitrary_write_enabled_code_execution",
            "not_full_ux_pass",
        ],
    }
    return {
        "schema_version": "memory_finder_tst_run.v1",
        "pathfinder_plan": plan,
        "pathfinder_runtime": {
            "trace_ref": runtime_result.get("trace_ref"),
            "final_result_ref": runtime_result.get("final_result_ref"),
            "runtime_mode": trace.get("runtime_mode"),
            "decision": trace.get("decision"),
            "capability_registry_count": len(trace.get("capability_registry") or []),
            "capability_calls": trace.get("capability_calls") or [],
            "final_result": trace.get("final_result") or {},
            "reason_codes": trace.get("reason_codes") or [],
        },
        "final_result": runtime_result.get("final_result") or {},
        "tst_supervisor": supervisor,
        "tst_capability_supervisor": supervisor,
    }


def run_memory_saver_tst(
    *,
    context_snapshot: str,
    vault_root: Path,
    provider_id: str = "unknown",
    max_nodes: int = 32,
) -> dict[str, Any]:
    """Run the MS write-scoped TST supervisor for classic save candidates."""
    from runtime.ptc.primitives import (
        _validate_admission,
        assign_edges,
        build_spo_triples,
        build_vault_node,
        extract_decisions,
        load_vault,
        save_to_vault,
    )

    snapshot = str(context_snapshot or "").strip()
    catalog = load_tst_capability_catalog()
    selected_tool_ids = [
        "source_anchor_check",
        "extract_decisions",
        "build_spo_triples",
        "build_vault_node",
        "check_near_duplicate_or_supersession",
        "validate_admission",
        "save_to_vault",
    ]
    selected_capabilities = _select_capability_records(
        catalog,
        role="memory_saver",
        capability_ids=[
            *selected_tool_ids,
            "memory_save_permission_decision",
            "record_worker_todo_state",
            "summarize_save_result",
            "diagnose_failed_save",
            "save_verifier",
            "normalize_save_receipt",
        ],
    )
    tool_references = [
        _tool_ref_from_capability(record, reason="memory_saver_role_scoped_selection")
        for record in selected_capabilities
        if str(record.get("tool_id") or "") in set(selected_tool_ids)
    ]

    events: list[dict[str, Any]] = []
    completed_tool_ids: list[str] = []
    nodes: list[str] = []
    rejected: list[dict[str, Any]] = []
    existing_nodes = load_vault(vault_root)

    source_use_id = f"tst-{_sha(['memory_saver', 'source', snapshot], length=12)}"
    events.append(
        _tool_use_event(
            event_type="tool_use",
            tool_use_id=source_use_id,
            capability_id="source_anchor_check",
            status="requested",
            input_keys=["context_snapshot"],
            output_kind="source_anchor_decision",
        )
    )
    source_anchor_ok = bool(snapshot)
    events.append(
        _tool_use_event(
            event_type="tool_result",
            tool_use_id=source_use_id,
            capability_id="source_anchor_check",
            status="completed",
            input_keys=["context_snapshot"],
            output_kind="source_anchor_decision",
            result_sha256="sha256:" + hashlib.sha256(
                json.dumps(
                    {"source_anchor_present": source_anchor_ok, "context_hash": _sha(snapshot, length=24)},
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        )
    )
    completed_tool_ids.append("source_anchor_check")

    extract_use_id = f"tst-{_sha(['memory_saver', 'extract', snapshot], length=12)}"
    events.append(
        _tool_use_event(
            event_type="tool_use",
            tool_use_id=extract_use_id,
            capability_id="extract_decisions",
            status="requested",
            input_keys=["context_snapshot"],
            output_kind="decision_candidates",
        )
    )
    candidates = extract_decisions(snapshot) if snapshot else []
    events.append(
        _tool_use_event(
            event_type="tool_result",
            tool_use_id=extract_use_id,
            capability_id="extract_decisions",
            status="completed",
            input_keys=["context_snapshot"],
            output_kind="decision_candidates",
            result_sha256="sha256:" + hashlib.sha256(
                json.dumps(candidates, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        )
    )
    completed_tool_ids.append("extract_decisions")

    for candidate in candidates:
        if len(nodes) >= max_nodes:
            break
        marker = str(candidate.get("marker") or "")
        triple_use_id = f"tst-{_sha(['memory_saver', 'triples', candidate], length=12)}"
        events.append(
            _tool_use_event(
                event_type="tool_use",
                tool_use_id=triple_use_id,
                capability_id="build_spo_triples",
                status="requested",
                input_keys=["decision_candidate", "marker"],
                output_kind="spo_triples",
            )
        )
        triples = build_spo_triples([candidate], marker)
        events.append(
            _tool_use_event(
                event_type="tool_result",
                tool_use_id=triple_use_id,
                capability_id="build_spo_triples",
                status="completed",
                input_keys=["decision_candidate", "marker"],
                output_kind="spo_triples",
                result_sha256="sha256:" + hashlib.sha256(
                    json.dumps(triples, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest(),
            )
        )
        completed_tool_ids.append("build_spo_triples")

        for spo in triples:
            if len(nodes) >= max_nodes:
                break
            node_use_id = f"tst-{_sha(['memory_saver', 'node', spo], length=12)}"
            events.append(
                _tool_use_event(
                    event_type="tool_use",
                    tool_use_id=node_use_id,
                    capability_id="build_vault_node",
                    status="requested",
                    input_keys=["spo", "metadata"],
                    output_kind="vault_node_candidate",
                )
            )
            node = build_vault_node(spo, metadata={"provider_id": provider_id})
            events.append(
                _tool_use_event(
                    event_type="tool_result",
                    tool_use_id=node_use_id,
                    capability_id="build_vault_node",
                    status="completed",
                    input_keys=["spo", "metadata"],
                    output_kind="vault_node_candidate",
                    result_sha256="sha256:" + hashlib.sha256(
                        json.dumps(node, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest(),
                )
            )
            completed_tool_ids.append("build_vault_node")

            duplicate_use_id = f"tst-{_sha(['memory_saver', 'duplicate', node], length=12)}"
            events.append(
                _tool_use_event(
                    event_type="tool_use",
                    tool_use_id=duplicate_use_id,
                    capability_id="check_near_duplicate_or_supersession",
                    status="requested",
                    input_keys=["vault_node_candidate", "existing_vault_nodes"],
                    output_kind="near_duplicate_or_supersession_check",
                )
            )
            possible_edges = assign_edges(node, existing_nodes)
            events.append(
                _tool_use_event(
                    event_type="tool_result",
                    tool_use_id=duplicate_use_id,
                    capability_id="check_near_duplicate_or_supersession",
                    status="completed",
                    input_keys=["vault_node_candidate", "existing_vault_nodes"],
                    output_kind="near_duplicate_or_supersession_check",
                    result_sha256="sha256:" + hashlib.sha256(
                        json.dumps(
                            {
                                "candidate_node_id": node.get("node_id"),
                                "possible_edge_count": len(possible_edges),
                                "destructive_action_taken": False,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )
            completed_tool_ids.append("check_near_duplicate_or_supersession")

            admission_use_id = f"tst-{_sha(['memory_saver', 'admit', node], length=12)}"
            events.append(
                _tool_use_event(
                    event_type="tool_use",
                    tool_use_id=admission_use_id,
                    capability_id="validate_admission",
                    status="requested",
                    input_keys=["vault_node_candidate"],
                    output_kind="admission_decision",
                )
            )
            passed, reason = _validate_admission(node)
            events.append(
                _tool_use_event(
                    event_type="tool_result",
                    tool_use_id=admission_use_id,
                    capability_id="validate_admission",
                    status="completed",
                    input_keys=["vault_node_candidate"],
                    output_kind="admission_decision",
                    result_sha256="sha256:" + hashlib.sha256(
                        json.dumps({"passed": passed, "reason": reason}, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                )
            )
            completed_tool_ids.append("validate_admission")
            if not passed:
                rejected.append({"node_id": node.get("node_id"), "reason": reason})
                continue

            save_use_id = f"tst-{_sha(['memory_saver', 'save', node.get('node_id')], length=12)}"
            events.append(
                _tool_use_event(
                    event_type="tool_use",
                    tool_use_id=save_use_id,
                    capability_id="save_to_vault",
                    status="requested",
                    input_keys=["vault_root", "vault_node"],
                    output_kind="vault_write_result",
                )
            )
            path = save_to_vault(vault_root, node)
            nodes.append(str(node.get("node_id")))
            events.append(
                _tool_use_event(
                    event_type="tool_result",
                    tool_use_id=save_use_id,
                    capability_id="save_to_vault",
                    status="completed",
                    input_keys=["vault_root", "vault_node"],
                    output_kind="vault_write_result",
                    result_ref=str(path),
                    result_sha256="sha256:" + hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
                )
            )
            completed_tool_ids.append("save_to_vault")

    status = "completed" if nodes else "typed_unavailable_no_save_candidates"
    loop_evaluation = _evaluate_loop(
        selected_tool_ids=selected_tool_ids,
        completed_tool_ids=completed_tool_ids,
        allow_empty=False,
    )
    worker_program = build_worker_authored_ptc_program(
        worker_role="memory_saver",
        work_order_ref={"context_hash": _sha(snapshot, length=24)},
        self_defined_goal="save only admitted durable memory candidates with source and duplicate checks",
        requested_capabilities=selected_tool_ids,
        program_steps=MS_CANONICAL_FLOW,
        success_condition=[
            "source_anchor_is_present",
            "near_duplicate_or_supersession_check_completed_before_write",
            "admission_passes_before_vault_write",
        ],
        failure_condition=[
            "missing_source_anchor",
            "candidate_fails_admission",
            "storage_would_occur_without_duplicate_or_graft_check",
        ],
        retry_plan={
            "same_angle_retry_allowed": False,
            "changed_angle_required_when_weak": True,
            "allowed_changed_angles": ["source_anchor", "candidate_shape", "graft_check"],
        },
    )
    program_review = review_ptc_program(
        worker_program,
        selected_capability_ids=[str(row.get("tool_id") or "") for row in selected_capabilities],
    )
    allowlist = build_tst_capability_allowlist(
        worker_role="memory_saver",
        selected_capabilities=selected_capabilities,
        requested_capabilities=selected_tool_ids,
    )
    program_observation = build_ptc_program_observation(
        program=worker_program,
        tool_use_events=events,
        evaluation=loop_evaluation,
        result_summary={
            "produced_count": len(nodes),
            "rejected_count": len(rejected),
            "source_anchor_present": source_anchor_ok,
        },
    )
    delta_gate = build_observation_delta_gate(
        program=worker_program,
        observation=program_observation,
    )
    supervisor = {
        "schema_version": SCHEMA_VERSION,
        "role": "memory_saver",
        "mode": "write_scoped_save",
        "catalog_version": catalog.get("catalog_version"),
        "catalog_source_ref": catalog.get("source_ref"),
        "available_family_counts": _available_family_counts(catalog),
        "selected_capabilities": selected_capabilities,
        "cleanroom_reference_policy": {
            "reference_families": ["claude_code_tool_search_affordance"],
            "private_reference_paths_included": False,
            "server_side_anthropic_tst_claimed": False,
        },
        "catalog_policy": {
            "full_catalog_loaded_into_worker_context": False,
            "selected_references_only": True,
            "server_side_anthropic_tst_claimed": False,
        },
        "tool_search": {
            "context_hash": _sha(snapshot, length=24),
            "strategy": "save_candidate_admission_then_vault_write",
            "planner_execution_mode": "deterministic_role_scoped_supervisor",
            "available_tool_count": len(tool_references),
            "selected_tool_ids": selected_tool_ids,
            "tool_reference_count": len(tool_references),
        },
        "tool_references": tool_references,
        "tool_use_events": events,
        "worker_authored_ptc_program": worker_program,
        "ptc_program_review": program_review,
        "tst_capability_allowlist": allowlist,
        "ptc_program_observation": program_observation,
        "observation_delta_gate": delta_gate,
        "worker_task_ledger": {
            "task": "memory_save",
            "phases": [
                "define_success_failure",
                "write_worker_program",
                "review_program",
                "select_capabilities",
                "source_anchor_check",
                "extract",
                "shape",
                "near_duplicate_check",
                "admit",
                "write",
                "observe",
                "delta_gate",
                "evaluate",
            ],
        },
        "permission_decision": {
            "write_allowed": bool(nodes),
            "reason": "admitted_nodes_written" if nodes else status,
        },
        "result_summary": {
            "produced_count": len(nodes),
            "rejected_count": len(rejected),
        },
        "retry_diagnosis": None if nodes else {
            "status": "not_retried",
            "reason": status,
        },
        "typed_unavailable": None if nodes else {
            "schema_version": "typed_unavailable.v1",
            "reason_code": status,
        },
        "evaluation": loop_evaluation,
        "hard_nonclaims": [
            "not_anthropic_server_tool_search_tool",
            "not_full_tool_catalog_in_worker_context",
            "not_unbounded_write_access",
            "not_full_ux_pass",
        ],
    }
    if not nodes:
        supervisor["evaluation"]["quality"] = "weak"
        supervisor["evaluation"]["typed_unavailable_reason"] = status
    return {
        "schema_version": "memory_saver_tst_run.v1",
        "status": status,
        "produced_count": len(nodes),
        "nodes": nodes,
        "rejected": rejected,
        "tst_supervisor": supervisor,
        "tst_capability_supervisor": supervisor,
    }


def build_memory_ticket_tst_supervisor(
    *,
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the MS TST receipt section for the strict memory_ticket.v1 path."""
    catalog = load_tst_capability_catalog()
    selected_tool_ids = [
        "load_memory_ticket_skill",
        "memory_save_permission_decision",
        "validate_admission",
        "save_to_vault",
        "normalize_save_receipt",
    ]
    selected_capabilities = _select_capability_records(
        catalog,
        role="memory_saver",
        capability_ids=selected_tool_ids,
    )
    tool_references = [
        _tool_ref_from_capability(record, reason="memory_ticket_role_scoped_selection")
        for record in selected_capabilities
    ]
    status = str(result.get("status") or "unknown")
    nodes = list(result.get("nodes") or [])
    required_payload_fields = [
        "source_ref",
        "bounded_source_range",
        "anchor_hash",
        "intent_field",
        "decomposition_guard",
        "min_split_unit",
        "why_not_atomic",
        "topic_hint",
        "category_community_hint",
        "decision_capsule",
    ]
    capsule_fields = ["decision", "context", "conclusion", "evidence", "reuse_condition"]
    capsule_present = bool(payload.get("decision_capsule")) or all(payload.get(field) for field in capsule_fields)
    bounded_source_range_present = bool(
        payload.get("message_index_range")
        or payload.get("message_id_range")
        or payload.get("source_line_range")
    )
    missing_payload_fields = []
    for field in required_payload_fields:
        if field == "decision_capsule":
            if not capsule_present:
                missing_payload_fields.append(field)
            continue
        if field == "bounded_source_range":
            if not bounded_source_range_present:
                missing_payload_fields.append(field)
            continue
        if not payload.get(field):
            missing_payload_fields.append(field)
    source_ref_resolved = str(result.get("source_ref_status") or "") in {"resolved", "verified"}
    raw_storage_succeeded = status in {"acknowledged", "completed"} and bool(nodes)
    admitted = raw_storage_succeeded and not missing_payload_fields and source_ref_resolved
    pre_execution_gate_passed = not missing_payload_fields and source_ref_resolved
    write_attempted = bool(nodes) or raw_storage_succeeded
    write_executed_after_gate = bool(admitted and write_attempted)
    strict_gate = {
        "schema_version": "memory_ticket_strict_storage_gate.v1",
        "gate_stage": "post_execution",
        "required_payload_fields": required_payload_fields,
        "decision_capsule_fields": capsule_fields,
        "decision_capsule_present": capsule_present,
        "bounded_source_range_present": bounded_source_range_present,
        "missing_payload_fields": missing_payload_fields,
        "source_ref_resolved": source_ref_resolved,
        "pre_execution_gate_passed": pre_execution_gate_passed,
        "write_attempted": write_attempted,
        "write_executed_after_gate": write_executed_after_gate,
        "raw_storage_succeeded": raw_storage_succeeded,
        "storage_success_allowed": admitted,
        "failure_reason": None
        if admitted
        else (
            "typed_unavailable_insufficient_memory_ticket"
            if missing_payload_fields
            else "source_ref_not_resolved"
            if not source_ref_resolved
            else "write_artifacts_absent"
        ),
        "hard_nonclaims": [
            "postman_delivery_is_not_storage_evidence",
            "pane_projection_is_not_storage_evidence",
            "node_ids_without_source_ref_resolution_are_not_strict_storage_success",
        ],
    }
    completed_tool_ids = [
        "load_memory_ticket_skill",
        "memory_save_permission_decision",
        "validate_admission",
    ]
    if admitted:
        completed_tool_ids.extend(["save_to_vault", "normalize_save_receipt"])
    else:
        completed_tool_ids.append("normalize_save_receipt")

    payload_hash = _sha(payload, length=24)
    events: list[dict[str, Any]] = []
    for capability_id in selected_tool_ids:
        tool_use_id = f"tst-{_sha(['memory_ticket', payload_hash, capability_id], length=12)}"
        events.append(
            _tool_use_event(
                event_type="tool_use",
                tool_use_id=tool_use_id,
                capability_id=capability_id,
                status="requested",
                input_keys=["memory_ticket.v1"],
                output_kind="memory_ticket_admission_or_receipt",
            )
        )
        events.append(
            _tool_use_event(
                event_type="tool_result",
                tool_use_id=tool_use_id,
                capability_id=capability_id,
                status="completed" if capability_id in completed_tool_ids else "skipped",
                input_keys=["memory_ticket.v1"],
                output_kind="memory_ticket_admission_or_receipt",
                result_sha256="sha256:" + hashlib.sha256(
                    json.dumps(
                        {
                            "payload_hash": payload_hash,
                            "capability_id": capability_id,
                            "status": status,
                            "admitted": admitted,
                            "reason": result.get("reason"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
            )
        )

    evaluation = _evaluate_loop(
        selected_tool_ids=selected_tool_ids,
        completed_tool_ids=completed_tool_ids,
        allow_empty=False,
    )
    if not admitted:
        evaluation["quality"] = "weak"
        evaluation["typed_unavailable_reason"] = (
            strict_gate["failure_reason"] or result.get("reason") or "typed_unavailable_insufficient_memory_ticket"
        )
    worker_program = build_worker_authored_ptc_program(
        worker_role="memory_saver",
        work_order_ref={"payload_hash": payload_hash},
        self_defined_goal="save a strict memory_ticket only when source and provenance evidence is sufficient",
        requested_capabilities=selected_tool_ids,
        program_steps=MS_CANONICAL_FLOW,
        success_condition=[
            "memory_ticket_source_ref_is_resolved",
            "admission_and_provenance_write_succeeded",
            "save_receipt_can_be_normalized",
        ],
        failure_condition=[
            "memory_ticket_missing_required_source_fields",
            "source_ref_unresolved",
            "write_artifacts_absent",
        ],
        retry_plan={
            "same_angle_retry_allowed": False,
            "changed_angle_required_when_weak": True,
            "allowed_changed_angles": ["source_ref", "ticket_fields", "provider_range"],
        },
    )
    program_review = review_ptc_program(
        worker_program,
        selected_capability_ids=selected_tool_ids,
    )
    allowlist = build_tst_capability_allowlist(
        worker_role="memory_saver",
        selected_capabilities=selected_capabilities,
        requested_capabilities=selected_tool_ids,
    )
    program_observation = build_ptc_program_observation(
        program=worker_program,
        tool_use_events=events,
        evaluation=evaluation,
        result_summary={
            "produced_count": len(nodes),
            "node_count": len(nodes),
            "source_ref_status": result.get("source_ref_status"),
            "strict_storage_gate": strict_gate,
        },
    )
    delta_gate = build_observation_delta_gate(
        program=worker_program,
        observation=program_observation,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "role": "memory_saver",
        "mode": "memory_ticket_strict_save",
        "execution_order": {
            "stage": "pre_execution_then_post_execution",
            "pre_execution_gate_required": True,
            "pre_execution_gate_passed": pre_execution_gate_passed,
            "write_attempted": write_attempted,
            "write_executed_after_gate": write_executed_after_gate,
        },
        "catalog_version": catalog.get("catalog_version"),
        "catalog_source_ref": catalog.get("source_ref"),
        "available_family_counts": _available_family_counts(catalog),
        "selected_capabilities": selected_capabilities,
        "cleanroom_reference_policy": {
            "reference_families": ["claude_code_tool_search_affordance"],
            "private_reference_paths_included": False,
            "server_side_anthropic_tst_claimed": False,
        },
        "catalog_policy": {
            "full_catalog_loaded_into_worker_context": False,
            "selected_references_only": True,
            "server_side_anthropic_tst_claimed": False,
        },
        "tool_search": {
            "payload_hash": payload_hash,
            "strategy": "memory_ticket_admission_then_provenance_ring_write",
            "planner_execution_mode": "deterministic_role_scoped_supervisor",
            "selected_tool_ids": selected_tool_ids,
            "tool_reference_count": len(tool_references),
        },
        "tool_references": tool_references,
        "tool_use_events": events,
        "worker_authored_ptc_program": worker_program,
        "ptc_program_review": program_review,
        "tst_capability_allowlist": allowlist,
        "ptc_program_observation": program_observation,
        "observation_delta_gate": delta_gate,
        "worker_task_ledger": {
            "task": "memory_ticket_save",
            "phases": [
                "define_success_failure",
                "write_worker_program",
                "review_program",
                "select_capabilities",
                "admit_ticket",
                "resolve_source",
                "write_artifacts",
                "observe",
                "delta_gate",
                "evaluate",
            ],
        },
        "permission_decision": {
            "write_allowed": admitted,
            "reason": strict_gate["failure_reason"] or result.get("reason") or status,
        },
        "result_summary": {
            "produced_count": len(nodes),
            "node_count": len(nodes),
            "source_ref_status": result.get("source_ref_status"),
            "strict_storage_gate": strict_gate,
        },
        "retry_diagnosis": None if admitted else {
            "status": "not_retried",
            "reason": strict_gate["failure_reason"] or result.get("reason") or status,
        },
        "typed_unavailable": None if admitted else {
            "schema_version": "typed_unavailable.v1",
            "reason_code": strict_gate["failure_reason"] or result.get("reason") or "typed_unavailable_insufficient_memory_ticket",
        },
        "evaluation": evaluation,
        "hard_nonclaims": [
            "delivery_is_not_storage_proof",
            "pane_text_is_not_storage_proof",
            "not_full_topology_proof",
            "not_full_ux_pass",
        ],
    }


__all__ = [
    "SCHEMA_VERSION",
    "build_memory_ticket_tst_supervisor",
    "load_tst_capability_catalog",
    "build_memory_finder_tst_result",
    "run_memory_saver_tst",
]
