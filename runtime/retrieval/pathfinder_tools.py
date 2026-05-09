from __future__ import annotations

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
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
from retrieval.recall_digest import build_recall_digest_from_support_bundle
from memory.wiki_node_taxonomy import coerce_node_taxonomy


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


def find_region(*, query_text: str, vault_root: Path = DEFAULT_VAULT) -> dict[str, Any]:
    """Backward-compatible alias for older Pathfinder PTC imports."""
    return locate_region(query_text=query_text, vault_root=vault_root)


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


def find_topic_anchor(
    *,
    query_text: str,
    region_id: str | None = None,
    vault_root: Path = DEFAULT_VAULT,
    evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias for older Pathfinder PTC imports."""
    return select_topic_anchor(
        query_text=query_text,
        region_id=region_id,
        vault_root=vault_root,
        evaluator=evaluator,
    )


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


def get_recent_episodes(
    *,
    topic_id: str,
    vault_root: Path = DEFAULT_VAULT,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Backward-compatible alias for older Pathfinder PTC imports."""
    return read_recent_claims(topic_id=topic_id, vault_root=vault_root, limit=limit)


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


def get_raw_sources(
    *,
    topic_id: str,
    claim_ids: list[str] | None = None,
    vault_root: Path = DEFAULT_VAULT,
) -> list[str]:
    """Backward-compatible alias for older Pathfinder PTC imports."""
    return read_source_paths(topic_id=topic_id, claim_ids=claim_ids, vault_root=vault_root)


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


def build_unanchored_bundle(*, query_text: str) -> dict[str, Any]:
    """Backward-compatible alias for older Pathfinder PTC imports."""
    return assemble_unanchored_bundle(query_text=query_text)


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


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", text, flags=re.MULTILINE)
    return match.group(1).strip().strip('"\'') if match else ""


def _first_record_with(records: list[Mapping[str, Any]], *keys: str) -> Mapping[str, Any]:
    for record in records:
        if all(str(record.get(key) or "").strip() for key in keys):
            return record
    return {}


def _concept_node_path_for_topic(*, topic_text: str, vault_root: Path) -> Path | None:
    node_id = _yaml_scalar(topic_text, "id")
    if not node_id:
        return None
    candidate = vault_root / "concepts" / f"{node_id}.md"
    return candidate if candidate.exists() else None


def _community_path_for_id(*, community_id: str, vault_root: Path) -> Path | None:
    if not community_id.startswith("community:"):
        return None
    key = community_id.split(":", 1)[1]
    candidate = vault_root / "communities" / f"{key}.md"
    return candidate if candidate.exists() else None


def _extract_node_taxonomy(
    *,
    topic_text: str,
    concept_text: str,
    all_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    for record in all_records:
        value = record.get("node_taxonomy")
        if isinstance(value, Mapping):
            return coerce_node_taxonomy(value)
    fallback_payload = {
        "continent": _yaml_scalar(topic_text, "continent") or _yaml_scalar(concept_text, "continent") or "concepts",
        "node_type": (
            _yaml_scalar(topic_text, "node_type")
            or _yaml_scalar(concept_text, "node_type")
            or _yaml_scalar(topic_text, "type")
            or _yaml_scalar(concept_text, "type")
            or "concept"
        ),
        "topography_level": _yaml_scalar(topic_text, "topography_level") or _yaml_scalar(concept_text, "topography_level"),
        "community_role": _yaml_scalar(topic_text, "community_role") or _yaml_scalar(concept_text, "community_role"),
    }
    return coerce_node_taxonomy(
        None,
        fallback_payload=fallback_payload,
        physical_continent=str(fallback_payload["continent"] or "concepts"),
        default_node_type=str(fallback_payload["node_type"] or "concept"),
    )


def _candidate_paths_from_matched_nodes(*, matched_nodes: list[Mapping[str, Any]], vault_root: Path) -> list[Path]:
    paths: list[Path] = []
    for node in matched_nodes:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
        raw_paths = [
            node.get("_source_path"),
            node.get("source_path"),
            metadata.get("_source_path") if isinstance(metadata, Mapping) else None,
            metadata.get("source_path") if isinstance(metadata, Mapping) else None,
        ]
        for raw_path in raw_paths:
            if not raw_path:
                continue
            path_text = str(raw_path).strip().replace("\\", "/")
            if path_text.startswith("vault/"):
                candidate = vault_root / path_text.removeprefix("vault/")
            else:
                candidate = Path(path_text)
                if not candidate.is_absolute():
                    candidate = vault_root / candidate
            if candidate.exists():
                paths.append(candidate)

        metadata_node_id = metadata.get("node_id") if isinstance(metadata, Mapping) else ""
        node_id = str(node.get("node_id") or metadata_node_id or "").strip()
        if not node_id:
            continue
        for continent in ("concepts", "entities", "comparisons", "queries"):
            candidate = vault_root / continent / f"{node_id}.md"
            if candidate.exists():
                paths.append(candidate)
    seen: set[str] = set()
    unique_paths: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def _vault_source_path(path: Path, *, vault_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(vault_root.resolve())
        return f"vault/{relative.as_posix()}"
    except RECOVERABLE_RUNTIME_ERRORS:
        return str(path).replace("\\", "/")


def _topic_key_from_candidate_paths(*, candidate_paths: list[Path], vault_root: Path) -> str | None:
    tokens: set[str] = set()
    for path in candidate_paths:
        if path.parent.name == "queries":
            return path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        tokens.update(_extract_ring_ids(text, _extract_json_objects_from_fenced_blocks(text)))
        tokens.update(_extract_community_ids(text, _extract_json_objects_from_fenced_blocks(text)))
        for key in ("id", "canonical_node_id", "node_id"):
            value = _yaml_scalar(text, key)
            if value:
                tokens.add(value)
        source_ref = _yaml_scalar(text, "source_ref")
        if source_ref:
            tokens.add(source_ref)

    if not tokens:
        return None
    best: tuple[int, str] | None = None
    for query_path in (vault_root / "queries").glob("*.md"):
        text = query_path.read_text(encoding="utf-8", errors="ignore")
        score = sum(1 for token in tokens if token and token in text)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, query_path.stem)
    return best[1] if best else None


def _typed_unavailable_bundle(*, query_text: str, missing_refs: list[str]) -> dict[str, Any]:
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
        "typed_unavailable": {
            "schema_version": "typed_unavailable.v1",
            "unavailable_ref": f"oy-vault://op2-support-bundle/{build_page_id(query_text)[:32]}",
            "created_at": utc_now_iso(),
            "reason_code": "unresolved_evidence_ref",
            "blocked_stage": "recall_support_bundle",
            "missing_or_rejected_refs": [
                {
                    "ref": f"oy-vault://{ref}",
                    "reason_code": "unresolved_evidence_ref",
                    "rejection_kind": "unresolved",
                }
                for ref in missing_refs
            ],
            "raw_provider_material_included": False,
            "skill_body_included": False,
            "portable_local_path_included": False,
            "fabricated_answer": False,
            "no_overclaim_boundary": {
                "live_readiness_claimed": False,
                "production_readiness_claimed": False,
                "reasoning_lease_solved_claimed": False,
                "public_runtime_integration_complete_claimed": False,
                "readiness_91_percent_claimed": False,
            },
        },
    }


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
            continue
        key = path.stem
        if best is None or score > best[0]:
            best = (score, key)
    return best[1] if best else None


def build_ring_support_bundle(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    topic_key: str | None = None,
    matched_nodes: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """나이테 기억 노드용 origin/recent/source/community/edge 혼합 support bundle을 구성한다.

    POC용 고정 경로다. 기존 Pathfinder bundle을 대체하지 않고 provenance ring node가
    감지될 때 OP2 receipt 안에 추가로 싣는다.
    """
    selected_topic_key = topic_key
    if not selected_topic_key and matched_nodes:
        candidate_paths = _candidate_paths_from_matched_nodes(matched_nodes=matched_nodes, vault_root=vault_root)
        selected_topic_key = _topic_key_from_candidate_paths(candidate_paths=candidate_paths, vault_root=vault_root)
    if not selected_topic_key:
        selected_topic_key = _select_ring_topic_key(query_text=query_text, vault_root=vault_root)
    if not selected_topic_key:
        return _typed_unavailable_bundle(query_text=query_text, missing_refs=["queries/*", "concepts/PRN-*.md"])

    topic_path = vault_root / "queries" / f"{selected_topic_key}.md"
    topic_text = topic_path.read_text(encoding="utf-8", errors="ignore") if topic_path.exists() else ""
    prov_path = vault_root / "_meta" / "provenance" / f"{selected_topic_key}.md"
    prov_text = prov_path.read_text(encoding="utf-8", errors="ignore") if prov_path.exists() else ""
    concept_path = _concept_node_path_for_topic(topic_text=topic_text, vault_root=vault_root)
    concept_text = concept_path.read_text(encoding="utf-8", errors="ignore") if concept_path else ""

    records = _extract_json_objects_from_fenced_blocks(prov_text)
    if not records:
        # 기존 parser가 이해하는 페이지면 그 결과도 보조로 사용한다.
        try:
            records = list(parse_provenance_records(prov_text))
        except RECOVERABLE_RUNTIME_ERRORS:
            records = []
    prn_records = _extract_json_objects_from_fenced_blocks(topic_text + "\n" + concept_text)
    all_records = list(records) + list(prn_records)
    all_text = topic_text + "\n" + prov_text + "\n" + concept_text
    ring_ids = _extract_ring_ids(all_text, all_records)
    community_ids = _extract_community_ids(all_text, all_records)
    community_id = community_ids[0] if community_ids else ""
    ring_record = _first_record_with(all_records, "ring_id", "source_ref", "origin_locator", "provider_session_id") or _first_record_with(all_records, "ring_id", "source_ref", "origin_locator")
    paragraph_intent = _first_record_with(
        all_records,
        "intent_field",
        "decomposition_guard",
        "min_split_unit",
        "why_not_atomic",
    )
    lifecycle_record = _first_record_with(all_records, "state")
    node_taxonomy = _extract_node_taxonomy(topic_text=topic_text, concept_text=concept_text, all_records=all_records)
    community_path = _community_path_for_id(community_id=community_id, vault_root=vault_root) if community_id else None

    origin_claims = [
        {
            "episode_id": str(row.get("episode_id") or ""),
            "claim_id": str(row.get("claim_id") or ""),
            "support_fact": str(row.get("support_fact") or row.get("answer_summary") or row.get("question_summary") or ""),
            "source_rel": str(row.get("derived_from") or row.get("promoted_from") or ""),
            "source_ref": str(row.get("source_ref") or ""),
            "origin_locator": str(row.get("origin_locator") or ""),
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
            "provider_session_id": str(row.get("provider_session_id") or ""),
            "message_index_range": row.get("message_index_range") or None,
            "source_line_range": row.get("source_line_range") or None,
            "anchor_hash": str(row.get("anchor_hash") or ""),
            "commit_watermark": str(row.get("commit_watermark") or ""),
            "lane": "recent",
        }
        for ring_id in ring_ids
        for row in (all_records or [{"ring_id": ring_id}])
        if str(row.get("ring_id") or ring_id) == ring_id and (row.get("source_ref") or row.get("origin_locator") or row.get("episode_id"))
    ]
    source_paths: list[str] = []
    if topic_path.exists():
        source_paths.append(_vault_source_path(topic_path, vault_root=vault_root))
    if prov_path.exists():
        source_paths.append(_vault_source_path(prov_path, vault_root=vault_root))
    if concept_path and concept_path.exists():
        source_paths.append(_vault_source_path(concept_path, vault_root=vault_root))
    if community_path and community_path.exists():
        source_paths.append(_vault_source_path(community_path, vault_root=vault_root))
    for row in records:
        rel = str(row.get("derived_from") or row.get("promoted_from") or "").strip()
        if rel:
            source_paths.append(_vault_source_path(vault_root / rel, vault_root=vault_root))
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

    missing_refs: list[str] = []
    if not ring_ids:
        missing_refs.append("ring_id")
    if not ring_record:
        missing_refs.append("source_ref/origin_locator")
    if not paragraph_intent:
        missing_refs.append("paragraph_intent_safety_belt")
    if not community_ids:
        missing_refs.append("community_id")
    lifecycle_state = _yaml_scalar(topic_text, "lifecycle_state") or _yaml_scalar(concept_text, "lifecycle_state") or str(lifecycle_record.get("state") or "")
    if not lifecycle_state:
        missing_refs.append("lifecycle_state")
    if not source_paths:
        missing_refs.append("source_paths")
    if missing_refs:
        unavailable = _typed_unavailable_bundle(query_text=query_text, missing_refs=missing_refs)
        unavailable["topic_key"] = selected_topic_key
        unavailable["ring_ids"] = ring_ids
        unavailable["ring_id"] = ring_ids[0] if ring_ids else None
        unavailable["community_id"] = community_id or None
        unavailable["community_edges"] = community_edges
        unavailable["semantic_edges"] = semantic_edges
        unavailable["origin_claims"] = origin_claims
        unavailable["recent_rings"] = recent_rings
        unavailable["source_paths"] = _unique_preserve_order(source_paths)
        unavailable["source_line_range"] = ring_record.get("source_line_range") if isinstance(ring_record, Mapping) else None
        unavailable["node_taxonomy"] = node_taxonomy
        unavailable["continent"] = node_taxonomy["continent"]
        unavailable["node_type"] = node_taxonomy["node_type"]
        unavailable["topography_level"] = node_taxonomy["topography_level"]
        unavailable["community_role"] = node_taxonomy["community_role"]
        return unavailable

    bundle = {
        "schema_version": "ring_support_bundle.v1",
        "bundle_mode": "provenance-ring-mixed",
        "query_text": query_text,
        "topic_key": selected_topic_key,
        "topic_hint": str(paragraph_intent.get("topic_hint") or _yaml_scalar(topic_text, "title") or ""),
        "topic_id": _yaml_scalar(topic_text, "id") or _yaml_scalar(concept_text, "id") or None,
        "ring_ids": ring_ids,
        "ring_id": ring_ids[0] if ring_ids else None,
        "community_id": community_id or None,
        "source_ref": str(ring_record.get("source_ref") or ""),
        "origin_locator": str(ring_record.get("origin_locator") or ""),
        "provider_session_id": str(ring_record.get("provider_session_id") or ""),
        "message_index_range": ring_record.get("message_index_range") or None,
        "source_line_range": ring_record.get("source_line_range") or None,
        "anchor_hash": str(ring_record.get("anchor_hash") or ""),
        "commit_watermark": str(ring_record.get("commit_watermark") or ""),
        "lifecycle_state": lifecycle_state,
        "current_authority": _yaml_scalar(topic_text, "current_authority") or _yaml_scalar(concept_text, "current_authority") or None,
        "node_taxonomy": node_taxonomy,
        "continent": node_taxonomy["continent"],
        "node_type": node_taxonomy["node_type"],
        "topography_level": node_taxonomy["topography_level"],
        "community_role": node_taxonomy["community_role"],
        "paragraph_intent_safety_belt": dict(paragraph_intent),
        "origin_claims": origin_claims,
        "recent_rings": recent_rings,
        "source_paths": _unique_preserve_order(source_paths),
        "support_facts": _unique_preserve_order([str(row.get("support_fact") or "") for row in origin_claims]),
        "community_edges": community_edges,
        "semantic_edges": semantic_edges,
    }
    bundle["recall_digest"] = build_recall_digest_from_support_bundle(query_text=query_text, support_bundle=bundle)
    return bundle
