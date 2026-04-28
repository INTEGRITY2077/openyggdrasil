from __future__ import annotations

from retrieval.pathfinder_tools import build_support_bundle


CAPABILITY_ID = "assemble_support_bundle"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = vault_root
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={
            "query_text": "string",
            "anchor": "object",
            "origin_rows": "array",
            "recent_rows": "array",
            "source_paths": "array",
        },
        read_only=True,
        output_kind="pathfinder_bundle",
        handler=build_support_bundle,
    )
