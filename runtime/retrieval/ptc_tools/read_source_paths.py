from __future__ import annotations

from retrieval.pathfinder_tools import read_source_paths


CAPABILITY_ID = "read_source_paths"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"topic_id": "string", "claim_ids": "array"},
        read_only=True,
        output_kind="source_path_list",
        handler=lambda **kwargs: read_source_paths(vault_root=vault_root, **kwargs),
    )
