from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "domain_evidence_enrichment.v1"
REQUEST_SCHEMA_VERSION = "domain_evidence_request.v1"
ROOTS_JSON_ENV = "OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON"
ROOTS_ENV = "OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS"
ROOTS_FILE_ENV = "OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_FILE"
WORKSPACE_ROOT_ENV = "OPENYGGDRASIL_WORKSPACE_ROOT"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[가-힣]{2,}")
MAX_FILES_PER_ROOT = 160
MAX_FILE_BYTES = 650_000

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "into",
    "from",
    "what",
    "where",
    "when",
    "어떻게",
    "그러면",
    "그리고",
    "기준",
    "문서",
    "정리",
    "나중",
}


def build_domain_evidence_request(
    *,
    query_text: str,
    signal_buckets: list[str],
    minimum_external_sources: int = 2,
    minimum_related_pages: int = 1,
) -> dict[str, Any]:
    query = " ".join(str(query_text or "").split())
    buckets = [str(item) for item in signal_buckets if str(item)]
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "request_kind": "domain_evidence_lookup",
        "query_text": query[:1200],
        "signal_buckets": buckets,
        "minimum_external_sources": int(minimum_external_sources),
        "minimum_related_pages": int(minimum_related_pages),
        "source_root_policy": {
            "configured_roots_only": True,
            "env_json": ROOTS_JSON_ENV,
            "env_pairs": ROOTS_ENV,
            "env_file": ROOTS_FILE_ENV,
            "workspace_config": "config/domain_source_roots.json",
        },
        "hard_nonclaims": [
            "provider_does_not_choose_source_files",
            "postman_does_not_add_evidence",
            "domain_evidence_request_is_not_storage_success",
        ],
    }


