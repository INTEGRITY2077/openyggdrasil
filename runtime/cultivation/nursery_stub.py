from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_decision_candidate,
    validate_engraved_seed,
)
from harness_common import utc_now_iso


def engrave_decision_seed(
    *,
    admission_verdict: Mapping[str, Any],
    decision_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    validate_admission_verdict(admission_verdict)
    validate_decision_candidate(decision_candidate)
    seed = {
        "schema_version": "engraved_seed.v1",
        "seed_id": uuid.uuid4().hex,
        "verdict_id": str(admission_verdict["verdict_id"]),
        "candidate_id": str(decision_candidate["candidate_id"]),
        "topic_key": str(admission_verdict["topic_key"]),
        "topic_id": str(admission_verdict["topic_id"]),
        "topic_title": str(admission_verdict["topic_title"]),
        "page_id": str(admission_verdict["page_id"]),
        "canonical_relative_path": str(admission_verdict["canonical_relative_path"]),
        "episode_id": str(admission_verdict["episode_id"]),
        "surface_summary": str(decision_candidate.get("surface_summary") or "").strip(),
        "trigger_reason": str(decision_candidate.get("trigger_reason") or "").strip(),
        "decision_text": str(decision_candidate.get("decision_text") or "").strip(),
        "rationale": str(decision_candidate.get("rationale") or "").strip(),
        "alternatives_rejected": list(decision_candidate.get("alternatives_rejected") or []),
        "stability_state": str(decision_candidate.get("stability_state") or "provisional").strip(),
        "source_ref": decision_candidate.get("source_ref"),
        "origin_locator": dict(decision_candidate.get("origin_locator") or {}),
        "engraved_at": utc_now_iso(),
    }
    validate_engraved_seed(seed)
    return seed
