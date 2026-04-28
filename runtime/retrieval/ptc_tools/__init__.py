from __future__ import annotations

from . import (
    assemble_support_bundle,
    assemble_unanchored_bundle,
    collect_claim_ids,
    locate_region,
    read_origin_claims,
    read_recent_claims,
    read_source_paths,
    select_topic_anchor,
)


REGISTERED_TOOL_MODULES = (
    locate_region,
    select_topic_anchor,
    read_origin_claims,
    read_recent_claims,
    collect_claim_ids,
    read_source_paths,
    assemble_support_bundle,
    assemble_unanchored_bundle,
)


def register_pathfinder_capabilities(
    *,
    vault_root,
    anchor_evaluator=None,
) -> dict:
    registry = {}
    for module in REGISTERED_TOOL_MODULES:
        module.register(
            registry,
            vault_root=vault_root,
            anchor_evaluator=anchor_evaluator,
        )
    return registry
