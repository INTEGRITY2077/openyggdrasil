from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.decision_contracts import (
    validate_admission_verdict,
    validate_decision_candidate,
    validate_evaluator_amundsen_handoff,
)
from common.map_identity import build_episode_id, build_page_id, build_topic_id
from harness_common import utc_now_iso
from admission.amundsen_stub import (
    canonical_relative_path_for_topic,
    classify_continent_proposal,
    topic_key_from_candidate,
    topic_title_from_key,
)


def admit_decision_candidate(
    *,
    decision_candidate: Mapping[str, Any],
    vault_root: Path | None = None,
) -> dict[str, Any]:
    validate_decision_candidate(decision_candidate)
    topic_key = topic_key_from_candidate(decision_candidate)
    topic_id = build_topic_id(topic_key)
    canonical_relative_path = canonical_relative_path_for_topic(topic_key)
    page_id = build_page_id(canonical_relative_path)
    episode_key = (
        f"turn-{int(decision_candidate['turn_start'])}-{int(decision_candidate['turn_end'])}"
        f"-{str(decision_candidate['candidate_id'])[:8]}"
    )
    rationale_code = (
        str((decision_candidate.get("reason_labels") or ["decision_candidate_admitted"])[0]).strip()
        or "decision_candidate_admitted"
    )
    continent_proposal = classify_continent_proposal(
        decision_candidate=decision_candidate,
        vault_root=vault_root if vault_root is not None else Path("."),
    ) if vault_root is not None else classify_continent_proposal(decision_candidate=decision_candidate)
    verdict = {
        "schema_version": "admission_verdict.v1",
        "verdict_id": uuid.uuid4().hex,
        "candidate_id": str(decision_candidate["candidate_id"]),
        "provider_id": str(decision_candidate["provider_id"]),
        "provider_profile": str(decision_candidate["provider_profile"]),
        "provider_session_id": str(decision_candidate["provider_session_id"]),
        "session_uid": str(decision_candidate["session_uid"]),
        "admission_status": "accepted",
        "topic_key": topic_key,
        "topic_id": topic_id,
        "topic_title": topic_title_from_key(topic_key),
        "page_id": page_id,
        "canonical_relative_path": canonical_relative_path,
        "episode_id": build_episode_id(topic_id=topic_id, episode_key=episode_key),
        "continent_key": continent_proposal["continent_key"],
        "continent_id": continent_proposal["continent_id"],
        "continent_title": continent_proposal["continent_title"],
        "continent_decision": continent_proposal["continent_decision"],
        "route_reason": continent_proposal["route_reason"],
        "rationale_code": rationale_code,
        "admitted_at": utc_now_iso(),
    }
    validate_admission_verdict(verdict)
    return verdict


def admit_evaluator_handoff(
    *,
    evaluator_amundsen_handoff: Mapping[str, Any],
    vault_root: Path | None = None,
) -> dict[str, Any]:
    """Admit only candidates that Evaluator explicitly handed to Amundsen."""

    validate_evaluator_amundsen_handoff(evaluator_amundsen_handoff)
    if evaluator_amundsen_handoff.get("handoff_status") != "ready_for_amundsen":
        raise ValueError(str(evaluator_amundsen_handoff.get("blocked_reason") or "handoff_not_ready"))
    if evaluator_amundsen_handoff.get("semantic_worth_authority") != "evaluator_only":
        raise ValueError("semantic_worth_authority must remain evaluator_only")
    if evaluator_amundsen_handoff.get("category_authority") != "amundsen_only_after_handoff":
        raise ValueError("category_authority must be amundsen_only_after_handoff")
    return admit_decision_candidate(
        decision_candidate=dict(evaluator_amundsen_handoff["decision_candidate"]),
        vault_root=vault_root,
    )
