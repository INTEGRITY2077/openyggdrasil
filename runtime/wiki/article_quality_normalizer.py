from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.common.jsonl_io import append_jsonl_atomic
from runtime.retrieval.safe_index_cursor import load_safe_index_cursor
from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article


CONTENT_FIRST_REPAIR_RUN_KIND = "content_first_active_article_normalization"
ACTIVE_ARTICLE_SECTION_ORDER = (
    "What This Page Is",
    "Why It Matters",
    "Key Points",
    "Operating Rule",
    "Category Placement",
    "Retrieval Surface",
    "Examples",
    "How This Changed",
    "Source Synthesis",
    "Important Distinctions",
    "Maintenance Notes",
    "Related Pages",
    "Wiki Operations",
    "Data Gaps",
    "Open Questions",
    "Machine Appendix",
)
BODY_FORBIDDEN_TERMS = (
    "receipt",
    "produced_count",
    "mail_id",
    "work_order_id",
    "source_ref",
    "source_ref_status",
    "message_index_range",
    "anchor_hash",
    "resolver_status",
    "hard_nonclaims",
    "reason_codes",
    "quality verdict",
    "production-ready",
    "production ready",
    "production readiness",
)


def normalize_active_wiki_article(markdown: str, *, path_hint: str, run_id: str) -> tuple[str, dict[str, Any]]:
    """Render an existing active article into the content-first production shape."""

    frontmatter = _frontmatter(markdown)
    sections = _sections(markdown)
    existing_appendix = _first_json_payload(markdown)
    title = _clean_inline(frontmatter.get("title") or _first_h1(markdown) or Path(path_hint).stem.replace("-", " ").title())
    root_claim = _clean_sentence(
        frontmatter.get("root_claim")
        or _first_sentence(_section(sections, "What This Page Is"))
        or f"{title} is a reusable wiki article."
    )
    page_ref = _page_ref(frontmatter, path_hint)
    semantic_category_path = _clean_inline(
        frontmatter.get("semantic_category_path")
        or _category_from_path_hint(path_hint)
    )
    retrieval_terms = _retrieval_terms(markdown, title=title, semantic_category_path=semantic_category_path)
    related_pages = _semantic_related_pages(markdown, semantic_category_path=semantic_category_path)
    appendix = _machine_appendix(
        original_frontmatter=frontmatter,
        existing_appendix=existing_appendix,
        path_hint=path_hint,
        page_ref=page_ref,
        semantic_category_path=semantic_category_path,
        run_id=run_id,
    )

    rendered_sections = {
        "What This Page Is": _paragraph(
            _section(sections, "What This Page Is")
            or _section(sections, "What Problem This Solves")
            or root_claim
        ),
        "Why It Matters": _paragraph(
            _section(sections, "Why It Matters")
            or f"{title} matters because later questions need the same distinction without rereading the whole source conversation."
        ),
        "Key Points": _bullets(
            _list_items(_section(sections, "Key Points"))
            or _split_key_points(
                _section(sections, "Core Distinction")
                or _section(sections, "Operating Rule")
                or root_claim
            )
        ),
        "Operating Rule": _paragraph(
            _section(sections, "Operating Rule")
            or _section(sections, "Core Rule")
            or f"Use this page when a later question needs the same boundary as {title}; split or reject adjacent topics when the source does not bridge them."
        ),
        "Category Placement": _category_placement_text(semantic_category_path),
        "Retrieval Surface": _bullets(retrieval_terms),
        "Examples": _bullets(_examples(title, semantic_category_path)),
        "How This Changed": _time_direction_text(frontmatter, sections),
        "Source Synthesis": _source_synthesis_text(sections, title),
        "Important Distinctions": _bullets(
            _list_items(_section(sections, "Important Distinctions"))
            or _list_items(_section(sections, "Data Gaps"))
            or [
                f"Use {title} only for its stated topic boundary.",
                "Keep sibling topics separate until a later source explicitly bridges them.",
                "Treat source cells and machine metadata as evidence support, not as the article body.",
            ]
        ),
        "Maintenance Notes": _paragraph(
            _section(sections, "Maintenance Notes")
            or "Future updates should change the article through a logged mutation, keep related pages semantic, and move stale or mismatched support to repair or exclusion."
        ),
        "Related Pages": _bullets(related_pages),
        "Wiki Operations": "\n".join(
            [
                "- Ingest: capture the raw source pointer, bounded range, hash, provider, and category decision before the article is trusted.",
                "- Query: MF1 may use this page only when safe cursor membership and source-backed support still match the current question.",
                "- Lint: Janitor checks stale, duplicate, conflict, unsafe, local path, and repair-needed states before this page can support an answer.",
                "- Index/log: index.md, log.md, category paths, and community events must stay aligned with this page.",
            ]
        ),
        "Data Gaps": _bullets(
            _data_gaps(sections)
            or [
                "The page may need later source-backed refinement when adjacent topics become strong enough to split.",
                "This article alone does not prove the whole memory system release gate.",
                "A future contradiction should create a repair event instead of silently overwriting the page.",
            ]
        ),
        "Open Questions": _bullets(
            _list_items(_section(sections, "Open Questions"))
            or ["None recorded for the current article state."]
        ),
        "Machine Appendix": "```json\n" + json.dumps(appendix, ensure_ascii=False, indent=2, sort_keys=True) + "\n```",
    }

    lines = [
        "---",
        "schema_version: wiki_article.v1",
        "article_role: representative_tree",
        "status: ACTIVE",
        f'title: "{_frontmatter_quote(title)}"',
        f'root_claim: "{_frontmatter_quote(root_claim)}"',
        f"page_ref: {page_ref}",
        f"semantic_category_path: {semantic_category_path}",
        "---",
        f"# {title}",
        "",
    ]
    for section in ACTIVE_ARTICLE_SECTION_ORDER:
        lines.extend([f"## {section}", rendered_sections[section], ""])
    normalized = "\n".join(lines).rstrip() + "\n"
    gate = evaluate_content_first_wiki_article(normalized, path_hint=path_hint)
    return normalized, gate


