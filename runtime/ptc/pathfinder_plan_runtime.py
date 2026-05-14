from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.ptc.base_utils import _clamp_int, _query_terms
from runtime.ptc.engine_contracts import (
    COMPARISON_TERMS,
    DEFAULT_MAX_RECENT_LIMIT,
    DETERMINISTIC_PLANNER_MODE,
    EXTERNAL_LLM_PLANNER_MODE,
    FALLBACK_PLANNER_MODE,
    LEASE_BACKED_LLM_PLANNER_MODE,
    MAX_PATHFINDER_JSON_TOOL_STEP_COUNT,
    MAX_PATHFINDER_TOOL_STEP_COUNT,
    ORIGIN_TERMS,
    PATHFINDER_JSON_TOOL_CAPABILITIES,
    QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION,
    QUERY_ADAPTIVE_PLAN_STATUS,
    RECENCY_TERMS,
    STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE,
)

def render_default_pathfinder_program(*, recent_limit: int) -> str:
    return (
        "region = tools['locate_region'](query_text=query_text)\n"
        "anchor = tools['select_topic_anchor'](query_text=query_text, region_id=region['region_id'])\n"
        "if anchor['topic_id'] is None:\n"
        "    RESULT = tools['assemble_unanchored_bundle'](query_text=query_text)\n"
        "else:\n"
        "    origin_rows = tools['get_origin_claims'](topic_id=anchor['topic_id'], limit=1)\n"
        f"    recent_rows = tools['read_recent_claims'](topic_id=anchor['topic_id'], limit={max(1, recent_limit)})\n"
        "    claim_ids = [row['claim_id'] for row in recent_rows + origin_rows if row.get('claim_id')]\n"
        "    source_paths = tools['read_source_paths'](topic_id=anchor['topic_id'], claim_ids=claim_ids)\n"
        "    RESULT = tools['build_support_bundle'](\n"
        "        query_text=query_text,\n"
        "        anchor=anchor,\n"
        "        origin_rows=origin_rows,\n"
        "        recent_rows=recent_rows,\n"
        "        source_paths=source_paths,\n"
        "    )\n"
    )

def render_default_pathfinder_json_plan(*, recent_limit: int) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "region",
            "capability_id": "locate_region",
            "input": {"query_text": {"from_context": "query_text"}},
        },
        {
            "step_id": "anchor",
            "capability_id": "select_topic_anchor",
            "input": {
                "query_text": {"from_context": "query_text"},
                "region_id": {"from_step": "region", "path": ["region_id"]},
            },
        },
        {
            "step_id": "origin",
            "capability_id": "read_origin_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": 1},
            },
        },
        {
            "step_id": "recent",
            "capability_id": "read_recent_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": max(1, recent_limit)},
            },
        },
        {
            "step_id": "claim_ids",
            "capability_id": "collect_claim_ids",
            "input": {
                "recent_rows": {"from_step": "recent"},
                "origin_rows": {"from_step": "origin"},
            },
        },
        {
            "step_id": "sources",
            "capability_id": "read_source_paths",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "claim_ids": {"from_step": "claim_ids"},
            },
        },
        {
            "step_id": "bundle",
            "capability_id": "assemble_support_bundle",
            "input": {
                "query_text": {"from_context": "query_text"},
                "anchor": {"from_step": "anchor"},
                "origin_rows": {"from_step": "origin"},
                "recent_rows": {"from_step": "recent"},
                "source_paths": {"from_step": "sources"},
            },
        },
    ]

