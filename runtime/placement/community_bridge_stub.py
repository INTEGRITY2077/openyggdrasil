from __future__ import annotations

import uuid
from typing import Mapping

from admission.decision_contracts import (
    validate_community_topography,
    validate_map_topography,
)
from common.map_identity import build_community_id
from harness_common import utc_now_iso


def _community_key_from_map(map_topography: Mapping[str, object]) -> str:
    return str(map_topography["continent_key"])


def _community_title_from_key(community_key: str) -> str:
    title = community_key.replace("/", " ").replace("-", " ").replace("_", " ").strip()
    return " ".join(part.capitalize() for part in title.split()) or "Community"


def _community_note_relative_path(community_key: str) -> str:
    return f"communities/{community_key}.md"


def build_community_topography(
    *,
    map_topography: Mapping[str, object],
) -> dict[str, object]:
    validate_map_topography(map_topography)
    community_key = _community_key_from_map(map_topography)
    community = {
        "schema_version": "community_topography.v1",
        "community_topography_id": uuid.uuid4().hex,
        "topography_id": str(map_topography["topography_id"]),
        "community_id": build_community_id(community_key),
        "community_key": community_key,
        "community_title": _community_title_from_key(community_key),
        "continent_id": str(map_topography["continent_id"]),
        "continent_key": str(map_topography["continent_key"]),
        "member_topic_ids": [str(map_topography["topic_id"])],
        "community_note_relative_path": _community_note_relative_path(community_key),
        "bridge_keys": [],
        "bridge_count": 0,
        "bridge_status": "no_bridges",
        "topography_status": "isolated",
        "updated_at": utc_now_iso(),
    }
    validate_community_topography(community)
    return community
