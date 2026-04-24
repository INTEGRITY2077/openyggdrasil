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
        "human_summary": str(decision_candidate.get("decision_text") or topic),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_admission_verdict_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    admission_verdict: Dict[str, Any],
    producer: str = "decision-roundtrip-once",
) -> Dict[str, Any]:
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "admission_verdict",
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
            "topic": str(admission_verdict.get("topic_title") or admission_verdict.get("topic_key") or ""),
        },
        "payload": {
            "admission_verdict": admission_verdict,
            "facts": [str(admission_verdict.get("topic_title") or "").strip()],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
        },
        "human_summary": (
            f"Admission accepted for {str(admission_verdict.get('topic_title') or '').strip() or 'decision candidate'}."
        ),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_engraved_seed_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    engraved_seed: Dict[str, Any],
    producer: str = "decision-roundtrip-once",
) -> Dict[str, Any]:
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "engraved_seed",
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
            "topic": str(engraved_seed.get("topic_title") or engraved_seed.get("topic_key") or ""),
        },
        "payload": {
            "engraved_seed": engraved_seed,
            "facts": [
                str(engraved_seed.get("seed_identity_key") or "").strip(),
                str(engraved_seed.get("integrity_reason") or "").strip(),
            ],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
        },
        "human_summary": (
            f"Nursery engraved seed {str(engraved_seed.get('seed_identity_key') or '').strip()} "
            f"with integrity {str(engraved_seed.get('integrity_status') or '').strip()}."
        ),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_planting_decision_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    planting_decision: Dict[str, Any],
    producer: str = "decision-roundtrip-once",
) -> Dict[str, Any]:
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "planting_decision",
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
            "topic": str(planting_decision.get("topic_title") or planting_decision.get("topic_id") or ""),
        },
        "payload": {
            "planting_decision": planting_decision,
            "facts": [
                str(planting_decision.get("planting_target_key") or "").strip(),
                str(planting_decision.get("growth_decision") or "").strip(),
                str(planting_decision.get("pruning_decision") or "").strip(),
            ],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
        },
        "human_summary": (
            f"Gardener planted into {str(planting_decision.get('planting_target_key') or '').strip()} "
            f"with growth={str(planting_decision.get('growth_decision') or '').strip()}."
        ),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_cultivated_decision_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    cultivated_decision: Dict[str, Any],
    producer: str = "decision-roundtrip-once",
) -> Dict[str, Any]:
    source_paths = [
        str(cultivated_decision.get("canonical_note_path") or "").strip(),
        str(cultivated_decision.get("provenance_note_path") or "").strip(),
    ]
    source_paths = [path for path in source_paths if path]
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "cultivated_decision",
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
            "topic": str(cultivated_decision.get("topic_title") or cultivated_decision.get("topic_id") or ""),
        },
        "payload": {
            "cultivated_decision": cultivated_decision,
            "source_paths": source_paths,
            "facts": [str(cultivated_decision.get("support_fact") or "").strip()],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
        },
        "human_summary": (
            f"Cultivated canonical decision page at {str(cultivated_decision.get('canonical_relative_path') or '').strip()}."
        ),
    }
    if session_id:
        message["scope"]["session_id"] = session_id
    validate_message(message)
    return message


def build_map_topography_packet(
    *,
    provider_id: str = "hermes",
    profile: str,
    session_id: Optional[str],
    parent_question_id: Optional[str] = None,
    map_topography: Dict[str, Any],
    producer: str = "decision-roundtrip-once",
) -> Dict[str, Any]:
    message = {
        "schema_version": "mailbox.v1",
        "message_id": uuid.uuid4().hex,
        "message_type": "map_topography",
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
            "topic": str(map_topography.get("topic_title") or map_topography.get("topic_id") or ""),
        },
        "payload": {
            "map_topography": map_topography,
            "facts": [
                str(map_topography.get("continent_key") or "").strip(),
                str(map_topography.get("bed_id") or "").strip(),
                str(map_topography.get("canonical_relative_path") or "").strip(),
            ],
            "confidence_score": 1.0,
            "relevance_score": 1.0,
        },
        "human_summary": (
            f"Map Maker aligned {str(map_topography.get('canonical_relative_path') or '').strip()} "
            f"inside {str(map_topography.get('bed_id') or '').strip()}."
        ),
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
