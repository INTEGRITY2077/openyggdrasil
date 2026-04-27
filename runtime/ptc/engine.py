"""PTC engine primitives extracted behind compatibility-preserving imports."""

from __future__ import annotations

import hashlib
import re
from typing import Any


STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE = "structural_anchor_fallback_without_hermes"
QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION = "ptc_query_adaptive_pathfinder_plan.v1"
QUERY_ADAPTIVE_PLAN_STATUS = "bounded_query_adaptive"
MAX_PATHFINDER_TOOL_STEP_COUNT = 6
DEFAULT_MAX_RECENT_LIMIT = 8

RECENCY_TERMS = {
    "recent",
    "recently",
    "latest",
    "current",
    "changed",
    "change",
    "today",
    "yesterday",
    "new",
}
COMPARISON_TERMS = {
    "compare",
    "conflict",
    "conflicts",
    "versus",
    "vs",
    "stale",
    "superseded",
    "supersession",
}
ORIGIN_TERMS = {"origin", "first", "initial", "root", "source"}


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _query_terms(query_text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query_text)}


def render_default_pathfinder_program(*, recent_limit: int) -> str:
    return (
        "region = tools['find_region'](query_text=query_text)\n"
        "anchor = tools['find_topic_anchor'](query_text=query_text, region_id=region['region_id'])\n"
        "if anchor['topic_id'] is None:\n"
        "    RESULT = tools['build_unanchored_bundle'](query_text=query_text)\n"
        "else:\n"
        "    origin_rows = tools['get_origin_claims'](topic_id=anchor['topic_id'], limit=1)\n"
        f"    recent_rows = tools['get_recent_episodes'](topic_id=anchor['topic_id'], limit={max(1, recent_limit)})\n"
        "    claim_ids = [row['claim_id'] for row in recent_rows + origin_rows if row.get('claim_id')]\n"
        "    source_paths = tools['get_raw_sources'](topic_id=anchor['topic_id'], claim_ids=claim_ids)\n"
        "    RESULT = tools['build_support_bundle'](\n"
        "        query_text=query_text,\n"
        "        anchor=anchor,\n"
        "        origin_rows=origin_rows,\n"
        "        recent_rows=recent_rows,\n"
        "        source_paths=source_paths,\n"
        "    )\n"
    )


def build_query_adaptive_pathfinder_plan(
    *,
    query_text: str,
    recent_limit: int = 3,
    max_recent_limit: int = DEFAULT_MAX_RECENT_LIMIT,
    max_step_count: int = MAX_PATHFINDER_TOOL_STEP_COUNT,
) -> dict[str, Any]:
    """Build a bounded deterministic Pathfinder PTC plan from query signals."""

    query = str(query_text or "").strip()
    if not query:
        raise ValueError("query_text is required")
    if max_step_count < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("max_step_count must allow the bounded Pathfinder plan")

    max_recent = _clamp_int(max_recent_limit, minimum=1, maximum=DEFAULT_MAX_RECENT_LIMIT)
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

    program_source = render_default_pathfinder_program(recent_limit=selected_recent)
    plan_hash = hashlib.sha256(
        f"{query}\n{selected_recent}\n{max_recent}\n{strategy}".encode("utf-8")
    ).hexdigest()[:32]
    plan = {
        "schema_version": QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION,
        "plan_id": f"ptc-query-adaptive-plan-{plan_hash}",
        "query_ref": f"query-ref://openyggdrasil/ptc-query-adaptive/{plan_hash}",
        "plan_status": QUERY_ADAPTIVE_PLAN_STATUS,
        "strategy": strategy,
        "bounded_tool_plan": True,
        "max_step_count": MAX_PATHFINDER_TOOL_STEP_COUNT,
        "requested_max_step_count": max_step_count,
        "base_recent_limit": _clamp_int(recent_limit, minimum=1, maximum=max_recent),
        "selected_recent_limit": selected_recent,
        "max_recent_limit": max_recent,
        "dynamic_code_execution_allowed": False,
        "program_source_status": "deterministic_plan_not_executed_as_code",
        "program_source": program_source,
        "tool_step_order": [
            "find_region",
            "find_topic_anchor",
            "get_origin_claims",
            "get_recent_episodes",
            "get_raw_sources",
            "build_support_bundle_or_unanchored_bundle",
        ],
        "reason_codes": reason_codes,
    }
    validate_query_adaptive_pathfinder_plan(plan)
    return plan


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
    if int(payload.get("requested_max_step_count") or 0) < MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("requested_max_step_count is below the required bounded plan")
    tool_steps = payload.get("tool_step_order")
    if not isinstance(tool_steps, list) or len(tool_steps) > MAX_PATHFINDER_TOOL_STEP_COUNT:
        raise ValueError("tool_step_order must be a bounded list")
    program_source = str(payload.get("program_source") or "")
    if f"limit={selected_recent}" not in program_source:
        raise ValueError("program_source must use selected_recent_limit")
    if "query_text" in payload:
        raise ValueError("query_text must not be copied into portable plan metadata")


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
    "DEFAULT_MAX_RECENT_LIMIT",
    "MAX_PATHFINDER_TOOL_STEP_COUNT",
    "QUERY_ADAPTIVE_PLAN_SCHEMA_VERSION",
    "QUERY_ADAPTIVE_PLAN_STATUS",
    "STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE",
    "build_query_adaptive_pathfinder_plan",
    "render_default_pathfinder_program",
    "render_query_adaptive_pathfinder_program",
    "structural_anchor_fallback_evaluator",
    "validate_query_adaptive_pathfinder_plan",
]
