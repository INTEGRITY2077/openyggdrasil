from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any, Callable, Mapping

from harness_common import DEFAULT_VAULT, utc_now_iso
from common.map_identity import build_claim_id, build_page_id, build_topic_id
from provenance.provenance_store import parse_provenance_records, provenance_page_path
from placement.topic_episode_placement_engine import list_existing_topics
from retrieval.pathfinder import (
    _topic_page_title,
    _unanchored_bundle,
    parse_episode_blocks,
    render_pathfinder_anchor_via_hermes,
    validate_pathfinder_bundle,
)


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


def locate_region(*, query_text: str, vault_root: Path = DEFAULT_VAULT) -> dict[str, Any]:
    _ = query_text
    _ = vault_root
    return {
        "region_id": "region:canonical-queries",
        "region_key": "canonical-queries",
        "region_title": "Canonical Query Region",
        "reason_labels": ["mvp_default_region"],
        "summary": "The current MVP keeps Pathfinder search inside the canonical query region.",
    }


def select_topic_anchor(
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


def read_recent_claims(
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


def read_source_paths(
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


def assemble_unanchored_bundle(*, query_text: str) -> dict[str, Any]:
    return _unanchored_bundle(query_text=query_text)


def _extract_json_objects_from_fenced_blocks(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        elif isinstance(parsed, list):
            records.extend(item for item in parsed if isinstance(item, dict))
    return records


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _extract_ring_ids(text: str, records: list[Mapping[str, Any]]) -> list[str]:
    ring_ids = [str(row.get("ring_id") or "") for row in records]
    for line in text.splitlines():
        m = re.match(r"\s*-?\s*ring_id\s*:\s*([0-9A-Za-z가-힣:_-]+)\s*$", line)
        if m:
            ring_ids.append(m.group(1))
    return _unique_preserve_order(ring_ids)


def _extract_community_ids(text: str, records: list[Mapping[str, Any]]) -> list[str]:
    community_ids = [str(row.get("community_id") or "") for row in records]
    community_ids.extend(re.findall(r"community:[0-9A-Za-z가-힣:_-]+", text))
    return _unique_preserve_order(community_ids)


def _select_ring_topic_key(*, query_text: str, vault_root: Path) -> str | None:
    query_words = {w for w in re.split(r"\s+", query_text.lower()) if w}
    best: tuple[int, str] | None = None
    for path in (vault_root / "queries").glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "ring_id" not in text and "Provenance Rings" not in text and "community_id" not in text:
            continue
        hay = text.lower()
        score = sum(1 for word in query_words if word and word in hay)
        if score <= 0:
            score = 1
        key = path.stem
        if best is None or score > best[0]:
            best = (score, key)
    return best[1] if best else None


def build_ring_support_bundle(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    topic_key: str | None = None,
) -> dict[str, Any]:
    """나이테 기억 노드용 origin/recent/source/community/edge 혼합 support bundle을 구성한다.

    POC용 고정 경로다. 기존 Pathfinder bundle을 대체하지 않고 provenance ring node가
    감지될 때 OP2 receipt 안에 추가로 싣는다.
    """
    selected_topic_key = topic_key or _select_ring_topic_key(query_text=query_text, vault_root=vault_root)
    if not selected_topic_key:
        return {
            "schema_version": "ring_support_bundle.v1",
            "bundle_mode": "provenance-ring-mixed",
            "query_text": query_text,
            "ring_ids": [],
            "origin_claims": [],
            "recent_rings": [],
            "source_paths": [],
            "community_edges": [],
            "semantic_edges": [],
        }

    topic_path = vault_root / "queries" / f"{selected_topic_key}.md"
    topic_text = topic_path.read_text(encoding="utf-8", errors="ignore") if topic_path.exists() else ""
    prov_path = vault_root / "_meta" / "provenance" / f"{selected_topic_key}.md"
    prov_text = prov_path.read_text(encoding="utf-8", errors="ignore") if prov_path.exists() else ""
    records = _extract_json_objects_from_fenced_blocks(prov_text)
    if not records:
        # 기존 parser가 이해하는 페이지면 그 결과도 보조로 사용한다.
        try:
            records = list(parse_provenance_records(prov_text))
        except Exception:
            records = []
    all_text = topic_text + "\n" + prov_text
    ring_ids = _extract_ring_ids(all_text, records)
    community_ids = _extract_community_ids(all_text, records)
    origin_claims = [
        {
            "episode_id": str(row.get("episode_id") or ""),
            "claim_id": str(row.get("claim_id") or ""),
            "support_fact": str(row.get("support_fact") or row.get("answer_summary") or row.get("question_summary") or ""),
            "source_rel": str(row.get("derived_from") or row.get("promoted_from") or ""),
            "lane": "origin",
        }
        for row in records
    ]
    recent_rings = [
        {
            "ring_id": str(row.get("ring_id") or ring_id),
            "episode_id": str(row.get("episode_id") or ""),
            "source_ref": str(row.get("source_ref") or ""),
            "origin_locator": str(row.get("origin_locator") or ""),
            "lane": "recent",
        }
        for ring_id in ring_ids
        for row in (records or [{"ring_id": ring_id}])
        if str(row.get("ring_id") or ring_id) == ring_id
    ]
    source_paths: list[str] = []
    if topic_path.exists():
        source_paths.append(str(topic_path.resolve()))
    if prov_path.exists():
        source_paths.append(str(prov_path.resolve()))
    for row in records:
        rel = str(row.get("derived_from") or row.get("promoted_from") or "").strip()
        if rel:
            source_paths.append(str((vault_root / rel).resolve()))
    community_edges = [
        {
            "community_id": cid,
            "ring_ids": ring_ids,
            "topic_key": selected_topic_key,
            "lane": "community_edges",
        }
        for cid in community_ids
    ]
    semantic_edges = [
        {
            "type": "PROVENANCE_RING_SUPPORTS",
            "ring_id": ring_id,
            "topic_key": selected_topic_key,
            "query_text": query_text,
        }
        for ring_id in ring_ids
    ]
    return {
        "schema_version": "ring_support_bundle.v1",
        "bundle_mode": "provenance-ring-mixed",
        "query_text": query_text,
        "topic_key": selected_topic_key,
        "ring_ids": ring_ids,
        "origin_claims": origin_claims,
        "recent_rings": recent_rings,
        "source_paths": _unique_preserve_order(source_paths),
        "community_edges": community_edges,
        "semantic_edges": semantic_edges,
    }