def validate_pathfinder_json_tool_plan(plan: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(plan, Sequence) or isinstance(plan, (str, bytes)):
        raise ValueError("pathfinder JSON tool plan must be a sequence")
    if not plan or len(plan) > MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("pathfinder JSON tool plan exceeds bounded step count")
    seen_step_ids: set[str] = set()
    for raw_step in plan:
        if not isinstance(raw_step, Mapping):
            raise ValueError("pathfinder JSON tool plan steps must be objects")
        step_id = str(raw_step.get("step_id") or "").strip()
        capability_id = str(raw_step.get("capability_id") or "").strip()
        if not step_id or step_id in seen_step_ids:
            raise ValueError("pathfinder JSON tool plan step_id must be unique and non-empty")
        seen_step_ids.add(step_id)
        if capability_id not in PATHFINDER_JSON_TOOL_CAPABILITIES:
            raise ValueError(f"unknown pathfinder JSON tool capability: {capability_id}")
        if not isinstance(raw_step.get("input"), Mapping):
            raise ValueError(f"{step_id}.input must be an object")
    if str(plan[-1].get("step_id") or "") != "bundle":
        raise ValueError("pathfinder JSON tool plan must finish at bundle")

def _normalized_json_tool_plan(plan: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validate_pathfinder_json_tool_plan(plan)
    return [
        {
            "step_id": str(step["step_id"]),
            "capability_id": str(step["capability_id"]),
            "input": dict(step["input"]),
        }
        for step in plan
    ]

def _extract_lease_ptc_tool_plan(lease_consumer_result: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    if not lease_consumer_result:
        return None
    if lease_consumer_result.get("consumer_status") != "completed":
        return None
    job_results = lease_consumer_result.get("job_results")
    if not isinstance(job_results, Sequence) or isinstance(job_results, (str, bytes)) or not job_results:
        return None
    first_job = job_results[0]
    if not isinstance(first_job, Mapping) or first_job.get("job_status") != "completed":
        return None
    lease_result = first_job.get("lease_result")
    if not isinstance(lease_result, Mapping) or lease_result.get("lease_status") != "completed":
        return None
    output = lease_result.get("output")
    if not isinstance(output, Mapping):
        return None
    trace = output.get("bubblewrap_trace")
    if not isinstance(trace, Mapping):
        return None
    if "ptc_plan_generation_recorded" not in trace.get("reason_codes", []):
        return None
    return _normalized_json_tool_plan(output.get("ptc_tool_plan") or [])

def _pathfinder_query_strategy(
    *,
    query: str,
    recent_limit: int,
    max_recent: int,
) -> tuple[int, str, list[str]]:
    selected_recent = _clamp_int(recent_limit, minimum=1, maximum=max_recent)
    terms = _query_terms(query)
    reason_codes = [
        "query_adaptive_bounded_plan_built",
        "fixed_default_plan_replaced_by_query_adaptive_hook",
        "dynamic_program_source_disabled",
    ]
    strategy = "default_pathfinder_support_bundle"

    if terms & RECENCY_TERMS:
        selected_recent = max(selected_recent, min(max_recent, selected_recent + 2))
        strategy = "recency_weighted_support_bundle"
        reason_codes.append("query_recency_signal_detected")
    if terms & COMPARISON_TERMS:
        selected_recent = max(selected_recent, min(max_recent, selected_recent + 1))
        strategy = (
            "recency_comparison_support_bundle"
            if strategy == "recency_weighted_support_bundle"
            else "comparison_support_bundle"
        )
        reason_codes.append("query_comparison_signal_detected")
    if terms & ORIGIN_TERMS:
        reason_codes.append("query_origin_signal_detected")
        if strategy == "default_pathfinder_support_bundle":
            strategy = "origin_weighted_support_bundle"
    if len(terms) <= 3 and not (terms & (RECENCY_TERMS | COMPARISON_TERMS)):
        selected_recent = min(selected_recent, 2)
        reason_codes.append("short_query_bounded_recent_limit")
    return selected_recent, strategy, reason_codes

def _pathfinder_planner_mode(
    *,
    extracted_llm_tool_plan: list[dict[str, Any]] | None,
    lease_consumer_result: Mapping[str, Any] | None,
    fallback_reason_code: str | None,
) -> str:
    if extracted_llm_tool_plan is not None and lease_consumer_result is not None:
        return LEASE_BACKED_LLM_PLANNER_MODE
    if extracted_llm_tool_plan is not None:
        return EXTERNAL_LLM_PLANNER_MODE
    if fallback_reason_code:
        return FALLBACK_PLANNER_MODE
    return DETERMINISTIC_PLANNER_MODE

def _append_llm_plan_metadata(
    *,
    plan: dict[str, Any],
    extracted_llm_tool_plan: list[dict[str, Any]] | None,
    lease_consumer_result: Mapping[str, Any] | None,
) -> None:
    if extracted_llm_tool_plan is None:
        return
    plan.update(
        {
            "lease_consumer_status": lease_consumer_result.get("consumer_status")
            if lease_consumer_result
            else "external_llm_tool_plan",
            "bubblewrap_trace_ref": (
                lease_consumer_result.get("job_results", [{}])[0].get(
                    "bubblewrap_trace_ref"
                )
                if lease_consumer_result
                else None
            ),
        }
    )
    plan["reason_codes"].extend(
        [
            "llm_json_plan_generated_via_phase2_lease_consumer",
            (
                "ptc_plan_generation_recorded_in_bwrap_trace"
                if lease_consumer_result is not None
                else "external_llm_json_plan_validated"
            ),
        ]
    )

def build_query_adaptive_pathfinder_plan(
    *,
    query_text: str,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
    llm_tool_plan: Sequence[Mapping[str, Any]] | None = None,
    lease_consumer_result: Mapping[str, Any] | None = None,
    fallback_reason_code: str | None = None,
) -> dict[str, Any]:
    """Build a bounded Pathfinder PTC plan from query signals or a lease-backed LLM plan."""

    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")
    if max_step_count < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("max_step_count must allow the bounded Pathfinder plan")

    max_recent = _clamp_int(max_recent_limit, minimum=1, maximum=DEFAULT_MAX_RECENT_LIMIT)
    selected_recent, strategy, reason_codes = _pathfinder_query_strategy(
        query=query,
        recent_limit=recent_limit,
        max_recent=max_recent,
    )

    extracted_llm_tool_plan = (
        _normalized_json_tool_plan(llm_tool_plan)
        if llm_tool_plan is not None
        else _extract_lease_ptc_tool_plan(lease_consumer_result)
    )
    json_tool_plan = extracted_llm_tool_plan or render_default_pathfinder_json_plan(
        recent_limit=selected_recent
    )
    planner_mode = _pathfinder_planner_mode(
        extracted_llm_tool_plan=extracted_llm_tool_plan,
        lease_consumer_result=lease_consumer_result,
        fallback_reason_code=fallback_reason_code,
    )
    program_source = render_default_pathfinder_program(recent_limit=selected_recent)
    plan_hash = hashlib.sha256(
        f"{query}\n{selected_recent}\n{max_recent}\n{strategy}\n{planner_mode}\n{json_tool_plan}".encode("utf-8")
    ).hexdigest()[:32]
    plan = {
        "schema_version": QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION,
        "plan_id": f"ptc-query-adaptive-plan-{plan_hash}",
        "query_ref": f"query-ref://openyggdrasil/ptc-query-adaptive/{plan_hash}",
        "plan_status": QUERY_ADAPTIVE_PLAN_STATUS,
        "strategy": strategy,
        "planner_execution_mode": planner_mode,
        "bounded_tool_plan": True,
        "max_step_count": MAX_PATHFINDER_TOOL_STEP_COUNT,
        "max_json_tool_step_count": MAX_PATHFINDER_JSON_TOOL_STEP_COUNT,
        "requested_max_step_count": max_step_count,
        "base_recent_limit": _clamp_int(recent_limit, minimum=1, maximum=max_recent),
        "selected_recent_limit": selected_recent,
        "max_recent_limit": max_recent,
        "dynamic_code_execution_allowed": False,
        "program_source_status": (
            "bounded_json_plan_from_llm_not_dynamic_code"
            if extracted_llm_tool_plan is not None
            else "deterministic_plan_not_executed_as_code"
        ),
        "program_source": program_source,
        "json_tool_plan": json_tool_plan,
        "tool_step_order": [step["capability_id"] for step in json_tool_plan],
        "reason_codes": reason_codes,
    }
    _append_llm_plan_metadata(
        plan=plan,
        extracted_llm_tool_plan=extracted_llm_tool_plan,
        lease_consumer_result=lease_consumer_result,
    )
    if fallback_reason_code:
        plan["reason_codes"].append(str(fallback_reason_code))
    validate_query_adaptive_pathfinder_plan(plan)
    return plan

def build_lease_backed_query_adaptive_pathfinder_plan(
    *,
    query_text: str,
    sandbox_decision: Mapping[str, Any],
    bwrap_command: Sequence[str],
    provider_descriptor: Mapping[str, Any] | None = None,
    db_path: Path | None = None,
    popen_factory=None,
    scratch_root: Path | None = None,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
) -> dict[str, Any]:
    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")

    from delivery.mailbox_store import append_message
    from reasoning.lease_executor import (
        build_reasoning_lease_mailbox_job,
        consume_reasoning_lease_mailbox_jobs,
    )
    from reasoning.provider_resource_boundary import build_provider_headless_lease_request

    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]
    descriptor = {
        "provider_id": "hermes",
        "provider_profile": "phase3a-ptc",
        "provider_session_id": f"ptc-plan-{query_hash}",
        "session_uid": f"hermes:phase3a-ptc:ptc-plan-{query_hash}",
        **dict(provider_descriptor or {}),
    }
    lease_request = build_provider_headless_lease_request(
        provider_descriptor=descriptor,
        requested_by_role="pathfinder",
        job_type="pathfinding_review",
        objective="Generate a bounded JSON Programmatic Tool Calling plan from safe refs.",
        input_refs={
            "query_ref": f"query-ref://openyggdrasil/ptc-dynamic-plan/{query_hash}",
            "tool_registry_ref": "ptc-tool-registry-ref://openyggdrasil/pathfinder/v1",
        },
        priority="medium",
        time_budget_seconds=120,
        expected_output_schema="pathfinder_json_tool_plan",
    )
    message = build_reasoning_lease_mailbox_job(
        lease_request,
        job_id=f"ptc-dynamic-plan-{query_hash}",
    )
    append_message(message, db_path=db_path)
    lease_consumer_result = consume_reasoning_lease_mailbox_jobs(
        lease_request_resolver=lambda _message: lease_request,
        sandbox_decision=sandbox_decision,
        bwrap_command=bwrap_command,
        db_path=db_path,
        max_jobs=1,
        popen_factory=popen_factory,
        scratch_root=scratch_root,
        evidence_ref_prefix=(
            "evidence-ref://openyggdrasil/public/proof-history/runs/phase3a-ptc-dynamic-plan"
        ),
    )
    extracted_plan = _extract_lease_ptc_tool_plan(lease_consumer_result)
    if extracted_plan is None:
        return build_query_adaptive_pathfinder_plan(
            query_text=query,
            recent_limit=recent_limit,
            max_recent_limit=max_recent_limit,
            max_step_count=max_step_count,
            fallback_reason_code="llm_plan_generation_failed_default_pathfinder_program_used",
        )
    return build_query_adaptive_pathfinder_plan(
        query_text=query,
        recent_limit=recent_limit,
        max_recent_limit=max_recent_limit,
        max_step_count=max_step_count,
        lease_consumer_result=lease_consumer_result,
    )

def validate_query_adaptive_pathfinder_plan(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION:
        raise ValueError("invalid query-adaptive Pathfinder plan schema_version")
    if payload.get("plan_status") != QUERY_ADAPTIVE_PLAN_STATUS:
        raise ValueError("query-adaptive Pathfinder plan must be bounded")
    if payload.get("bounded_tool_plan") is not True:
        raise ValueError("query-adaptive Pathfinder plan must be bounded")
    if payload.get("dynamic_code_execution_allowed") is not False:
        raise ValueError("query-adaptive Pathfinder plan must not allow dynamic code")
    max_recent = int(payload.get("max_recent_limit") or 0)
    selected_recent = int(payload.get("selected_recent_limit") or 0)
    if max_recent < 1 or max_recent > DEFAULT_MAX_RECENT_LIMIT:
        raise ValueError("max_recent_limit is out of bounds")
    if selected_recent < 1 or selected_recent > max_recent:
        raise ValueError("selected_recent_limit is out of bounds")
    if int(payload.get("max_step_count") or 0) != MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("max_step_count must match bounded Pathfinder tool plan")
    if int(payload.get("max_json_tool_step_count") or 0) != MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("max_json_tool_step_count must match bounded JSON tool plan")
    if int(payload.get("requested_max_step_count") or 0) < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("requested_max_step_count is below the required bounded plan")
    tool_steps = payload.get("tool_step_order")
    if not isinstance(tool_steps, list) or len(tool_steps) > MAX_PATHFINDER_JSON_TOOL_STEP_COUNT:
        raise ValueError("tool_step_order must be a bounded list")
    validate_pathfinder_json_tool_plan(payload.get("json_tool_plan") or [])
    program_source = str(payload.get("program_source") or "")
    if f"limit={selected_recent}" not in program_source:
        raise ValueError("program_source must use selected_recent_limit")
    if "query_text" in payload:
        raise ValueError("query_text must not be copied into portable plan metadata")
    planner_mode = str(payload.get("planner_execution_mode") or "")
    if planner_mode == LEASE_BACKED_LLM_PLANNER_MODE:
        if payload.get("lease_consumer_status") != "completed":
            raise ValueError("lease-backed LLM plan requires completed lease consumer status")
        if not str(payload.get("bubblewrap_trace_ref") or "").startswith("ptc-trace-ref://"):
            raise ValueError("lease-backed LLM plan requires a safe bubblewrap_trace_ref")

def render_query_adaptive_pathfinder_program(
    *,
    query_text: str,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
) -> str:
    plan = build_query_adaptive_pathfinder_plan(
        query_text=query_text,
        recent_limit=recent_limit,
        max_recent_limit=max_recent_limit,
        max_step_count=max_step_count,
    )
    return str(plan["program_source"])

def structural_anchor_fallback_evaluator(
    *,
    query_text: str,
    existing_topics: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    _ = query_text
    _ = existing_topics
    return {
        "topic_key": None,
        "reason_labels": [STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE],
        "summary": "PTC structural path did not use Hermes; returning an unanchored fallback.",
    }


__all__ = [
    "render_default_pathfinder_program",
    "render_default_pathfinder_json_plan",
    "validate_pathfinder_json_tool_plan",
    "_normalized_json_tool_plan",
    "_extract_lease_ptc_tool_plan",
    "build_query_adaptive_pathfinder_plan",
    "build_lease_backed_query_adaptive_pathfinder_plan",
    "validate_query_adaptive_pathfinder_plan",
    "render_query_adaptive_pathfinder_program",
    "structural_anchor_fallback_evaluator",
]