def normalize_safe_cursor_articles(vault_root: Path, *, run_id: str) -> dict[str, Any]:
    cursor = load_safe_index_cursor(vault_root)
    repaired: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    category_paths = [
        str(path)
        for path in cursor.get("committed_paths", [])
        if str(path).startswith("vault/categories/")
        and str(path).endswith(".md")
        and "graphify-out" not in str(path)
    ]
    for rel_path in category_paths:
        path = vault_root / rel_path.removeprefix("vault/")
        if not path.exists():
            failed.append({"path": rel_path, "reason": "missing_safe_cursor_path"})
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        normalized, gate = normalize_active_wiki_article(original, path_hint=str(path), run_id=run_id)
        if gate["verdict"] != "pass":
            failed.append({"path": rel_path, "gate": gate})
            continue
        path.write_text(normalized, encoding="utf-8", newline="\n")
        repaired.append({"path": rel_path, "score": gate["score"], "reason_codes": gate["reason_codes"]})

    receipt = {
        "schema_version": "active_article_normalization_receipt.v1",
        "run_id": run_id,
        "created_at": _now_iso(),
        "repair_kind": CONTENT_FIRST_REPAIR_RUN_KIND,
        "safe_cursor_article_count": len(category_paths),
        "repaired_count": len(repaired),
        "failed_count": len(failed),
        "repaired": repaired,
        "failed": failed,
        "hard_nonclaims": [
            "article_normalization_is_not_live_provider_proof",
            "article_gate_pass_is_not_graphify_product_ux",
            "safe_cursor_membership_is_not_semantic_truth",
        ],
    }
    append_jsonl_atomic(vault_root / "_meta" / "repair_receipts.jsonl", receipt)
    append_jsonl_atomic(
        vault_root / "_meta" / "mutation_log.jsonl",
        {
            "schema_version": "wiki_page_mutation.v1",
            "mutation_id": f"mutation-{run_id}",
            "timestamp": receipt["created_at"],
            "operation": CONTENT_FIRST_REPAIR_RUN_KIND,
            "pages_touched": [item["path"] for item in repaired],
            "summary": "Normalized active safe-cursor wiki articles into content-first representative-tree pages.",
            "hard_nonclaims": receipt["hard_nonclaims"],
        },
    )
    return receipt


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", markdown, flags=re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _sections(markdown: str) -> dict[str, str]:
    result: dict[str, str] = {}
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        result[match.group(1).strip().casefold()] = markdown[start:end].strip()
    return result


