from __future__ import annotations

import uuid
from typing import Mapping

from admission.decision_contracts import (
    validate_cultivated_decision,
    validate_map_topography,
    validate_planting_decision,
)
from harness_common import utc_now_iso


def update_map_topography(
    *,
    planting_decision: Mapping[str, object],
    cultivated_decision: Mapping[str, object],
) -> dict[str, object]:
    validate_planting_decision(planting_decision)
    validate_cultivated_decision(cultivated_decision)
    topography = {
        "schema_version": "map_topography.v1",
        "topography_id": uuid.uuid4().hex,
        "cultivation_id": str(cultivated_decision["cultivation_id"]),
        "planting_id": str(planting_decision["planting_id"]),
        "continent_id": str(planting_decision["continent_id"]),
        "continent_key": str(planting_decision["continent_key"]),
        "topic_id": str(cultivated_decision["topic_id"]),
        "topic_title": str(cultivated_decision["topic_title"]),
        "page_id": str(cultivated_decision["page_id"]),
        "canonical_relative_path": str(cultivated_decision["canonical_relative_path"]),
        "bed_id": str(planting_decision["bed_id"]),
        "planting_target_kind": str(planting_decision["planting_target_kind"]),
        "planting_target_key": str(planting_decision["planting_target_key"]),
        "routing_mode": "topic_page_only",
        "topography_status": "aligned",
        "adjacency_keys": [],
        "bridge_count": 0,
        "map_updated_at": utc_now_iso(),
    }
    validate_map_topography(topography)
    return topography
