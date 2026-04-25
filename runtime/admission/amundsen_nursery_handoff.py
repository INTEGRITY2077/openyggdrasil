from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_amundsen_nursery_handoff,
)
from harness_common import utc_now_iso


def _nursery_route_kind(admission_verdict: Mapping[str, Any]) -> str:
    decision = str(admission_verdict["continent_decision"])
    if decision == "existing_continent":
        return "existing_continent_route"
    return "new_continent_candidate"


def build_amundsen_nursery_handoff(*, admission_verdict: Mapping[str, Any]) -> dict[str, Any]:
    """Expose Amundsen's route decision without granting semantic or placement authority."""

    validate_admission_verdict(admission_verdict)
    admission_status = str(admission_verdict["admission_status"])
    ready = admission_status == "accepted"
    handoff = {
        "schema_version": "amundsen_nursery_handoff.v1",
        "handoff_id": uuid.uuid4().hex,
        "verdict_id": str(admission_verdict["verdict_id"]),
        "candidate_id": str(admission_verdict["candidate_id"]),
        "provider_id": str(admission_verdict["provider_id"]),
        "provider_profile": str(admission_verdict["provider_profile"]),
        "provider_session_id": str(admission_verdict["provider_session_id"]),
        "session_uid": str(admission_verdict["session_uid"]),
        "handoff_status": "ready_for_nursery" if ready else "blocked_by_admission",
        "nursery_route_kind": _nursery_route_kind(admission_verdict),
        "admission_status": admission_status,
        "topic_route": {
            "topic_key": str(admission_verdict["topic_key"]),
            "topic_id": str(admission_verdict["topic_id"]),
            "topic_title": str(admission_verdict["topic_title"]),
            "page_id": str(admission_verdict["page_id"]),
            "canonical_relative_path": str(admission_verdict["canonical_relative_path"]),
            "episode_id": str(admission_verdict["episode_id"]),
        },
        "continent_route": {
            "continent_key": str(admission_verdict["continent_key"]),
            "continent_id": str(admission_verdict["continent_id"]),
            "continent_title": str(admission_verdict["continent_title"]),
            "continent_decision": str(admission_verdict["continent_decision"]),
            "route_reason": str(admission_verdict["route_reason"]),
        },
        "route_authority": "amundsen_category_decision_only",
        "semantic_worth_authority": "not_amundsen",
        "placement_authority": "not_amundsen",
        "nursery_authority": "seed_composition_after_handoff",
        "blocked_reason": None if ready else "admission_status_not_accepted",
        "reason_codes": [
            "amundsen_route_explicit",
            f"continent_decision:{str(admission_verdict['continent_decision'])}",
        ],
        "admission_verdict": dict(admission_verdict),
        "created_at": utc_now_iso(),
    }
    validate_amundsen_nursery_handoff(handoff)
    return handoff
