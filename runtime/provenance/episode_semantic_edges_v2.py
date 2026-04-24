from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso
from provenance.episode_semantic_edges import validate_semantic_edge_verdict


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = OPENYGGDRASIL_ROOT / "contracts" / "episode_semantic_edges.v2.schema.json"


@lru_cache(maxsize=1)
def load_semantic_edge_v2_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_semantic_edge_temporal_verdict(verdict: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(verdict), schema=load_semantic_edge_v2_schema())


def _edge_id(*, source_claim_id: str, edge_type: str, target_claim_id: str) -> str:
    return f"edge:{source_claim_id}:{edge_type}:{target_claim_id}"


def _edge_rows(
    *,
    source_claim_id: str,
    edge_type: str,
    target_claim_ids: list[str],
    valid_at: str,
    as_of: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    invalidates_target = edge_type in {"supersedes", "contradicts"}
    for target_claim_id in target_claim_ids:
        rows.append(
            {
                "edge_id": _edge_id(
                    source_claim_id=source_claim_id,
                    edge_type=edge_type,
                    target_claim_id=target_claim_id,
                ),
                "edge_type": edge_type,
                "source_claim_id": source_claim_id,
                "target_claim_id": target_claim_id,
                "valid_at": valid_at,
                "invalid_at": valid_at if invalidates_target else None,
                "invalidated_by": source_claim_id if invalidates_target else None,
                "as_of": as_of,
            }
        )
    return rows


def build_temporal_semantic_edge_verdict(
    *,
    verdict_v1: Mapping[str, Any],
    current_episode_id: str,
    current_claim_id: str,
    as_of: str | None = None,
    valid_at: str | None = None,
) -> dict[str, Any]:
    validate_semantic_edge_verdict(verdict_v1)
    as_of_value = as_of or str(verdict_v1.get("evaluated_at") or utc_now_iso())
    valid_at_value = valid_at or as_of_value
    edges: list[dict[str, Any]] = []
    for edge_type in ("supports", "supersedes", "contradicts"):
        edges.extend(
            _edge_rows(
                source_claim_id=current_claim_id,
                edge_type=edge_type,
                target_claim_ids=list(verdict_v1.get(edge_type) or []),
                valid_at=valid_at_value,
                as_of=as_of_value,
            )
        )
    verdict = {
        "schema_version": "episode_semantic_edges.v2",
        "source_schema_version": "episode_semantic_edges.v1",
        "current_episode_id": current_episode_id,
        "current_claim_id": current_claim_id,
        "edges": edges,
        "reason_labels": list(verdict_v1.get("reason_labels") or []),
        "summary": str(verdict_v1.get("summary") or ""),
        "evaluation_mode": str(verdict_v1.get("evaluation_mode") or ""),
        "evaluated_at": str(verdict_v1.get("evaluated_at") or as_of_value),
        "as_of": as_of_value,
    }
    validate_semantic_edge_temporal_verdict(verdict)
    return verdict
