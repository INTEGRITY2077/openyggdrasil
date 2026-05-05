from __future__ import annotations

from retrieval.pathfinder_tools import locate_region


CAPABILITY_ID = "locate_region"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"query_text": "string"},
        read_only=True,
        output_kind="region_hint",
        handler=lambda **kwargs: find_region(vault_root=vault_root, **kwargs),
    )
