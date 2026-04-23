from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from harness_common import DEFAULT_VAULT, utc_now_iso
from map_identity import build_claim_id, build_page_id, build_topic_id
from pathfinder import (
    _topic_page_title,
    _unanchored_bundle,
    parse_episode_blocks,
    render_pathfinder_anchor_via_hermes,
    validate_pathfinder_bundle,
)
from provenance_store import parse_provenance_records, provenance_page_path
from topic_episode_placement_engine import list_existing_topics


def _topic_key_from_topic_id(topic_id: str) -> str:
    return str(topic_id).split(":", 1)[1]


def _canonical_relative_path_for_topic(topic_id: str) -> str:
    return f"queries/{_topic_key_from_topic_id(topic_id)}.md"


def _load_topic_page(*, topic_id: str, vault_root: Path) -> tuple[Path, str, str, str]:
    canonical_relative_path = _canonical_relative_path_for_topic(topic_id)
    page_path = vault_root / canonical_relative_path
    if not page_path.exists():
        raise FileNotFoundError(f"Topic page does not exist: {canonical_relative_path}")
    text = page_path.read_text(encoding="utf-8")
    anchor_title = _topic_page_title(
        text,
        fallback=page_path.stem.replace("-", " ").title(),
    )
    page_id = build_page_id(canonical_relative_path)
    return page_path, text, anchor_title, page_id


def _normalize_provenance_row(row: Mapping[str, Any], *, lane: str) -> dict[str, Any]:
    return {
        "topic_id": str(row.get("topic_id") or ""),
        "episode_id": str(row.get("episode_id") or ""),
        "claim_id": str(row.get("claim_id") or ""),
        "support_fact": str(row.get("answer_summary") or row.get("question_summary") or "").strip(),
        "source_rel": str(row.get("promoted_from") or row.get("derived_from") or "").strip(),
        "lane": lane,
    }


def _fallback_rows_from_episode_blocks(
    *,
    topic_id: str,
    text: str,
    lane: str,
) -> list[dict[str, Any]]:
    rows = []
    for block in parse_episode_blocks(text):
        episode_id = str(block["episode_id"])
        rows.append(
            {
                "topic_id": topic_id,
                "episode_id": episode_id,
                "claim_id": build_claim_id(topic_id=topic_id, claim_key=f"{episode_id}:summary"),
                "support_fact": str(block.get("summary") or "").strip(),
                "source_rel": "",
                "lane": lane,
            }
        )
    return rows


def find_region(*, query_text: str, vault_root: Path = DEFAULT_VAULT) -> dict[str, Any]:
    _ = query_text
    _ = vault_root
    return {
        "region_id": "region:canonical-queries",
        "region_key": "canonical-queries",
        "region_title": "Canonical Query Region",
        "reason_labels": ["mvp_default_region"],
        "summary": "The current MVP keeps Pathfinder search inside the canonical query region.",
    }


