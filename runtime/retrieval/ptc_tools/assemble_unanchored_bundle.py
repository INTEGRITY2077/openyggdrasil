from __future__ import annotations

from retrieval.pathfinder_tools import build_unanchored_bundle


CAPABILITY_ID = "assemble_unanchored_bundle"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = vault_root
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"query_text": "string"},
        read_only=True,
        output_kind="pathfinder_bundle",
        handler=build_unanchored_bundle,
    )
