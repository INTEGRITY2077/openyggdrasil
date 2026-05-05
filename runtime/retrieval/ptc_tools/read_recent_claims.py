from __future__ import annotations

from retrieval.pathfinder_tools import read_recent_claims


CAPABILITY_ID = "read_recent_claims"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"topic_id": "string", "limit": "integer"},
        read_only=True,
        output_kind="recent_claim_rows",
        handler=lambda **kwargs: get_recent_episodes(vault_root=vault_root, **kwargs),
    )