def find_topic_anchor(
    *,
    query_text: str,
    region_id: str | None = None,
    vault_root: Path = DEFAULT_VAULT,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _ = region_id
    existing_topics = list_existing_topics(vault_root=vault_root)
    active_evaluator = evaluator or render_pathfinder_anchor_via_hermes
    raw_anchor = active_evaluator(query_text=query_text, existing_topics=existing_topics)
    topic_key = str(raw_anchor.get("topic_key") or "").strip()
    if not topic_key or topic_key.lower() == "null":
        return {
            "anchor_type": "none",
            "topic_id": None,
            "topic_key": None,
            "page_id": None,
            "anchor_title": None,
            "reason_labels": list(raw_anchor.get("reason_labels") or []),
            "summary": str(raw_anchor.get("summary") or "").strip(),
        }
    topic_id = build_topic_id(topic_key)
    canonical_relative_path = _canonical_relative_path_for_topic(topic_id)
    page_id = build_page_id(canonical_relative_path)
    page_path = vault_root / canonical_relative_path
    anchor_title = page_path.stem.replace("-", " ").title()
    if page_path.exists():
        anchor_title = _topic_page_title(
            page_path.read_text(encoding="utf-8"),
            fallback=anchor_title,
        )
    return {
        "anchor_type": "topic",
        "topic_id": topic_id,
        "topic_key": topic_key,
        "page_id": page_id,
        "anchor_title": anchor_title,
        "reason_labels": list(raw_anchor.get("reason_labels") or []),
        "summary": str(raw_anchor.get("summary") or "").strip(),
    }


def get_origin_claims(
    *,
    topic_id: str,
    vault_root: Path = DEFAULT_VAULT,
    limit: int = 1,
) -> list[dict[str, Any]]:
    page_path, text, _, _ = _load_topic_page(topic_id=topic_id, vault_root=vault_root)
    provenance_path = provenance_page_path(vault_root=vault_root, topic_id=topic_id)
    if provenance_path.exists():
        rows = sorted(parse_provenance_records(provenance_path.read_text(encoding="utf-8")), key=lambda row: row["episode_id"])
        return [_normalize_provenance_row(row, lane="origin") for row in rows[: max(1, limit)]]
    rows = _fallback_rows_from_episode_blocks(topic_id=topic_id, text=text, lane="origin")
    return rows[: max(1, limit)]


def get_recent_episodes(
    *,
    topic_id: str,
    vault_root: Path = DEFAULT_VAULT,
    limit: int = 3,
) -> list[dict[str, Any]]:
    page_path, text, _, _ = _load_topic_page(topic_id=topic_id, vault_root=vault_root)
    provenance_path = provenance_page_path(vault_root=vault_root, topic_id=topic_id)
    if provenance_path.exists():
        rows = sorted(
            parse_provenance_records(provenance_path.read_text(encoding="utf-8")),
            key=lambda row: row["episode_id"],
            reverse=True,
        )
        return [_normalize_provenance_row(row, lane="recent") for row in rows[: max(1, limit)]]
    rows = sorted(
        _fallback_rows_from_episode_blocks(topic_id=topic_id, text=text, lane="recent"),
        key=lambda row: row["episode_id"],
        reverse=True,
    )
    return rows[: max(1, limit)]


def get_raw_sources(
    *,
    topic_id: str,
    claim_ids: list[str] | None = None,
    vault_root: Path = DEFAULT_VAULT,
) -> list[str]:
    claim_filter = {str(item) for item in claim_ids or [] if str(item)}
    page_path, _, _, _ = _load_topic_page(topic_id=topic_id, vault_root=vault_root)
    provenance_path = provenance_page_path(vault_root=vault_root, topic_id=topic_id)
    resolved: set[str] = {str(page_path.resolve())}
    if provenance_path.exists():
        resolved.add(str(provenance_path.resolve()))
        for row in parse_provenance_records(provenance_path.read_text(encoding="utf-8")):
            if claim_filter and str(row.get("claim_id") or "") not in claim_filter:
                continue
            source_rel = str(row.get("promoted_from") or row.get("derived_from") or "").strip()
            if source_rel:
                resolved.add(str((vault_root / source_rel).resolve()))
    return sorted(resolved)


def build_support_bundle(
    *,
    query_text: str,
    anchor: Mapping[str, Any],
    origin_rows: list[Mapping[str, Any]],
    recent_rows: list[Mapping[str, Any]],
    source_paths: list[str],
) -> dict[str, Any]:
    if anchor.get("topic_id") is None:
        return _unanchored_bundle(query_text=query_text)

    topic_id = str(anchor["topic_id"])
    canonical_relative_path = _canonical_relative_path_for_topic(topic_id)
    page_id = build_page_id(canonical_relative_path)

    lane_rows: list[Mapping[str, Any]] = []
    seen_claim_ids: set[str] = set()
    for row in list(recent_rows) + list(origin_rows):
        claim_id = str(row.get("claim_id") or "").strip()
        if not claim_id or claim_id in seen_claim_ids:
            continue
        seen_claim_ids.add(claim_id)
        lane_rows.append(row)

    support_facts: list[str] = []
    for row in lane_rows:
        fact = str(row.get("support_fact") or "").strip()
        if fact and fact not in support_facts:
            support_facts.append(fact)

    bundle = {
        "schema_version": "pathfinder.v1",
        "query_text": query_text,
        "anchor_type": "topic",
        "anchor_id": topic_id,
        "topic_id": topic_id,
        "anchor_title": str(anchor.get("anchor_title") or "").strip() or None,
        "episode_ids": [str(row.get("episode_id") or "") for row in lane_rows if str(row.get("episode_id") or "")],
        "claim_ids": [str(row.get("claim_id") or "") for row in lane_rows if str(row.get("claim_id") or "")],
        "page_ids": [page_id],
        "source_paths": list(source_paths),
        "support_facts": support_facts,
        "bundle_mode": "topic-page-recent-origin",
        "generated_at": utc_now_iso(),
    }
    validate_pathfinder_bundle(bundle)
    return bundle


def build_unanchored_bundle(*, query_text: str) -> dict[str, Any]:
    return _unanchored_bundle(query_text=query_text)
