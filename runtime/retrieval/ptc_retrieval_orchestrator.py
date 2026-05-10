from __future__ import annotations

from runtime.common.exceptions import OPTIONAL_IMPORT_ERRORS, RECOVERABLE_RUNTIME_ERRORS
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_common import DEFAULT_VAULT, utc_now_iso
from ptc.primitives import (
    _boost_by_edges,
    format_consumer_result,
    load_edges,
    load_vault,
    search_vault_bm25,
    search_vault_by_edge,
    search_vault_by_keyword,
)
from retrieval.pathfinder_tools import build_ring_support_bundle

try:
    from runtime.bm25_search import bm25_search as _rank_bm25_search
except OPTIONAL_IMPORT_ERRORS:  # pragma: no cover - import shape differs in direct script runs.
    try:
        from bm25_search import bm25_search as _rank_bm25_search
    except OPTIONAL_IMPORT_ERRORS:  # pragma: no cover
        _rank_bm25_search = None


GENERATOR_ORDER = (
    "bm25",
    "keyword",
    "korean_expansion",
    "edge",
    "community",
    "provenance_ring",
    "recent_episode",
    "source_ref_lookup",
)
STRONG_EVIDENCE = {"source_path", "provenance"}
DOMAIN_ROUTE_FRAGMENTS = {
    "hooks": ("hooks", "event-automation", "lifecycle-event"),
    "skills": ("skills", "reusable-guidance", "skill.md"),
    "subagents": ("subagent", "subagents", "isolated-context", "isolated-worker"),
    "mcp": ("mcp", "external-tool-transport", "external-capability"),
    "context_safe_recall": ("context-window-safe-recall", "safe-recall", "recall"),
}


def _sha_token(*parts: Any, length: int = 24) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _query_terms(query_text: str) -> list[str]:
    terms = [term.lower() for term in re.split(r"\s+", query_text) if term.strip()]
    try:
        from korean_text.query_expansion import query_expansion_tokens

        terms.extend(str(term).lower() for term in query_expansion_tokens(query_text))
    except (ImportError, ValueError):
        pass
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        token = term.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _query_domain_hints(query_text: str) -> set[str]:
    text = query_text.lower()
    hints: set[str] = set()
    if any(marker in text for marker in ("자동", "매번", "이벤트", "event", "lifecycle", "pretooluse", "posttooluse", "도구 호출")):
        hints.add("hooks")
    if any(marker in text for marker in ("반복", "체크리스트", "작업 절차", "재사용", "필요할 때", "skill", "skills", "skill.md", "지침")):
        hints.add("skills")
    if any(marker in text for marker in ("파일을 많이", "조사", "격리", "side work", "subagent", "subagents", "요약만", "메인 context")):
        hints.add("subagents")
    if any(marker in text for marker in ("외부", "데이터베이스", "database", "api", "transport", "mcp", "서비스", "도구 연결")):
        hints.add("mcp")
    if any(marker in text for marker in ("raw", "원문", "복붙", "곱씹", "회상", "digest", "alignment", "정렬")):
        hints.add("context_safe_recall")

    # Negative disambiguation: "not a skill" in an automation question should not
    # pull the route toward the skill node.
    if "skills" in hints and "hooks" in hints and any(marker in text for marker in ("말고", "아니라", "not skill", "not the skill")):
        hints.discard("skills")
    return hints


def _candidate_route_text(candidate: Mapping[str, Any]) -> str:
    values = [
        candidate.get("node_id"),
        candidate.get("source_path"),
        candidate.get("source_ref"),
        candidate.get("origin_locator"),
        candidate.get("community_id"),
        candidate.get("ring_id"),
    ]
    return " ".join(str(value or "").lower() for value in values)


def _domain_matches_route(candidate: Mapping[str, Any], domain: str) -> bool:
    route_text = _candidate_route_text(candidate)
    return any(fragment in route_text for fragment in DOMAIN_ROUTE_FRAGMENTS.get(domain, ()))


def _apply_domain_affinity(candidate: Mapping[str, Any], domains: set[str]) -> dict[str, Any]:
    boosted = dict(candidate)
    if not domains:
        return boosted
    matched = [domain for domain in domains if _domain_matches_route(candidate, domain)]
    conflicting = [
        domain
        for domain in DOMAIN_ROUTE_FRAGMENTS
        if domain not in domains and _domain_matches_route(candidate, domain)
    ]
    score = float(boosted.get("score") or 0.0)
    if matched:
        score += 1.5 * len(matched)
        supporting = set(boosted.get("supporting_generators") or [])
        supporting.add("domain_affinity")
        boosted["supporting_generators"] = sorted(str(item) for item in supporting if item)
        boosted["domain_affinity"] = {"matched": matched, "conflicting": conflicting}
    elif conflicting:
        score *= 0.35
        boosted["domain_affinity"] = {"matched": [], "conflicting": conflicting}
    boosted["score"] = max(0.0, score)
    return boosted


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _candidate_search_text(candidate: Mapping[str, Any]) -> str:
    values = [
        candidate.get("node_id"),
        candidate.get("subject"),
        candidate.get("predicate"),
        candidate.get("object"),
        candidate.get("category"),
        candidate.get("node_text"),
        candidate.get("source_path"),
        candidate.get("source_ref"),
        candidate.get("origin_locator"),
        candidate.get("community_id"),
        candidate.get("ring_id"),
        candidate.get("evidence_class"),
    ]
    values.extend(candidate.get("supporting_generators") or [])
    return " ".join(str(value or "").lower() for value in values)


