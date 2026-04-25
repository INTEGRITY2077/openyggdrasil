from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_map_topography,
    validate_postman_delivery_handoff,
)
from harness_common import utc_now_iso


def build_postman_delivery_handoff(
    *,
    admission_verdict: Mapping[str, Any],
    map_topography: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
    session_admission_verdict_id: str | None = None,
) -> dict[str, Any]:
    """Finalize a provider-session delivery target without taking upstream authority."""

    validate_admission_verdict(admission_verdict)
    validate_map_topography(map_topography)
    handoff = {
        "schema_version": "postman_delivery_handoff.v1",
        "handoff_id": uuid.uuid4().hex,
        "handoff_status": "ready_for_mailbox_packet",
        "message_type": "map_topography",
        "target": {
            "provider_id": str(admission_verdict["provider_id"]),
            "provider_profile": str(admission_verdict["provider_profile"]),
            "provider_session_id": str(admission_verdict["provider_session_id"]),
            "topic": str(admission_verdict["topic_key"]),
            "canonical_relative_path": str(map_topography["canonical_relative_path"]),
            "topography_id": str(map_topography["topography_id"]),
            "session_admission_verdict_id": session_admission_verdict_id,
            "source_refs": source_refs,
        },
        "delivery_authority": "session_delivery_finalization_only",
        "semantic_worth_authority": "not_postman",
        "category_authority": "not_postman",
        "placement_authority": "not_postman",
        "sot_mutation_authority": "not_postman",
        "mailbox_mutation_authority": "deferred_to_guarded_emission",
        "source_ref_authority": "forward_only",
        "reason_codes": [
            "postman_handoff_ready",
            "delivery_finalization_only",
            "mailbox_mutation_deferred_to_r3",
        ],
        "created_at": utc_now_iso(),
    }
    validate_postman_delivery_handoff(handoff)
    return handoff