def _section(sections: dict[str, str], name: str) -> str:
    return sections.get(name.casefold(), "").strip()


def _first_h1(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _first_sentence(text: str) -> str:
    compact = " ".join(str(text or "").split())
    match = re.search(r"(.+?[.!?])(?:\s|$)", compact)
    return match.group(1) if match else compact[:220]


def _page_ref(frontmatter: dict[str, str], path_hint: str) -> str:
    if frontmatter.get("page_ref", "").startswith("oy-vault://"):
        return frontmatter["page_ref"]
    normalized = path_hint.replace("\\", "/")
    marker = "/vault/"
    if marker in normalized:
        return "oy-vault://" + normalized.split(marker, 1)[1]
    return "oy-vault://" + Path(path_hint).name


def _category_from_path_hint(path_hint: str) -> str:
    normalized = path_hint.replace("\\", "/")
    marker = "/categories/"
    if marker not in normalized:
        return ""
    rel = normalized.split(marker, 1)[1]
    return rel.rsplit("/", 1)[0]


def _clean_inline(value: Any) -> str:
    return " ".join(str(value or "").replace("`", "").split()).strip()


def _clean_sentence(value: Any) -> str:
    text = _clean_inline(value)
    text = re.sub(r"\b(production-ready|production ready|production readiness)\b", "release gate", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(receipt|produced_count|mail_id|work_order_id|source_ref_status)\b", "operation record", text, flags=re.IGNORECASE)
    return text


def _paragraph(value: Any) -> str:
    lines = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        if any(term in line.lower() for term in BODY_FORBIDDEN_TERMS):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        lines.append(_clean_sentence(line))
    text = " ".join(lines).strip()
    return text or "This article records a reusable source-backed distinction for later retrieval and rejudgment."


def _list_items(value: str) -> list[str]:
    items: list[str] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        cleaned = _clean_sentence(re.sub(r"^[-*]\s+", "", line))
        if cleaned and not any(term in cleaned.lower() for term in BODY_FORBIDDEN_TERMS):
            items.append(cleaned)
    return _unique(items)


def _split_key_points(value: str) -> list[str]:
    text = _paragraph(value)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return _unique([part for part in parts if len(part) >= 20])[:5] or [text]


def _bullets(items: list[str]) -> str:
    cleaned = _unique([_clean_sentence(item) for item in items if _clean_sentence(item)])
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else "- None recorded."


def _retrieval_terms(markdown: str, *, title: str, semantic_category_path: str) -> list[str]:
    candidates: list[str] = [title]
    for section_name in ("Retrieval Surface", "Key Points", "Operating Rule"):
        section = _section(_sections(markdown), section_name)
        candidates.extend(_list_items(section))
        match = re.search(r"retrieval_terms\s*:\s*(.+)", section, flags=re.IGNORECASE)
        if match:
            candidates.extend(part.strip() for part in match.group(1).split(","))
    candidates.extend(segment.replace("-", " ") for segment in semantic_category_path.split("/") if segment)
    return _unique([item for item in candidates if len(item) >= 3])[:12]


def _examples(title: str, semantic_category_path: str) -> list[str]:
    topic = semantic_category_path.replace("/", " / ") or title
    return [
        f"Use this page when a later question asks for the same {topic} distinction in different words.",
        f"Attach a new source here only when it reinforces the {title} boundary.",
        "Split into a sibling page when the main question moves to a different decision axis.",
        "Return unsupported rather than stretching this page across an unrelated topic.",
    ]


def _time_direction_text(frontmatter: dict[str, str], sections: dict[str, str]) -> str:
    existing = _section(sections, "How This Changed") or _section(sections, "How This Changed Over The Conversation")
    if existing:
        return _paragraph(existing)
    source_ref = frontmatter.get("source_ref") or ""
    message_range = frontmatter.get("message_index_range") or ""
    if source_ref and message_range:
        return (
            "Earlier turns established the reusable boundary; later updates should record whether new evidence attaches, "
            "splits, bridges, or rejects the topic. The current source pointer and bounded range are preserved in the "
            "machine appendix so the article can change without losing lineage."
        )
    return (
        "Earlier turns provide the initial topic boundary. Later turns must be logged as attach, child, sibling, split, "
        "bridge, reject, or repair events instead of silently overwriting the article."
    )


def _source_synthesis_text(sections: dict[str, str], title: str) -> str:
    existing = _section(sections, "Source Synthesis") or _section(sections, "Sources") or _section(sections, "Source Notes")
    cleaned = _paragraph(existing)
    if cleaned and cleaned != "This article records a reusable source-backed distinction for later retrieval and rejudgment.":
        return cleaned
    return (
        f"{title} combines the bounded Provider conversation with accepted domain or project sources. "
        "The article states the reusable distinction in prose, while raw pointers, hashes, and lineage metadata stay in the appendix."
    )


def _semantic_related_pages(markdown: str, *, semantic_category_path: str) -> list[str]:
    items = []
    for item in _list_items(_section(_sections(markdown), "Related Pages")):
        lowered = item.lower()
        if "concepts/" in lowered or re.search(r"\bN-[a-f0-9]{8,}\b", item):
            continue
        if "ring-" in lowered or "claim:" in lowered:
            continue
        items.append(re.sub(r"^[-*]\s+", "", item).strip())
    if items:
        return _unique(items)[:8]
    segments = [segment for segment in semantic_category_path.split("/") if segment]
    related = []
    if len(segments) >= 2:
        related.append(f"Parent category: {' / '.join(segments[:-1])}")
    if len(segments) >= 3:
        related.append(f"Sibling review area: {' / '.join(segments[:2])}")
    related.append("Community page for this topic family")
    return related


def _category_placement_text(semantic_category_path: str) -> str:
    segments = [segment for segment in semantic_category_path.split("/") if segment]
    if not segments:
        return "No accepted semantic category path is attached yet; keep this page conservative until Amundsen or Janitor records one."
    continent = segments[0]
    mountain = " / ".join(segments[:2]) if len(segments) >= 2 else continent
    forest = " / ".join(segments[:3]) if len(segments) >= 3 else mountain
    tree = semantic_category_path
    return (
        f"This page sits in continent `{continent}`, mountain `{mountain}`, forest `{forest}`, and tree path `{tree}`. "
        "That placement is used to decide attach, child, sibling, split, bridge, or reject outcomes for later source-backed updates."
    )


def _data_gaps(sections: dict[str, str]) -> list[str]:
    items = _list_items(_section(sections, "Data Gaps"))
    return [
        item
        for item in items
        if "production-ready" not in item.lower()
        and "production ready" not in item.lower()
        and "receipt" not in item.lower()
        and "hard_nonclaims" not in item.lower()
        and "source_ref" not in item.lower()
    ]


def _machine_appendix(
    *,
    original_frontmatter: dict[str, str],
    existing_appendix: dict[str, Any],
    path_hint: str,
    page_ref: str,
    semantic_category_path: str,
    run_id: str,
) -> dict[str, Any]:
    source_ref = original_frontmatter.get("source_ref") or existing_appendix.get("source_ref")
    message_index_range = original_frontmatter.get("message_index_range") or existing_appendix.get("message_index_range")
    anchor_hash = original_frontmatter.get("anchor_hash") or existing_appendix.get("anchor_hash")
    provider_source_event_ref = original_frontmatter.get("provider_source_event_ref") or existing_appendix.get("provider_source_event_ref")
    reason_codes = _parse_frontmatter_list(original_frontmatter.get("reason_codes")) or [
        str(item) for item in existing_appendix.get("reason_codes", []) if str(item).strip()
    ]
    return {
        "schema_version": "wiki_article_machine_appendix.v1",
        "page_ref": page_ref,
        "semantic_category_path": semantic_category_path,
        "source_ref": source_ref,
        "message_index_range": message_index_range,
        "anchor_hash": anchor_hash,
        "provider_source_event_ref": provider_source_event_ref,
        "confidence_value": original_frontmatter.get("confidence") or existing_appendix.get("confidence_value") or existing_appendix.get("confidence"),
        "reason_codes": reason_codes,
        "lineage_contracts": {
            "wiki_continent_page": {
                "schema_version": "wiki_continent_page.v1",
                "page_ref": page_ref,
                "semantic_category_path": semantic_category_path,
                "contract_role": "production_facing_article_lineage",
            },
            "provider_source_event": {
                "schema_version": "provider_source_event.v1",
                "event_id": provider_source_event_ref,
                "source_ref": source_ref,
                "message_index_range": message_index_range,
                "anchor_hash": anchor_hash,
            },
            "decision_timeline_event": {
                "schema_version": "decision_timeline_event.v1",
                "event_kind": "article_normalized_for_content_first_gate",
                "decision_owner": "janitor",
                "reason_codes": ["content_first_normalization", *reason_codes[:4]],
            },
            "semantic_category_path": {
                "schema_version": "semantic_category_path.v1",
                "path": semantic_category_path,
                "segments": [segment for segment in semantic_category_path.split("/") if segment],
                "physical_storage_is_not_semantic_category": True,
            },
            "community_growth_event": {
                "schema_version": "community_growth_event.v1",
                "event_kind": "article_normalization_reinforced_existing_topic",
                "topic_key": semantic_category_path,
                "reason_codes": ["content_first_article_repaired_without_topic_merge"],
            },
        },
        "repair": {
            "run_id": run_id,
            "repair_kind": CONTENT_FIRST_REPAIR_RUN_KIND,
            "source_path_role": "active_safe_cursor_article",
        },
        "hard_nonclaims": [
            "content_first_article_gate_is_not_whole_system_production_readiness",
            "machine_appendix_is_not_user_answer_material",
            "mf1_safe_recall_and_provider_rejudgment_still_apply",
        ],
        "original_path_hint": _vault_ref_from_path_hint(path_hint),
    }


def _parse_frontmatter_list(value: str | None) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return _unique(part.strip().strip("'").strip('"') for part in raw.split(",") if part.strip())


def _first_json_payload(markdown: str) -> dict[str, Any]:
    for match in re.finditer(r"```json\s*(.*?)\s*```", markdown, flags=re.DOTALL):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _frontmatter_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _vault_ref_from_path_hint(path_hint: str) -> str:
    normalized = path_hint.replace("\\", "/")
    marker = "/vault/"
    if marker in normalized:
        return "oy-vault://" + normalized.split(marker, 1)[1]
    if normalized.startswith("vault/"):
        return "oy-vault://" + normalized.removeprefix("vault/")
    return Path(normalized).name


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = [
    "normalize_active_wiki_article",
    "normalize_safe_cursor_articles",
]