def _specificity_terms(query_text: str) -> list[str]:
    specific: list[str] = []
    for term in [term.lower().strip(".,;:()[]{}\"'") for term in re.split(r"\s+", query_text) if term.strip()]:
        if len(term) >= 12 or "-" in term or "://" in term or any(char.isdigit() for char in term):
            specific.append(term)
    return specific


def _term_overlap_score(terms: Sequence[str], text: str) -> float:
    normalized = text.lower()
    unique = [term for term in dict.fromkeys(str(term).lower() for term in terms) if term]
    if not unique:
        return 0.0
    hits = sum(1 for term in unique if term in normalized)
    return _clamp01(hits / len(unique))


def _candidate_feature_vector(
    candidate: Mapping[str, Any],
    *,
    query_text: str,
    domains: set[str],
) -> dict[str, Any]:
    text = _candidate_search_text(candidate)
    terms = _query_terms(query_text)
    specific_terms = _specificity_terms(query_text)
    supporting = set(str(item) for item in (candidate.get("supporting_generators") or []) if str(item))
    lifecycle = str(candidate.get("lifecycle_state") or "").upper()
    source_present = bool(candidate.get("source_path") or candidate.get("source_ref"))
    source_path_present = bool(candidate.get("source_path"))
    evidence_class = str(candidate.get("evidence_class") or "")
    matched_domains = list((candidate.get("domain_affinity") or {}).get("matched") or [])
    conflicting_domains = list((candidate.get("domain_affinity") or {}).get("conflicting") or [])
    raw_score_alignment = _clamp01(float(candidate.get("score") or 0.0) / 5.0)
    specificity_overlap = _term_overlap_score(specific_terms, text) if specific_terms else 1.0
    return {
        "schema_version": "candidate_feature_vector.v1",
        "lexical_score": _clamp01(float(candidate.get("score") or 0.0) / 10.0),
        "topology_score": _clamp01(
            (0.35 if candidate.get("community_id") else 0.0)
            + (0.35 if candidate.get("ring_id") else 0.0)
            + (0.30 if "edge" in supporting or "community" in supporting else 0.0)
        ),
        "provenance_score": _clamp01(
            (0.45 if candidate.get("source_ref") else 0.0)
            + (0.35 if source_path_present else 0.0)
            + (0.20 if evidence_class == "provenance" else 0.0)
        ),
        "freshness_score": 1.0 if lifecycle == "ACTIVE" else (0.0 if lifecycle in {"STALE", "SUPERSEDED"} else 0.35),
        "query_alignment_score": max(
            _term_overlap_score(terms, text),
            raw_score_alignment,
            1.0 if domains and matched_domains else 0.0,
        ),
        "source_integrity_score": _clamp01(
            (0.55 if source_present else 0.0)
            + (0.25 if candidate.get("line_range") else 0.0)
            + (0.20 if evidence_class in STRONG_EVIDENCE else 0.0)
        ),
        "consensus_score": _clamp01(len(supporting) / max(len(GENERATOR_ORDER), 1)),
        "specificity_score": specificity_overlap,
        "contamination_penalty": _clamp01(0.35 * len(conflicting_domains)),
        "missing_evidence_penalty": 0.0 if source_present else 1.0,
    }


