from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from harness_common import DEFAULT_VAULT
from retrieval.pathfinder_bundle_builder import (
    _topic_page_title,
    _unanchored_bundle,
    build_anchor_prompt,
    finalize_pathfinder_bundle,
    parse_episode_blocks,
    render_pathfinder_anchor_via_hermes,
)
from retrieval.pathfinder_contracts import (
    OPENYGGDRASIL_ROOT,
    PATHFINDER_PRODUCT_ROUTE_RESULT_SCHEMA_PATH,
    PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH,
    PATHFINDER_SCHEMA_PATH,
    PRODUCT_ROUTE_FORBIDDEN_TEXT,
    PRODUCT_ROUTE_GRAPHIFY_HINT_STATUSES,
    load_pathfinder_product_route_result_schema,
    load_pathfinder_retrieval_result_schema,
    load_pathfinder_schema,
    validate_pathfinder_bundle,
    validate_pathfinder_product_route_result,
    validate_pathfinder_retrieval_result,
)
from retrieval.pathfinder_lifecycle import (
    ACTIVE_LIFECYCLE_STATE,
    EXCLUDED_RETRIEVAL_LIFECYCLE_STATES,
    filter_lifecycle_records_for_retrieval,
    measure_historical_intent_discriminator_metrics,
    measure_lifecycle_rejection_ux_metrics,
)
from retrieval.pathfinder_mailbox import build_pathfinder_retrieval_result
from retrieval.pathfinder_product_route import (
    build_pathfinder_product_route_result,
)


def build_pathfinder_bundle(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a Pathfinder bundle through the bounded PTC runtime substrate."""

    from retrieval.programmatic_tool_runtime import (
        DEFAULT_SCRATCH_ROOT,
        build_pathfinder_bundle_via_programmatic_tool_runtime,
    )

    runtime_result = build_pathfinder_bundle_via_programmatic_tool_runtime(
        query_text=query_text,
        vault_root=vault_root,
        anchor_evaluator=evaluator,
        scratch_root=DEFAULT_SCRATCH_ROOT,
    )
    trace = dict(runtime_result["trace"])
    bundle = dict(trace["final_result"])
    validate_pathfinder_bundle(bundle)
    return bundle


def build_pathfinder_bundle_ptc_mvp(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    program_source: str | None = None,
    recent_limit: int = 3,
) -> dict[str, Any]:
    from retrieval.pathfinder_ptc_mvp import build_pathfinder_bundle_via_ptc_mvp

    return build_pathfinder_bundle_via_ptc_mvp(
        query_text=query_text,
        vault_root=vault_root,
        anchor_evaluator=anchor_evaluator,
        program_source=program_source,
        recent_limit=recent_limit,
    )


__all__ = [
    "ACTIVE_LIFECYCLE_STATE",
    "EXCLUDED_RETRIEVAL_LIFECYCLE_STATES",
    "OPENYGGDRASIL_ROOT",
    "PATHFINDER_PRODUCT_ROUTE_RESULT_SCHEMA_PATH",
    "PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH",
    "PATHFINDER_SCHEMA_PATH",
    "PRODUCT_ROUTE_FORBIDDEN_TEXT",
    "PRODUCT_ROUTE_GRAPHIFY_HINT_STATUSES",
    "_topic_page_title",
    "_unanchored_bundle",
    "build_anchor_prompt",
    "build_pathfinder_bundle",
    "build_pathfinder_bundle_ptc_mvp",
    "build_pathfinder_product_route_result",
    "build_pathfinder_retrieval_result",
    "filter_lifecycle_records_for_retrieval",
    "finalize_pathfinder_bundle",
    "load_pathfinder_product_route_result_schema",
    "load_pathfinder_retrieval_result_schema",
    "load_pathfinder_schema",
    "measure_historical_intent_discriminator_metrics",
    "measure_lifecycle_rejection_ux_metrics",
    "parse_episode_blocks",
    "render_pathfinder_anchor_via_hermes",
    "validate_pathfinder_bundle",
    "validate_pathfinder_product_route_result",
    "validate_pathfinder_retrieval_result",
]