def enrich_memory_ticket_payload(
    payload: Mapping[str, Any],
    *,
    vault: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Attach bounded domain evidence selected by MS-side runtime configuration.

    The Provider may request evidence lookup, but it does not pass local paths,
    source snippets, proof language, or a preferred conclusion. Source roots must
    come from runtime configuration or an explicit test payload.
    """

    enriched = dict(payload)
    request = enriched.get("domain_evidence_request")
    if not isinstance(request, Mapping):
        return enriched

    evidence = _collect_domain_evidence(request=request, payload=enriched, env=env)
    enriched["domain_evidence_enrichment"] = evidence
    if evidence.get("status") != "resolved":
        return enriched

    accepted = [
        item for item in evidence.get("accepted_evidence", [])
        if isinstance(item, Mapping) and item.get("evidence_ref")
    ]
    evidence_refs = [str(item["evidence_ref"]) for item in accepted]
    related_pages = [
        str(item)
        for item in evidence.get("related_pages", [])
        if str(item).strip()
    ]

    capsule = dict(enriched.get("decision_capsule") or {})
    existing_refs = _as_list(capsule.get("evidence") or enriched.get("evidence"))
    capsule["evidence"] = _merge_unique([*existing_refs, *evidence_refs])
    enriched["decision_capsule"] = capsule
    enriched["evidence"] = capsule["evidence"]
    enriched["related_pages"] = _merge_unique([*_as_list(enriched.get("related_pages")), *related_pages])
    enriched["automated_quality_review_status"] = "executed"
    enriched["quality_review_status"] = "executed"
    enriched["quality_review_basis"] = {
        "schema_version": "memory_ticket_quality_review_basis.v1",
        "reviewer": "ms_domain_evidence_enrichment",
        "accepted_evidence_count": len(accepted),
        "related_page_count": len(related_pages),
    }
    dedupe = _run_graph_dedupe(vault=vault, payload=enriched)
    enriched["graph_dedupe_status"] = "executed"
    enriched["graph_dedupe_review"] = dedupe
    return enriched


def _collect_domain_evidence(
    *,
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    roots = _configured_roots(payload=payload, env=env or os.environ)
    if not roots:
        return _typed_unavailable("source_roots_not_configured")

    query_text = " ".join(
        str(value or "")
        for value in (
            request.get("query_text"),
            payload.get("topic_hint"),
            payload.get("category_community_hint"),
            payload.get("decision"),
            payload.get("context"),
            payload.get("reuse_condition"),
        )
    )
    query_terms = _query_terms(query_text)
    if not query_terms:
        return _typed_unavailable("query_terms_empty")

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_key, root in roots.items():
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            rejected.append({"source_key": source_key, "reason": "root_not_found"})
            continue
        selected.extend(_rank_markdown_segments(source_key=source_key, root=root_path, query_terms=query_terms))

    selected = sorted(selected, key=lambda row: (-float(row["score"]), str(row["relative_path"])))[:6]
    minimum_sources = int(request.get("minimum_external_sources") or 2)
    if len(selected) < minimum_sources:
        return {
            **_typed_unavailable("insufficient_domain_evidence"),
            "query_terms": query_terms,
            "accepted_evidence": selected,
            "rejected_evidence": rejected,
            "minimum_external_sources": minimum_sources,
        }

    accepted = [
        {
            "source_key": row["source_key"],
            "relative_path": row["relative_path"],
            "line_range": {"start": row["start"], "end": row["end"]},
            "evidence_ref": f"local-docs://{row['source_key']}/{row['relative_path']}:{row['start']}-{row['end']}",
            "role": row["role"],
            "matched_terms": row["matched_terms"],
            "score": row["score"],
            "segment_hash": row["segment_hash"],
        }
        for row in selected
    ]
    related_pages = _merge_unique(
        f"local-docs://{row['source_key']}/{row['relative_path']}"
        for row in selected
    )
    program = _worker_program_record(query_terms=query_terms, source_keys=list(roots))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "resolved",
        "selected_capability_class": "domain_source_lookup",
        "bounded_program_intent": "find bounded source segments that can qualify a Provider memory candidate before wiki promotion",
        "worker_authored_ptc_program_ref": program["worker_authored_ptc_program_ref"],
        "code_hash": program["code_hash"],
        "capability_allowlist": [
            "read_configured_markdown_sources",
            "rank_source_segments",
            "attach_evidence_pointers",
            "run_graph_dedupe_review",
        ],
        "allowed_source_surfaces": [
            {"source_key": key, "root_policy": "configured_runtime_root"}
            for key in roots
        ],
        "allowed_write_surfaces": ["memory_ticket_payload_enrichment_only"],
        "query_terms": query_terms,
        "accepted_evidence": accepted,
        "rejected_evidence": rejected,
        "related_pages": related_pages,
        "hard_nonclaims": [
            "domain_evidence_lookup_is_not_provider_answer",
            "domain_evidence_lookup_is_not_production_ready_by_itself",
            "source_roots_are_runtime_configuration_not_provider_mail",
        ],
    }


def _typed_unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "typed_unavailable",
        "reason_code": reason_code,
        "accepted_evidence": [],
        "related_pages": [],
        "hard_nonclaims": [
            "no_domain_evidence_was_fabricated",
            "memory_ticket_must_remain_candidate_or_typed_unavailable",
        ],
    }


def _configured_roots(*, payload: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    request = payload.get("domain_evidence_request")
    if isinstance(request, Mapping) and isinstance(request.get("docs_roots"), Mapping):
        roots.update(_clean_roots(request["docs_roots"]))
    resolver_options = payload.get("resolver_options")
    if isinstance(resolver_options, Mapping) and isinstance(resolver_options.get("docs_roots"), Mapping):
        roots.update(_clean_roots(resolver_options["docs_roots"]))
    raw_json = str(env.get(ROOTS_JSON_ENV) or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, Mapping):
            roots.update(_clean_roots(parsed))
    raw_pairs = str(env.get(ROOTS_ENV) or "").strip()
    for part in raw_pairs.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = _source_key(key)
        if key and value.strip():
            roots[key] = value.strip()
    roots.update(_roots_from_config_file(env))
    return roots


def _roots_from_config_file(env: Mapping[str, str]) -> dict[str, str]:
    candidates: list[Path] = [Path.home() / ".yggdrasil" / "config" / "domain_source_roots.json"]
    explicit = str(env.get(ROOTS_FILE_ENV) or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    workspace_root = str(env.get(WORKSPACE_ROOT_ENV) or "").strip()
    if workspace_root:
        candidates.append(Path(workspace_root).expanduser() / "config" / "domain_source_roots.json")
    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(parsed, Mapping):
            if isinstance(parsed.get("docs_roots"), Mapping):
                return _clean_roots(parsed["docs_roots"])
            return _clean_roots(parsed)
    return {}


def _clean_roots(values: Mapping[str, Any]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for key, value in values.items():
        clean_key = _source_key(str(key))
        clean_value = str(value or "").strip()
        if clean_key and clean_value:
            roots[clean_key] = clean_value
    return roots


def _source_key(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    return clean[:80]


def _query_terms(text: str) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, match in enumerate(TOKEN_RE.finditer(str(text or ""))):
        raw = match.group(0)
        token = raw.lower()
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        has_ascii = bool(re.search(r"[a-z]", token))
        identifier_like = has_ascii and (
            raw[:1].isupper()
            or raw.isupper()
            or any(char in raw for char in "._/-")
            or len(token) >= 5
        )
        priority = 0 if identifier_like else 1 if has_ascii else 2
        candidates.append((priority, index, token))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return [token for _, _, token in candidates[:28]]


def _rank_markdown_segments(*, source_key: str, root: Path, query_terms: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    files = sorted(root.rglob("*.md"))[:MAX_FILES_PER_ROOT]
    for path in files:
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        lines = text.splitlines()
        hay_path = relative.lower().replace("/", " ")
        for index, line in enumerate(lines, start=1):
            hay = f"{hay_path} {line.lower()}"
            matched = [term for term in query_terms if term in hay]
            if not matched:
                continue
            heading_bonus = 1.4 if line.lstrip().startswith("#") else 0.0
            score = len(set(matched)) + heading_bonus + min(len(line), 240) / 1000
            start = max(1, index - 2)
            end = min(len(lines), index + 3)
            segment_text = "\n".join(lines[start - 1 : end])
            rows.append(
                {
                    "source_key": source_key,
                    "relative_path": relative,
                    "start": start,
                    "end": end,
                    "role": "support",
                    "matched_terms": sorted(set(matched)),
                    "score": round(score, 4),
                    "segment_hash": hashlib.sha256(segment_text.encode("utf-8")).hexdigest()[:16],
                }
            )
    return rows


def _run_graph_dedupe(*, vault: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    terms = set(_query_terms(" ".join(str(payload.get(key) or "") for key in ("decision", "topic_hint", "canonical_topic_title"))))
    nearest: list[dict[str, Any]] = []
    concepts = vault / "concepts"
    if concepts.exists():
        for path in sorted(concepts.glob("N-*.md"))[:200]:
            try:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            overlap = sorted(term for term in terms if term and term in text)
            if overlap:
                nearest.append({"node_id": path.stem, "overlap_terms": overlap[:8], "score": len(overlap)})
    nearest = sorted(nearest, key=lambda row: (-int(row["score"]), str(row["node_id"])))[:5]
    return {
        "schema_version": "graph_dedupe_review.v1",
        "status": "executed",
        "nearest_nodes": nearest,
        "dedupe_method": "bounded_token_overlap_against_existing_concept_nodes",
        "merge_or_supersede_decision": "no_existing_node" if not nearest else "attach_or_review_nearest_nodes",
        "hard_nonclaims": [
            "graph_dedupe_is_bounded_local_overlap_not_full_semantic_equivalence",
        ],
    }


def _worker_program_record(*, query_terms: list[str], source_keys: list[str]) -> dict[str, str]:
    program = {
        "role": "memory_saver",
        "intent": "domain_evidence_lookup_before_memory_ticket_promotion",
        "query_terms": query_terms,
        "source_keys": sorted(source_keys),
        "steps": [
            "load configured markdown source roots",
            "rank bounded line windows by query term overlap",
            "attach pointer-only evidence refs",
            "reject if minimum evidence is missing",
        ],
    }
    raw = json.dumps(program, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return {
        "code_hash": f"sha256:{digest}",
        "worker_authored_ptc_program_ref": f"ptc-program-ref://memory_saver/domain-evidence-{digest[:16]}",
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _merge_unique(values: list[str] | Any) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


__all__ = [
    "REQUEST_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "build_domain_evidence_request",
    "enrich_memory_ticket_payload",
]
