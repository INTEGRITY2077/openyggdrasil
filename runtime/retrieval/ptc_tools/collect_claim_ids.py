from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CAPABILITY_ID = "collect_claim_ids"


def collect_claim_ids(*, recent_rows: list[Any], origin_rows: list[Any]) -> list[str]:
    claim_ids: list[str] = []
    for row in list(recent_rows) + list(origin_rows):
        if not isinstance(row, Mapping):
            continue
        claim_id = str(row.get("claim_id") or "").strip()
        if claim_id and claim_id not in claim_ids:
            claim_ids.append(claim_id)
    return claim_ids


def register(registry: dict, *, vault_root, anchor_evaluator=None) -> None:
    _ = vault_root
    _ = anchor_evaluator
    from retrieval.programmatic_tool_runtime import Capability

    registry[CAPABILITY_ID] = Capability(
        capability_id=CAPABILITY_ID,
        required_inputs={"recent_rows": "array", "origin_rows": "array"},
        read_only=True,
        output_kind="claim_id_list",
        handler=collect_claim_ids,
    )