def _candidate_reranker(candidate: Mapping[str, Any], features: Mapping[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    lifecycle = str(candidate.get("lifecycle_state") or "").upper()
    if not (candidate.get("source_path") or candidate.get("source_ref")):
        reason_codes.append("missing_source_ref_or_source_path")
    if lifecycle in {"STALE", "SUPERSEDED"}:
        reason_codes.append(f"lifecycle_{lifecycle.lower()}")
    if candidate.get("evidence_class") == "typed_unavailable":
        reason_codes.append("typed_unavailable_candidate")
    if float(features.get("specificity_score") or 0.0) <= 0.0:
        reason_codes.append("near_miss_specificity_marker_mismatch")
    if float(features.get("query_alignment_score") or 0.0) <= 0.0:
        reason_codes.append("missing_query_alignment")

    weighted = (
        0.16 * float(features.get("lexical_score") or 0.0)
        + 0.14 * float(features.get("topology_score") or 0.0)
        + 0.20 * float(features.get("provenance_score") or 0.0)
        + 0.10 * float(features.get("freshness_score") or 0.0)
        + 0.18 * float(features.get("query_alignment_score") or 0.0)
        + 0.12 * float(features.get("source_integrity_score") or 0.0)
        + 0.05 * float(features.get("consensus_score") or 0.0)
        + 0.05 * float(features.get("specificity_score") or 0.0)
        - 0.20 * float(features.get("contamination_penalty") or 0.0)
        - 0.25 * float(features.get("missing_evidence_penalty") or 0.0)
    )
    return {
        "schema_version": "candidate_reranker.v1",
        "score_model": "deterministic_feature_weighted_v1",
        "embedding_rerank_status": "optional_not_used",
        "final_score": _clamp01(weighted),
        "hard_gate_results": {
            "answer_support_allowed": not reason_codes,
            "reason_codes": reason_codes,
            "hard_gate_precedes_score": True,
        },
        "selected_or_rejected": "pending",
        "rejection_reason": None,
    }


def _rerank_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    query_text: str,
    domains: set[str],
) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        features = _candidate_feature_vector(candidate, query_text=query_text, domains=domains)
        reranker = _candidate_reranker(candidate, features)
        candidate["candidate_feature_vector"] = features
        candidate["candidate_reranker"] = reranker
        candidate["score"] = reranker["final_score"]
        reranked.append(candidate)
    return sorted(reranked, key=lambda item: float(item.get("score") or 0.0), reverse=True)


def _source_path_for_node(node: Mapping[str, Any]) -> str | None:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
    for raw in (
        node.get("_source_path"),
        node.get("source_path"),
        metadata.get("_source_path") if isinstance(metadata, Mapping) else None,
        metadata.get("source_path") if isinstance(metadata, Mapping) else None,
    ):
        if raw:
            value = str(raw).strip().replace("\\", "/")
            if value:
                return value if value.startswith("vault/") else f"vault/{value}"
    content_hash = str(node.get("content_hash") or "").strip()
    if content_hash:
        return f"vault/N-{content_hash}.md"
    node_id = str(node.get("node_id") or "").strip()
    return f"vault/{node_id}.md" if node_id else None


def _safe_ref_from_source_path(source_path: str | None) -> str | None:
    if not source_path:
        return None
    clean = source_path.removeprefix("vault/").strip("/")
    if not clean:
        return None
    return f"oy-vault://{clean}"


def _lifecycle_state(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"ACTIVE", "SUPERSEDED", "STALE"}:
        return raw
    return "UNKNOWN"


def _freshness_for_lifecycle(lifecycle_state: str) -> str:
    if lifecycle_state == "ACTIVE":
        return "current"
    if lifecycle_state == "STALE":
        return "stale"
    return "unknown"


def _candidate(
    *,
    query_text: str,
    generator: str,
    score: float,
    node_id: str | None = None,
    source_path: str | None = None,
    source_ref: str | None = None,
    origin_locator: str | None = None,
    line_range: Mapping[str, Any] | None = None,
    community_id: str | None = None,
    ring_id: str | None = None,
    lifecycle_state: str = "UNKNOWN",
    freshness: str | None = None,
    evidence_class: str = "lexical_match",
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    normalized_lifecycle = _lifecycle_state(lifecycle_state)
    normalized_source_ref = source_ref or _safe_ref_from_source_path(source_path)
    candidate = {
        "schema_version": "retrieval_candidate.v1",
        "candidate_id": "",
        "generator": generator,
        "node_id": node_id,
        "source_path": source_path,
        "source_ref": normalized_source_ref,
        "origin_locator": origin_locator,
        "line_range": dict(line_range) if isinstance(line_range, Mapping) else None,
        "community_id": community_id,
        "ring_id": ring_id,
        "lifecycle_state": normalized_lifecycle,
        "score": max(0.0, float(score)),
        "freshness": freshness or _freshness_for_lifecycle(normalized_lifecycle),
        "evidence_class": evidence_class,
        "supporting_generators": [generator],
        "rejection_reason": rejection_reason,
    }
    candidate["candidate_id"] = f"cand:{_sha_token(query_text, candidate, length=20)}"
    return candidate


def _candidate_from_node(
    *,
    query_text: str,
    generator: str,
    node: Mapping[str, Any],
    score: float,
    evidence_class: str = "lexical_match",
) -> dict[str, Any]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
    spo = node.get("spo") if isinstance(node.get("spo"), Mapping) else {}
    source_path = _source_path_for_node(node)
    community_id = (
        node.get("community_id")
        or metadata.get("community_id")
        or node.get("community")
        or metadata.get("community")
        or ""
    )
    candidate = _candidate(
        query_text=query_text,
        generator=generator,
        score=score,
        node_id=str(node.get("node_id") or metadata.get("node_id") or "") or None,
        source_path=source_path,
        source_ref=str(node.get("source_ref") or metadata.get("source_ref") or "") or None,
        origin_locator=str(node.get("origin_locator") or metadata.get("origin_locator") or "") or None,
        community_id=str(community_id).strip() or None,
        ring_id=str(node.get("ring_id") or metadata.get("ring_id") or "") or None,
        lifecycle_state=str(metadata.get("status") or metadata.get("lifecycle_state") or "UNKNOWN"),
        evidence_class=evidence_class,
    )
    candidate["subject"] = str(spo.get("subject") or metadata.get("title") or node.get("title") or "").strip()
    candidate["predicate"] = str(spo.get("predicate") or "").strip()
    candidate["object"] = str(spo.get("object") or "").strip()
    candidate["category"] = str(spo.get("category") or metadata.get("type") or "").strip()
    candidate["node_text"] = " ".join(
        part
        for part in (
            candidate["subject"],
            candidate["predicate"],
            candidate["object"],
            candidate["category"],
        )
        if part
    )
    return candidate


def _node_index(vault_nodes: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for node in vault_nodes:
        node_id = str(node.get("node_id") or "").strip()
        if node_id:
            indexed[node_id] = node
        source_path = _source_path_for_node(node)
        if source_path:
            indexed[Path(source_path).stem] = node
    return indexed


def _rank_bm25_candidates(
    *,
    query_text: str,
    vault_root: Path,
    vault_nodes: Sequence[Mapping[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    indexed = _node_index(vault_nodes)
    if _rank_bm25_search is not None:
        try:
            rows = _rank_bm25_search(vault_root, query_text, top_k=top_k)
            candidates = []
            for row in rows:
                node_id = str(row.get("node_id") or row.get("metadata", {}).get("node_id") or "")
                node = indexed.get(node_id) or indexed.get(Path(node_id).stem)
                if node is None:
                    continue
                candidates.append(
                    _candidate_from_node(
                        query_text=query_text,
                        generator="bm25",
                        node=node,
                        score=float(row.get("score") or row.get("bm25_score") or 0.0),
                    )
                )
            if candidates:
                return candidates
        except RECOVERABLE_RUNTIME_ERRORS:
            pass

    return [
        _candidate_from_node(
            query_text=query_text,
            generator="bm25",
            node=node,
            score=float(node.get("_match_score") or 0.0),
        )
        for node in search_vault_bm25(list(vault_nodes), query_text, top_k=top_k)
    ]


def _keyword_candidates(
    *,
    query_text: str,
    vault_nodes: Sequence[Mapping[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    return [
        _candidate_from_node(
            query_text=query_text,
            generator="keyword",
            node=node,
            score=float(node.get("_match_score") or 0.0),
        )
        for node in search_vault_by_keyword(list(vault_nodes), query_text)[:top_k]
    ]


def _korean_expansion_candidates(
    *,
    query_text: str,
    vault_nodes: Sequence[Mapping[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    try:
        from korean_text.query_expansion import query_expansion_tokens

        tokens = [str(token) for token in query_expansion_tokens(query_text) if str(token).strip()]
    except RECOVERABLE_RUNTIME_ERRORS:
        tokens = []
    if not tokens:
        return []
    expanded_query = " ".join([query_text, *tokens])
    return [
        _candidate_from_node(
            query_text=query_text,
            generator="korean_expansion",
            node=node,
            score=float(node.get("_match_score") or 0.0),
        )
        for node in search_vault_by_keyword(list(vault_nodes), expanded_query)[:top_k]
    ]


def _edge_candidates(
    *,
    query_text: str,
    vault_root: Path,
    vault_nodes: Sequence[Mapping[str, Any]],
    seed_candidates: Sequence[Mapping[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    edges = load_edges(vault_root)
    if not edges:
        return []
    node_by_id = _node_index(vault_nodes)
    out: list[dict[str, Any]] = []
    for seed in seed_candidates[:top_k]:
        node_id = str(seed.get("node_id") or "").strip()
        if not node_id:
            continue
        for node in search_vault_by_edge(list(vault_nodes), edges, node_id)[:top_k]:
            boosted = dict(node)
            boosted["_match_score"] = max(float(seed.get("score") or 0.0) * 0.8, 0.1)
            resolved = node_by_id.get(str(boosted.get("node_id") or "")) or boosted
            out.append(
                _candidate_from_node(
                    query_text=query_text,
                    generator="edge",
                    node=resolved,
                    score=float(boosted.get("_match_score") or 0.0),
                    evidence_class="source_path",
                )
            )
    return out


def _community_candidates(
    *,
    query_text: str,
    vault_root: Path,
    top_k: int,
) -> list[dict[str, Any]]:
    terms = _query_terms(query_text)
    if not terms:
        return []
    out: list[dict[str, Any]] = []
    for path in sorted((vault_root / "communities").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        hay = text.lower()
        score = sum(1 for term in terms if term in hay)
        if score <= 0:
            continue
        community_id = f"community:{path.stem}"
        out.append(
            _candidate(
                query_text=query_text,
                generator="community",
                score=float(score) / max(len(terms), 1),
                source_path=f"vault/communities/{path.name}",
                community_id=community_id,
                lifecycle_state="ACTIVE",
                evidence_class="community_hint",
            )
        )
    return sorted(out, key=lambda item: item["score"], reverse=True)[:top_k]


def _ring_candidates(
    *,
    query_text: str,
    vault_root: Path,
    matched_nodes: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        ring_bundle = build_ring_support_bundle(
            query_text=query_text,
            vault_root=vault_root,
            matched_nodes=list(matched_nodes),
        )
    except RECOVERABLE_RUNTIME_ERRORS:
        return [], None

    if ring_bundle.get("typed_unavailable"):
        return [
            _candidate(
                query_text=query_text,
                generator="provenance_ring",
                score=0.0,
                lifecycle_state="UNKNOWN",
                evidence_class="typed_unavailable",
                rejection_reason="typed_unavailable",
            )
        ], ring_bundle

    source_paths = list(ring_bundle.get("source_paths") or [])
    primary_source = str(source_paths[0]) if source_paths else None
    line_range = ring_bundle.get("source_line_range") if isinstance(ring_bundle.get("source_line_range"), Mapping) else None
    primary = _candidate(
        query_text=query_text,
        generator="provenance_ring",
        score=1.0 + min(len(source_paths), 4) * 0.05,
        node_id=str(ring_bundle.get("topic_id") or ring_bundle.get("topic_key") or "") or None,
        source_path=primary_source,
        source_ref=str(ring_bundle.get("source_ref") or "") or None,
        origin_locator=str(ring_bundle.get("origin_locator") or "") or None,
        line_range=line_range,
        community_id=str(ring_bundle.get("community_id") or "") or None,
        ring_id=str(ring_bundle.get("ring_id") or "") or None,
        lifecycle_state=str(ring_bundle.get("lifecycle_state") or "UNKNOWN"),
        evidence_class="provenance",
    )
    return [primary], ring_bundle


def _recent_candidates(
    *,
    query_text: str,
    ring_bundle: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(ring_bundle, Mapping) or ring_bundle.get("typed_unavailable"):
        return []
    out: list[dict[str, Any]] = []
    source_paths = list(ring_bundle.get("source_paths") or [])
    primary_source = str(source_paths[0]) if source_paths else None
    for row in list(ring_bundle.get("recent_rings") or [])[:5]:
        if not isinstance(row, Mapping):
            continue
        out.append(
            _candidate(
                query_text=query_text,
                generator="recent_episode",
                score=0.85,
                node_id=str(ring_bundle.get("topic_id") or ring_bundle.get("topic_key") or "") or None,
                source_path=primary_source,
                source_ref=str(row.get("source_ref") or ring_bundle.get("source_ref") or "") or None,
                origin_locator=str(row.get("origin_locator") or ring_bundle.get("origin_locator") or "") or None,
                line_range=row.get("source_line_range") if isinstance(row.get("source_line_range"), Mapping) else None,
                community_id=str(ring_bundle.get("community_id") or "") or None,
                ring_id=str(row.get("ring_id") or ring_bundle.get("ring_id") or "") or None,
                lifecycle_state=str(ring_bundle.get("lifecycle_state") or "UNKNOWN"),
                evidence_class="provenance",
                freshness="recent",
            )
        )
    return out


def _source_ref_lookup_candidates(
    *,
    query_text: str,
    vault_root: Path,
    top_k: int,
) -> list[dict[str, Any]]:
    refs = re.findall(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s)]+", query_text)
    terms = refs or [term for term in _query_terms(query_text) if "://" in term]
    if not terms:
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(vault_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not any(term in text for term in terms):
            continue
        rel = path.resolve().relative_to(vault_root.resolve()).as_posix()
        out.append(
            _candidate(
                query_text=query_text,
                generator="source_ref_lookup",
                score=1.0,
                source_path=f"vault/{rel}",
                source_ref=_safe_ref_from_source_path(f"vault/{rel}"),
                lifecycle_state="ACTIVE",
                evidence_class="source_path",
            )
        )
        if len(out) >= top_k:
            break
    return out


def _merge_key(candidate: Mapping[str, Any]) -> str:
    for key in ("ring_id", "node_id", "source_path", "source_ref"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return str(candidate["candidate_id"])


def _merge_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in candidates:
        candidate = dict(raw)
        key = _merge_key(candidate)
        current = merged.get(key)
        if current is None or float(candidate.get("score") or 0.0) > float(current.get("score") or 0.0):
            supporting = set(current.get("supporting_generators") or []) if current else set()
            supporting.update(candidate.get("supporting_generators") or [candidate.get("generator")])
            candidate["supporting_generators"] = sorted(str(item) for item in supporting if item)
            merged[key] = candidate
            continue
        supporting = set(current.get("supporting_generators") or [])
        supporting.update(candidate.get("supporting_generators") or [candidate.get("generator")])
        current["supporting_generators"] = sorted(str(item) for item in supporting if item)
    return sorted(merged.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)


def _evaluate_candidates(candidates: Sequence[Mapping[str, Any]], *, max_selected: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    selected_route_keys: set[str] = set()
    for raw in candidates:
        candidate = dict(raw)
        reason = None
        reranker = candidate.get("candidate_reranker") if isinstance(candidate.get("candidate_reranker"), Mapping) else {}
        hard_gate = reranker.get("hard_gate_results") if isinstance(reranker.get("hard_gate_results"), Mapping) else {}
        hard_gate_reasons = list(hard_gate.get("reason_codes") or [])
        strong_route_already = any(item.get("evidence_class") in STRONG_EVIDENCE for item in selected)
        if hard_gate.get("answer_support_allowed") is False:
            reason = str(hard_gate_reasons[0] if hard_gate_reasons else "hard_gate_rejected")
        elif candidate.get("evidence_class") == "typed_unavailable":
            reason = "typed_unavailable"
        elif candidate.get("lifecycle_state") in {"SUPERSEDED", "STALE"}:
            reason = f"lifecycle_{str(candidate.get('lifecycle_state')).lower()}"
        elif strong_route_already and candidate.get("evidence_class") not in STRONG_EVIDENCE:
            reason = "weaker_candidate_after_source_backed_route"
        elif len(selected) >= max_selected:
            reason = "lower_rank_after_bounded_selection"
        route_key = str(candidate.get("community_id") or candidate.get("ring_id") or candidate.get("node_id") or "")
        if reason is None and route_key and route_key in selected_route_keys:
            reason = "duplicate_route_after_merge"

        if reason is None:
            candidate["rejection_reason"] = None
            if isinstance(candidate.get("candidate_reranker"), Mapping):
                candidate["candidate_reranker"] = dict(candidate["candidate_reranker"])
                candidate["candidate_reranker"]["selected_or_rejected"] = "selected"
                candidate["candidate_reranker"]["rejection_reason"] = None
            selected.append(candidate)
            if route_key:
                selected_route_keys.add(route_key)
        else:
            candidate["rejection_reason"] = reason
            if isinstance(candidate.get("candidate_reranker"), Mapping):
                candidate["candidate_reranker"] = dict(candidate["candidate_reranker"])
                candidate["candidate_reranker"]["selected_or_rejected"] = "rejected"
                candidate["candidate_reranker"]["rejection_reason"] = reason
            rejected.append(candidate)
    return selected, rejected


def _coverage_state(selected: Sequence[Mapping[str, Any]], rejected: Sequence[Mapping[str, Any]]) -> str:
    if any(candidate.get("evidence_class") in STRONG_EVIDENCE and candidate.get("source_path") for candidate in selected):
        return "present"
    if any(candidate.get("source_path") and candidate.get("lifecycle_state") == "ACTIVE" for candidate in selected):
        return "present"
    if selected or rejected:
        return "weak"
    return "absent"


def _typed_unavailable(query_text: str, *, reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": "typed_unavailable.v1",
        "unavailable_ref": f"oy-vault://ptc-retrieval/{_sha_token(query_text, reason_code, length=32)}",
        "created_at": utc_now_iso(),
        "reason_code": "unresolved_evidence_ref",
        "blocked_stage": "recall_support_bundle",
        "missing_or_rejected_refs": [
            {
                "ref": f"oy-vault://ptc-retrieval/{reason_code}",
                "reason_code": reason_code,
                "rejection_kind": "unresolved",
            }
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
    }


def _matched_nodes_from_candidates(
    *,
    selected: Sequence[Mapping[str, Any]],
    vault_nodes: Sequence[Mapping[str, Any]],
    vault_root: Path,
) -> list[dict[str, Any]]:
    indexed = _node_index(vault_nodes)
    out: list[dict[str, Any]] = []
    for candidate in selected:
        node_id = str(candidate.get("node_id") or "").strip()
        if not node_id:
            continue
        node = indexed.get(node_id) or indexed.get(Path(node_id).stem)
        if node is None:
            continue
        copied = dict(node)
        copied["_match_score"] = float(candidate.get("score") or 0.0)
        out.append(copied)
    boosted = _boost_by_edges(out, load_edges(vault_root)) if out else out
    return boosted


def build_structured_recall_answer_frame(result: Mapping[str, Any]) -> dict[str, Any]:
    query_text = str(result.get("query_text") or "")
    candidate_set = result.get("candidate_set") if isinstance(result.get("candidate_set"), Mapping) else {}
    consumer_bundle = result.get("consumer_bundle") if isinstance(result.get("consumer_bundle"), Mapping) else {}
    ring_bundle = consumer_bundle.get("support_bundle") if isinstance(consumer_bundle.get("support_bundle"), Mapping) else {}
    support_facts = list(ring_bundle.get("support_facts") or consumer_bundle.get("support_facts") or [])
    selected = [
        candidate
        for candidate in candidate_set.get("candidates", [])
        if candidate.get("candidate_id") in set(candidate_set.get("selected_candidate_ids") or [])
    ]
    rejected = [
        candidate
        for candidate in candidate_set.get("candidates", [])
        if candidate.get("candidate_id") in set(candidate_set.get("rejected_candidate_ids") or [])
    ]
    return {
        "schema_version": "structured_recall_answer_frame.v1",
        "original_prompt": query_text,
        "task_understanding": "answer_from_recalled_wiki_memory_when_evidence_is_present",
        "coverage_state": str(candidate_set.get("coverage_state") or "absent"),
        "recalled_topic_key": ring_bundle.get("topic_key"),
        "recalled_community_id": ring_bundle.get("community_id"),
        "source_line_range": ring_bundle.get("source_line_range"),
        "source_paths": list(ring_bundle.get("source_paths") or consumer_bundle.get("source_paths") or []),
        "recalled_memory": support_facts[:5],
        "selected_routes": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "generator": candidate.get("generator"),
                "community_id": candidate.get("community_id"),
                "ring_id": candidate.get("ring_id"),
                "evidence_class": candidate.get("evidence_class"),
            }
            for candidate in selected[:5]
        ],
        "rejected_routes": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "generator": candidate.get("generator"),
                "community_id": candidate.get("community_id"),
                "ring_id": candidate.get("ring_id"),
                "reason": candidate.get("rejection_reason"),
            }
            for candidate in rejected[:8]
        ],
        "answer_resolution": (
            support_facts[0]
            if support_facts
            else "typed_unavailable: no source-backed recall candidate was selected"
        ),
        "hard_nonclaims": [
            "not_hidden_chain_of_thought",
            "not_raw_transcript_replay",
            "not_automatic_web_scraping",
            "not_full_ux_pass",
        ],
    }


def build_ptc_retrieval_orchestrator_result(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    top_k: int = 20,
    max_attempts: int = 5,
) -> dict[str, Any]:
    if not query_text.strip():
        raise ValueError("query_text is required")

    vault_nodes = load_vault(vault_root)
    domain_hints = _query_domain_hints(query_text)
    generator_reports: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []

    def collect(generator: str, fn) -> list[dict[str, Any]]:
        try:
            candidates = fn()
            generator_reports.append(
                {
                    "generator": generator,
                    "status": "completed" if candidates else "typed_unavailable",
                    "candidate_count": len(candidates),
                    "reason": None if candidates else "no_candidates",
                }
            )
            return candidates
        except RECOVERABLE_RUNTIME_ERRORS as exc:
            generator_reports.append(
                {
                    "generator": generator,
                    "status": "error",
                    "candidate_count": 0,
                    "reason": type(exc).__name__,
                }
            )
            return []

    bm25 = collect(
        "bm25",
        lambda: _rank_bm25_candidates(
            query_text=query_text,
            vault_root=vault_root,
            vault_nodes=vault_nodes,
            top_k=top_k,
        ),
    )
    keyword = collect(
        "keyword",
        lambda: _keyword_candidates(query_text=query_text, vault_nodes=vault_nodes, top_k=top_k),
    )
    korean = collect(
        "korean_expansion",
        lambda: _korean_expansion_candidates(query_text=query_text, vault_nodes=vault_nodes, top_k=top_k),
    )
    all_candidates.extend(bm25)
    all_candidates.extend(keyword)
    all_candidates.extend(korean)
    all_candidates.extend(
        collect(
            "edge",
            lambda: _edge_candidates(
                query_text=query_text,
                vault_root=vault_root,
                vault_nodes=vault_nodes,
                seed_candidates=[*bm25, *keyword, *korean],
                top_k=top_k,
            ),
        )
    )
    all_candidates.extend(
        collect(
            "community",
            lambda: _community_candidates(query_text=query_text, vault_root=vault_root, top_k=top_k),
        )
    )
    ring_candidates, ring_bundle = _ring_candidates(
        query_text=query_text,
        vault_root=vault_root,
        matched_nodes=vault_nodes,
    )
    generator_reports.append(
        {
            "generator": "provenance_ring",
            "status": "completed" if ring_candidates and not ring_candidates[0].get("rejection_reason") else "typed_unavailable",
            "candidate_count": len(ring_candidates),
            "reason": ring_candidates[0].get("rejection_reason") if ring_candidates else "no_candidates",
        }
    )
    all_candidates.extend(ring_candidates)
    all_candidates.extend(
        collect(
            "recent_episode",
            lambda: _recent_candidates(query_text=query_text, ring_bundle=ring_bundle),
        )
    )
    all_candidates.extend(
        collect(
            "source_ref_lookup",
            lambda: _source_ref_lookup_candidates(query_text=query_text, vault_root=vault_root, top_k=top_k),
        )
    )

    all_candidates = [_apply_domain_affinity(candidate, domain_hints) for candidate in all_candidates]
    merged = _merge_candidates(all_candidates)
    reranked = _rerank_candidates(merged, query_text=query_text, domains=domain_hints)
    selected, rejected = _evaluate_candidates(reranked)
    coverage_state = _coverage_state(selected, rejected)
    selected_ids = [str(candidate["candidate_id"]) for candidate in selected]
    rejected_ids = [str(candidate["candidate_id"]) for candidate in rejected]
    retry_decision = {
        "status": "not_required" if coverage_state == "present" else "retry_recommended",
        "attempts_used": 1,
        "max_attempts": max(1, int(max_attempts)),
        "reason": (
            "source_backed_candidate_selected"
            if coverage_state == "present"
            else "source_backed_candidate_missing_or_weak"
        ),
    }
    candidate_set = {
        "schema_version": "retrieval_candidate_set.v1",
        "query_text": query_text,
        "domain_hints": sorted(domain_hints),
        "generated_at": utc_now_iso(),
        "generators_attempted": list(GENERATOR_ORDER),
        "generator_reports": generator_reports,
        "merge_strategy": "dedupe_by_ring_node_source_then_feature_rerank",
        "reranker_policy": {
            "schema_version": "candidate_reranker_policy.v1",
            "candidate_feature_vector_schema": "candidate_feature_vector.v1",
            "candidate_reranker_schema": "candidate_reranker.v1",
            "score_components": [
                "lexical_score",
                "topology_score",
                "provenance_score",
                "freshness_score",
                "query_alignment_score",
                "source_integrity_score",
                "consensus_score",
                "specificity_score",
                "contamination_penalty",
                "missing_evidence_penalty",
            ],
            "hard_gate_precedes_score": True,
            "embedding_reranking": "optional_future_feature_cannot_override_provenance_gate",
        },
        "candidates": selected + rejected,
        "selected_candidate_ids": selected_ids,
        "rejected_candidate_ids": rejected_ids,
        "coverage_state": coverage_state,
        "retry_decision": retry_decision,
    }
    matched_nodes = _matched_nodes_from_candidates(
        selected=selected,
        vault_nodes=vault_nodes,
        vault_root=vault_root,
    )
    consumer_bundle = format_consumer_result(query_text, matched_nodes)
    final_ring_bundle = ring_bundle
    if matched_nodes:
        try:
            final_ring_bundle = build_ring_support_bundle(
                query_text=query_text,
                vault_root=vault_root,
                matched_nodes=matched_nodes,
            )
        except RECOVERABLE_RUNTIME_ERRORS:
            final_ring_bundle = ring_bundle
    if isinstance(final_ring_bundle, Mapping):
        consumer_bundle["support_bundle"] = dict(final_ring_bundle)
    if coverage_state == "absent" and "support_bundle" not in consumer_bundle:
        consumer_bundle["typed_unavailable"] = _typed_unavailable(
            query_text,
            reason_code="no_retrieval_candidates",
        )
    consumer_bundle["ptc_retrieval_orchestrator"] = {
        "schema_version": "ptc_retrieval_orchestrator.v1",
        "coverage_state": coverage_state,
        "generators_attempted": list(GENERATOR_ORDER),
        "selected_candidate_ids": selected_ids,
        "rejected_candidate_ids": rejected_ids,
        "retry_decision": retry_decision,
    }
    result = {
        "schema_version": "ptc_retrieval_orchestrator_result.v1",
        "query_text": query_text,
        "candidate_set": candidate_set,
        "consumer_bundle": consumer_bundle,
        "claim_scope": "deterministic_read_only_retrieval_orchestrator_not_full_ux",
        "hard_nonclaims": [
            "not_dynamic_worker_authored_ptc_code",
            "not_automatic_web_scraping",
            "not_full_ux_pass",
            "not_production_ready",
        ],
    }
    result["structured_recall_answer_frame"] = build_structured_recall_answer_frame(result)
    return result


__all__ = [
    "build_ptc_retrieval_orchestrator_result",
    "build_structured_recall_answer_frame",
]
