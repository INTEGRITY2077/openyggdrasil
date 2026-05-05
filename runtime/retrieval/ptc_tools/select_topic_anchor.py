from __future__ import annotations

from retrieval.pathfinder_tools import select_topic_anchor


CAPABILITY_ID = "select_topic_anchor"


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"query_text": "string", "region_id": "string"},
        read_only=True,
        output_kind="topic_anchor",
        handler=lambda **kwargs: find_topic_anchor(
            vault_root=vault_root,
            evaluator=anchor_evaluator,
            **kwargs,
        ),
    )
