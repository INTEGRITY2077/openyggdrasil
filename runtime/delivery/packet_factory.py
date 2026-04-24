from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, Optional

from delivery.mailbox_schema import validate_message
from harness_common import DEFAULT_VAULT, utc_now_iso


def default_delivery(*, profile: str, session_id: Optional[str]) -> Dict[str, Any]:
    payload = {
        "mode": "push_ready",
        "channel": "hermes-inbox",
        "profile_target": profile,
    }
    if session_id:
        payload["session_target"] = session_id
    return payload


def build_graph_hint_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    topic: str,
    source_paths: Iterable[str],
    facts: Iterable[str],
    human_summary: str,
    relevance_score: float = 0.85,
    confidence_score: float = 0.85,
    query_text: Optional[str] = None,
    producer: str = "observer-daemon",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source_paths": list(source_paths),
        "facts": list(facts),
        "relevance_score": relevance_score,
        "confidence_score": confidence_score,
    }
    if query_text:
        payload["query_text"] = query_text

    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "graph_hint",
        "kind": "packet",
        "parent_question_id": parent_question_id,
        "producer": producer,
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "medium",
        "scope": {
            "provider_id": provider_id,
            "profile": profile,
            "vault_path": str(DEFAULT_VAULT.resolve()),
            "topic": topic,
        },
        "payload": payload,
        "delivery": default_delivery(profile=profile, session_id=session_id),
        "human_summary": human_summary,
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_decision_candidate_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    decision_candidate: Dict[str, Any],
    producer: str = "decision-capture-executor",
) -> Dict[str, Any]:
    topic = str(
        decision_candidate.get("topic_hint")
        or decision_candidate.get("surface_summary")
        or "decision candidate"
    ).strip() or "decision candidate"
    confidence_score = float(decision_candidate.get("confidence_score") or 0.0)
    facts = [
        str(decision_candidate.get("decision_text") or "").strip(),
        str(decision_candidate.get("rationale") or "").strip(),
    ]
    facts = [fact for fact in facts if fact]

    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "decision_candidate",
        "kind": "packet",
        "parent_question_id": parent_question_id,
        "producer": producer,
        "created_at": utc_now_iso(),
        "status": "new",
        "priority": "high",
        "scope": {
            "provider_id": provider_id,
            "profile": profile,
            "vault_path": str(DEFAULT_VAULT.resolve()),
            "topic": topic,
        },
        "payload": {
            "decision_candidate": decision_candidate,
            "facts": facts,
            "relevance_score": confidence_score,
            "confidence_score": confidence_score,
        },
        "delivery": default_delivery(profile=profile, session_id=session_id),
        "human_summary": str(decision_candidate.get("decision_text") or topic),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def is_push_ready_packet(message: Dict[str, Any]) -> bool:
    return (
        message.get("kind") == "packet"
        and message.get("status") == "new"
        and message.get("delivery", {}).get("mode") == "push_ready"
        and message.get("delivery", {}).get("channel") == "hermes-inbox"
    )
