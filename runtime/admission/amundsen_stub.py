from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from common.map_identity import normalize_key
from harness_common import DEFAULT_VAULT
from admission.decision_contracts import validate_decision_candidate


def topic_key_from_candidate(decision_candidate: Mapping[str, Any]) -> str:
    candidate_hint = str(decision_candidate.get("topic_hint") or "").strip()
    if candidate_hint:
        return normalize_key(candidate_hint)
    decision_text = str(decision_candidate.get("decision_text") or "").strip()
    if decision_text:
        return normalize_key(decision_text[:96])
    return normalize_key(str(decision_candidate.get("surface_summary") or "decision-candidate"))


def topic_title_from_key(topic_key: str) -> str:
    title = topic_key.replace("/", " ").replace("-", " ").replace("_", " ").strip()
    return " ".join(part.capitalize() for part in title.split()) or "Decision Candidate"


def continent_key_from_topic_key(topic_key: str) -> str:
    head = topic_key.split("/", 1)[0]
    first = head.split("-", 1)[0].split("_", 1)[0].strip()
    return normalize_key(first or head or topic_key)


def continent_title_from_key(continent_key: str) -> str:
    return " ".join(part.capitalize() for part in continent_key.replace("-", " ").replace("_", " ").split()) or "Continent"


def build_continent_id(continent_key: str) -> str:
    return f"continent:{normalize_key(continent_key)}"


def canonical_relative_path_for_topic(topic_key: str) -> str:
    return f"queries/{normalize_key(topic_key)}.md"


def classify_continent_proposal(
    *,
    decision_candidate: Mapping[str, Any],
    vault_root: Path = DEFAULT_VAULT,
) -> dict[str, str]:
    validate_decision_candidate(decision_candidate)
    topic_key = topic_key_from_candidate(decision_candidate)
    continent_key = continent_key_from_topic_key(topic_key)
    continent_id = build_continent_id(continent_key)
    continent_title = continent_title_from_key(continent_key)
    active_vault_root = vault_root.resolve()
    canonical_relative_path = canonical_relative_path_for_topic(topic_key)
    canonical_path = active_vault_root / canonical_relative_path
    if canonical_path.exists():
        return {
            "continent_key": continent_key,
            "continent_id": continent_id,
            "continent_title": continent_title,
            "continent_decision": "existing_continent",
            "route_reason": "existing_canonical_page_present",
        }

    has_existing_signal = any(
        path.stem.lower().startswith(continent_key.lower())
        for path in active_vault_root.rglob("*.md")
        if path.is_file()
    )
    if has_existing_signal:
        return {
            "continent_key": continent_key,
            "continent_id": continent_id,
            "continent_title": continent_title,
            "continent_decision": "existing_continent",
            "route_reason": "existing_continent_signal_present",
        }
    return {
        "continent_key": continent_key,
        "continent_id": continent_id,
        "continent_title": continent_title,
        "continent_decision": "new_continent",
        "route_reason": "new_continent_required",
    }
