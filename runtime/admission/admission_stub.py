from __future__ import annotations

import uuid
from typing import Any, Mapping

from admission.decision_contracts import validate_admission_verdict, validate_decision_candidate
from common.map_identity import build_episode_id, build_page_id, build_topic_id, normalize_key
from harness_common import utc_now_iso


def _topic_key_from_candidate(decision_candidate: Mapping[str, Any]) -> str:
    candidate_hint = str(decision_candidate.get("topic_hint") or "").strip()
    if candidate_hint:
        return normalize_key(candidate_hint)
    decision_text = str(decision_candidate.get("decision_text") or "").strip()
    if decision_text:
        return normalize_key(decision_text[:96])
    return normalize_key(str(decision_candidate.get("surface_summary") or "decision-candidate"))


def _topic_title_from_key(topic_key: str) -> str:
    title = topic_key.replace("/", " ").replace("-", " ").replace("_", " ").strip()
    return " ".join(part.capitalize() for part in title.split()) or "Decision Candidate"


def admit_decision_candidate(*, decision_candidate: Mapping[str, Any]) -> dict[str, Any]:
    validate_decision_candidate(decision_candidate)
    topic_key = _topic_key_from_candidate(decision_candidate)
    topic_id = build_topic_id(topic_key)
    canonical_relative_path = f"queries/{topic_key}.md"
    page_id = build_page_id(canonical_relative_path)
    episode_key = (
        f"turn-{int(decision_candidate['turn_start'])}-{int(decision_candidate['turn_end'])}"
        f"-{str(decision_candidate['candidate_id'])[:8]}"
    )
    rationale_code = (
        str((decision_candidate.get("reason_labels") or ["decision_candidate_admitted"])[0]).strip()
        or "decision_candidate_admitted"
    )
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
        "topic_title": _topic_title_from_key(topic_key),
        "page_id": page_id,
        "canonical_relative_path": canonical_relative_path,
        "episode_id": build_episode_id(topic_id=topic_id, episode_key=episode_key),
        "rationale_code": rationale_code,
        "admitted_at": utc_now_iso(),
    }
    validate_admission_verdict(verdict)
    return verdict
