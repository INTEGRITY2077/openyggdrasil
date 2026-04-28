from __future__ import annotations

from retrieval.pathfinder_tools import get_origin_claims


CAPABILITY_ID = "read_origin_claims"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"topic_id": "string", "limit": "integer"},
        read_only=True,
        output_kind="origin_claim_rows",
        handler=lambda **kwargs: get_origin_claims(vault_root=vault_root, **kwargs),
    )
