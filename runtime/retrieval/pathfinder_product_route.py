from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from harness_common import DEFAULT_VAULT
from retrieval.pathfinder_contracts import (
    PRODUCT_ROUTE_GRAPHIFY_HINT_STATUSES,
    validate_pathfinder_product_route_result,
)


def _product_route_ref_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]

def _normalize_graphify_hint_status(value: str | None) -> str:
    status = str(value or "not_requested").strip() or "not_requested"
    if status not in PRODUCT_ROUTE_GRAPHIFY_HINT_STATUSES:
        raise ValueError(f"unsupported graphify_hint_status: {status}")
    return status

def build_pathfinder_product_route_result(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    program: Sequence[Mapping[str, Any]] | None = None,
    recent_limit: int = 3,
    same_run_context: Mapping[str, Any] | None = None,
    graphify_hint_status: str | None = "not_requested",
    scratch_root: Path | None = None,
) -> dict[str, Any]:
    from retrieval.programmatic_tool_runtime import (
        DEFAULT_SCRATCH_ROOT,
        build_pathfinder_bundle_via_programmatic_tool_runtime,
    )

    runtime_result = build_pathfinder_bundle_via_programmatic_tool_runtime(
        query_text=query_text,
        vault_root=vault_root,
        anchor_evaluator=anchor_evaluator,
        program=program,
        recent_limit=recent_limit,
        scratch_root=scratch_root or DEFAULT_SCRATCH_ROOT,
        same_run_context=same_run_context,
    )
    trace = dict(runtime_result["trace"])
    trace_id = str(trace["trace_id"])
    final_result = dict(trace["final_result"])
    result_sha256 = str(final_result["result_sha256"])
    result_token = result_sha256.removeprefix("sha256:")
    query_token = _product_route_ref_token(query_text.strip())
    graphify_status = _normalize_graphify_hint_status(graphify_hint_status)

    query_ref = f"query-ref://openyggdrasil/pathfinder-product-route/{query_token}"
    support_bundle_ref = f"support-bundle-ref://openyggdrasil/pathfinder-product-route/{result_token}"
    ptc_trace_ref = f"ptc-trace-ref://openyggdrasil/programmatic-tool-runtime/{trace_id}"

    selected_memory_refs = [
        {
            "ref": f"ptc-result-ref://openyggdrasil/pathfinder-product-route/{trace_id}/final_result",
            "role": "pathfinder_bundle_result",
            "reason_code": "bounded_programmatic_tool_final_result",
        },
        {
            "ref": support_bundle_ref,
            "role": "support_bundle_source",
            "reason_code": "bounded_programmatic_tool_support_bundle",
        },
        {
            "ref": ptc_trace_ref,
            "role": "ptc_trace",
            "reason_code": "programmatic_tool_runtime_trace",
        },
    ]
    if isinstance(same_run_context, Mapping):
        selected_memory_refs.append(
            {
                "ref": f"same-run-context-ref://openyggdrasil/programmatic-tool-runtime/{trace_id}",
                "role": "same_run_context_source",
                "reason_code": "upstream_verified_same_run_context_accepted",
            }
        )

    rejected_memory_refs = []
    if graphify_status == "unavailable_fallback":
        rejected_memory_refs.append(
            {
                "ref": "graphify-ref://openyggdrasil/pathfinder-product-route/unavailable",
                "role": "graphify_hint",
                "reason_code": "derived_index_unavailable_not_sot",
            }
        )

    result = {
        "schema_version": "pathfinder_product_route_result.v1",
        "route_status": "completed" if trace.get("decision") == "completed" else "stopped",
        "query_ref": query_ref,
        "support_bundle_ref": support_bundle_ref,
        "ptc_trace_ref": ptc_trace_ref,
        "graphify_hint_status": graphify_status,
        "provenance_fallback_status": "used" if graphify_status == "unavailable_fallback" else "not_needed",
        "selected_memory_refs": selected_memory_refs,
        "rejected_memory_refs": rejected_memory_refs,
        "raw_provider_material_included": False,
        "portable_local_path_included": False,
        "live_readiness_claimed": False,
        "target_readiness_claimed": False,
        "source_007_rerun": False,
        "stale_heartbeat_resumed": False,
    }
    validate_pathfinder_product_route_result(result)
    return result
