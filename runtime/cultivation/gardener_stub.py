from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from admission.decision_contracts import validate_cultivated_decision, validate_engraved_seed
from common.map_identity import build_claim_id
from harness_common import DEFAULT_VAULT, utc_now_iso
from placement.topic_page_filing import render_topic_page
from provenance.provenance_store import (
    provenance_page_path,
    provenance_relative_path,
    render_provenance_page,
)


def _question_text(seed: Mapping[str, Any]) -> str:
    surface_summary = str(seed.get("surface_summary") or "").strip()
    trigger_reason = str(seed.get("trigger_reason") or "").strip()
    if surface_summary and trigger_reason:
        return f"{surface_summary}\n\nTrigger reason: {trigger_reason}"
    return surface_summary or trigger_reason or "Decision surface captured by provider foreground session."


def _answer_text(seed: Mapping[str, Any]) -> str:
    decision_text = str(seed.get("decision_text") or "").strip()
    rationale = str(seed.get("rationale") or "").strip()
    if decision_text and rationale:
        return f"{decision_text}\n\nRationale: {rationale}"
    return decision_text or rationale or "(no decision text)"


def cultivate_decision_seed(
    *,
    engraved_seed: Mapping[str, Any],
    vault_root: Path = DEFAULT_VAULT,
) -> dict[str, Any]:
    validate_engraved_seed(engraved_seed)
    if not bool(engraved_seed.get("planting_ready")):
        raise ValueError(
            f"Nursery seed is not planting-ready: {str(engraved_seed.get('integrity_reason') or 'unknown')}"
        )
    active_vault_root = vault_root.resolve()
    canonical_relative_path = str(engraved_seed["canonical_relative_path"])
    topic_path = active_vault_root / canonical_relative_path
    provenance_path = provenance_page_path(vault_root=active_vault_root, topic_id=str(engraved_seed["topic_id"]))
    source_rel = canonical_relative_path
    created = utc_now_iso()
    placement_verdict = {
        "topic_title": str(engraved_seed["topic_title"]),
        "page_id": str(engraved_seed["page_id"]),
        "topic_id": str(engraved_seed["topic_id"]),
        "episode_id": str(engraved_seed["episode_id"]),
        "session_id": "decision-roundtrip-mvp",
        "profile": "system",
    }
    question = _question_text(engraved_seed)
    answer = _answer_text(engraved_seed)

    existing_topic = topic_path.read_text(encoding="utf-8") if topic_path.exists() else None
    topic_text = render_topic_page(
        existing_text=existing_topic,
        placement_verdict=placement_verdict,
        source_rel=source_rel,
        question=question,
        answer=answer,
        created=created,
    )
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    topic_path.write_text(topic_text, encoding="utf-8")

    existing_provenance = provenance_path.read_text(encoding="utf-8") if provenance_path.exists() else None
    provenance_text = render_provenance_page(
        existing_text=existing_provenance,
        placement_verdict=placement_verdict,
        source_rel=source_rel,
        question=question,
        answer=answer,
        created=created,
    )
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(provenance_text, encoding="utf-8")

    cultivated = {
        "schema_version": "cultivated_decision.v1",
        "cultivation_id": uuid.uuid4().hex,
        "seed_id": str(engraved_seed["seed_id"]),
        "candidate_id": str(engraved_seed["candidate_id"]),
        "topic_id": str(engraved_seed["topic_id"]),
        "topic_title": str(engraved_seed["topic_title"]),
        "page_id": str(engraved_seed["page_id"]),
        "canonical_relative_path": canonical_relative_path,
        "provenance_relative_path": provenance_relative_path(topic_id=str(engraved_seed["topic_id"])),
        "canonical_note_path": str(topic_path.resolve()),
        "provenance_note_path": str(provenance_path.resolve()),
        "claim_id": build_claim_id(
            topic_id=str(engraved_seed["topic_id"]),
            claim_key=f"{str(engraved_seed['episode_id'])}:summary",
        ),
        "decision_text": str(engraved_seed["decision_text"]),
        "support_fact": str(engraved_seed["decision_text"]),
        "source_rel": source_rel,
        "cultivated_at": created,
    }
    validate_cultivated_decision(cultivated)
    return cultivated
