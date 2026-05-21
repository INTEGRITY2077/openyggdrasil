from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from runtime.common.contract_validation import validate_contract_payload


RAW_SOURCE_SCHEMA = "raw_source.v1.schema.json"
SOURCE_CELL_SCHEMA = "source_cell.v1.schema.json"
WIKI_PAGE_SCHEMA = "wiki_page.v1.schema.json"
WIKI_INDEX_ENTRY_SCHEMA = "wiki_index_entry.v1.schema.json"
WIKI_LOG_ENTRY_SCHEMA = "wiki_log_entry.v1.schema.json"
WIKI_INGEST_TICKET_SCHEMA = "wiki_ingest_ticket.v1.schema.json"
WIKI_PAGE_MUTATION_SCHEMA = "wiki_page_mutation.v1.schema.json"
SUPPORT_BUNDLE_V2_SCHEMA = "support_bundle.v2.schema.json"

REQUIRED_WIKI_SECTIONS = (
    "## What This Page Decides",
    "## Why It Matters",
    "## Core Distinction",
    "## Ontology Position",
    "## Decision Path",
    "## Common Confusions",
    "## Examples",
    "## How This Changed Over Time",
    "## Community Growth Notes",
    "## Source Synthesis",
    "## Related Pages",
    "## Open Questions",
    "## Maintenance Notes",
    "## Machine Appendix",
)

PROOF_FIRST_MARKERS = (
    "receipt",
    "produced_count",
    "quality verdict",
    "quality_assessment",
    "source_ref_status",
    "proof report",
    "storage_receipt",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strings(values: Iterable[Any]) -> list[str]:
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def validate_raw_source(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, RAW_SOURCE_SCHEMA)


def validate_source_cell(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, SOURCE_CELL_SCHEMA)


def validate_wiki_page(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_PAGE_SCHEMA)


def validate_index_entry(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_INDEX_ENTRY_SCHEMA)


def validate_log_entry(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_LOG_ENTRY_SCHEMA)


def validate_wiki_ingest_ticket(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_INGEST_TICKET_SCHEMA)


def validate_wiki_page_mutation(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, WIKI_PAGE_MUTATION_SCHEMA)


def validate_support_bundle_v2(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, SUPPORT_BUNDLE_V2_SCHEMA)


def build_source_cell(
    *,
    raw_source_ref: str,
    origin_locator: str,
    supports: Iterable[str],
    does_not_support: Iterable[str] | None = None,
    captured_at: str | None = None,
    anchor_hash: str | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    payload = {
        "schema_version": "source_cell.v1",
        "source_cell_id": _stable_id("src-cell", raw_source_ref, origin_locator, list(supports)),
        "raw_source_ref": raw_source_ref,
        "origin_locator": origin_locator,
        "supports": _strings(supports),
        "does_not_support": _strings(does_not_support or []),
        "captured_at": captured_at or _now(),
        "anchor_hash": anchor_hash,
        "confidence": confidence,
        "hard_nonclaims": [
            "source_cell_is_not_a_wiki_page",
            "source_cell_support_is_claim_scoped_not_production_ready_evidence",
        ],
    }
    validate_source_cell(payload)
    return payload


def build_wiki_page_from_ring_node(
    *,
    ring_node: Mapping[str, Any],
    page_ref: str,
    source_cell_refs: Iterable[str],
    machine_appendix_ref: str,
) -> dict[str, Any]:
    topic = ring_node.get("canonical_topic") or {}
    capsule = ring_node.get("decision_capsule") or {}
    title = str(topic.get("title") or ring_node.get("node_id") or "Untitled wiki page").strip()
    context = str(capsule.get("context") or "").strip()
    decision = str(capsule.get("decision") or capsule.get("conclusion") or "").strip()
    reuse_condition = str(capsule.get("reuse_condition") or "").strip()
    forbidden = _strings(_as_list(capsule.get("forbidden")))
    related = []
    for rel in ring_node.get("related_pages") or []:
        if isinstance(rel, Mapping) and rel.get("page_ref"):
            related.append(
                {
                    "page_ref": str(rel.get("page_ref")),
                    "relation": str(rel.get("relation") or "related"),
                    "why_related": str(rel.get("why_related") or "Shares a reusable decision context."),
                }
            )
    community = ring_node.get("community") or {}
    retrieval_contract = ring_node.get("retrieval_contract") if isinstance(ring_node.get("retrieval_contract"), Mapping) else {}
    retrieval_terms = _unique_strings(
        [
            *_strings(retrieval_contract.get("retrieval_terms") or []),
            *_strings(retrieval_contract.get("keywords") or []),
        ]
    )
    timeline = [
        item
        for item in ring_node.get("decision_timeline") or []
        if isinstance(item, Mapping)
    ]
    growth = [
        item
        for item in ring_node.get("community_growth_events") or []
        if isinstance(item, Mapping)
    ]
    if not related and community.get("community_id"):
        related.append(
            {
                "page_ref": f"oy-vault://communities/{str(community.get('community_id')).replace(':', '/')}.md",
                "relation": "community_context",
                "why_related": "This page belongs to the same knowledge community.",
            }
        )
    timeline_summary = _timeline_summary(timeline)
    examples = _strings(
        [
            _example_from_decision(decision),
            _example_from_reuse_condition(reuse_condition),
        ]
    )
    payload = {
        "schema_version": "wiki_page.v1",
        "page_ref": page_ref,
        "canonical_title": title,
        "display_title": title,
        "what_it_is": decision or context or "A reusable OpenYggdrasil wiki topic.",
        "why_it_matters": context or reuse_condition or "Future providers can reuse this without rereading the full source.",
        "key_points": _unique_strings(
            [
                decision,
                reuse_condition,
                str(capsule.get("conclusion") or "").strip(),
            ]
        )
        or ["This page summarizes a reusable source-backed distinction."],
        "examples": examples or ["Use this page when the same distinction appears in a later conversation."],
        "time_direction": timeline_summary
        or "The page records an initial Provider source, an MS1 admission decision, and later category/community updates when they occur.",
        "community_growth_summary": _community_growth_summary(growth),
        "important_distinctions": forbidden
        or ["Keep adjacent topics separate until an accepted later source explicitly bridges them."],
        "retrieval_terms": retrieval_terms,
        "related_pages": related,
        "source_cell_refs": _strings(source_cell_refs),
        "open_questions": _strings(ring_node.get("open_questions") or []),
        "machine_appendix_ref": machine_appendix_ref,
        "hard_nonclaims": [
            "wiki_page_is_not_a_provider_answer",
            "wiki_page_is_not_a_receipt_or_production_ready_proof",
            "mf1_safe_recall_and_provider_rejudgment_still_apply",
        ],
    }
    validate_wiki_page(payload)
    return payload


def build_index_entry(
    *,
    wiki_page: Mapping[str, Any],
    category_path: str,
    updated_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "wiki_index_entry.v1",
        "page_ref": wiki_page["page_ref"],
        "canonical_title": wiki_page["canonical_title"],
        "category_path": category_path,
        "summary": wiki_page["what_it_is"],
        "updated_at": updated_at or _now(),
        "source_cell_refs": list(wiki_page.get("source_cell_refs") or []),
        "related_page_refs": [
            str(item.get("page_ref"))
            for item in wiki_page.get("related_pages") or []
            if isinstance(item, Mapping) and item.get("page_ref")
        ],
    }
    validate_index_entry(payload)
    return payload


def build_log_entry(
    *,
    operation: str,
    summary: str,
    pages_touched: Iterable[str],
    source_ref: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "wiki_log_entry.v1",
        "log_id": _stable_id("wiki-log", operation, summary, list(pages_touched), source_ref),
        "timestamp": timestamp or _now(),
        "operation": operation,
        "summary": summary,
        "pages_touched": _strings(pages_touched),
        "source_ref": source_ref,
        "hard_nonclaims": [
            "log_entry_records_an_operation_not_final_support",
        ],
    }
    validate_log_entry(payload)
    return payload


def render_wiki_page_markdown(
    *,
    wiki_page: Mapping[str, Any],
    source_cells: Iterable[Mapping[str, Any]] = (),
    machine_appendix: Mapping[str, Any] | None = None,
) -> str:
    validate_wiki_page(wiki_page)
    cell_rows = list(source_cells)
    for cell in cell_rows:
        validate_source_cell(cell)
    related = wiki_page.get("related_pages") or []
    open_questions = wiki_page.get("open_questions") or []
    title = str(wiki_page["canonical_title"])
    what_it_is = str(wiki_page["what_it_is"])
    why_it_matters = str(wiki_page["why_it_matters"])
    core_rule = str((wiki_page.get("key_points") or [wiki_page.get("what_it_is")])[0])
    lines = [
        "---",
        "schema_version: wiki_article.v1",
        "article_role: representative_tree",
        f"page_ref: {wiki_page['page_ref']}",
        f"title: {title}",
        f"root_claim: {what_it_is.replace(chr(10), ' ')}",
        "---",
        f"# {title}",
        "",
        "## What This Page Decides",
        _decision_intro_text(title=title, what_it_is=what_it_is),
        "",
        "## Why It Matters",
        _why_it_matters_text(why_it_matters=why_it_matters),
        "",
        "## Core Distinction",
        _core_distinction_text(core_rule=core_rule),
        "",
        "## Ontology Position",
        _ontology_position_text(machine_appendix=machine_appendix, wiki_page=wiki_page),
        "",
        "## Decision Path",
        _decision_path_text(core_rule=core_rule, wiki_page=wiki_page),
        "",
        "## Common Confusions",
        *_common_confusion_lines(wiki_page=wiki_page),
        "",
        "## Examples",
        *[f"- {item}" for item in wiki_page.get("examples") or []],
        "",
        "## How This Changed Over Time",
        _time_direction_text(wiki_page=wiki_page),
        "",
        "## Community Growth Notes",
        _community_growth_note_text(wiki_page=wiki_page),
        "",
        "## Source Synthesis",
        _source_synthesis_text(wiki_page=wiki_page, source_cells=cell_rows),
        "",
        "## Related Pages",
    ]
    if related:
        lines.extend(
            f"- {item.get('relation')}: {item.get('page_ref')} - {item.get('why_related')}"
            for item in related
            if isinstance(item, Mapping)
        )
    else:
        lines.append("- No related page has been accepted yet.")
    lines.extend(
        [
            "",
            "## Open Questions",
        ]
    )
    if open_questions:
        lines.extend(f"- {item}" for item in open_questions)
    else:
        lines.extend(_default_open_questions())
    lines.extend(
        [
            "",
            "## Maintenance Notes",
            *_maintenance_note_lines(),
        ]
    )
    lines.extend(
        [
            "",
            "## Machine Appendix",
            "```json",
            _json_block(machine_appendix or {"wiki_page": dict(wiki_page)}),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _decision_intro_text(*, title: str, what_it_is: str) -> str:
    return (
        f"{title}는 나중에 같은 질문이 돌아왔을 때 다시 판단할 수 있도록 남기는 "
        f"중심 article입니다. 이 page가 결정하는 핵심은 다음입니다: {what_it_is} "
        "본문은 먼저 사람이 읽는 판단 지도를 제공하고, 실행 흔적과 기계 필드는 뒤의 appendix로 분리합니다."
    )


def _why_it_matters_text(*, why_it_matters: str) -> str:
    return (
        f"{why_it_matters} 이 구분이 장기 지식이 되는 이유는, 한 번의 답변보다 이후의 팀 문서, "
        "재질문, 인접 주제 분리, 회상 판단에 반복해서 쓰이기 때문입니다. 사용자가 헷갈린 지점이 "
        "다시 나타나면 Provider는 이 article을 직접 주장으로 복사하지 않고, MF1 support와 현재 질문을 "
        "다시 맞춰 본 뒤 필요한 결론만 답해야 합니다."
    )


def _ontology_position_text(
    *,
    machine_appendix: Mapping[str, Any] | None,
    wiki_page: Mapping[str, Any],
) -> str:
    appendix = machine_appendix if isinstance(machine_appendix, Mapping) else {}
    category = appendix.get("semantic_category_path") if isinstance(appendix.get("semantic_category_path"), Mapping) else {}
    category_path = str(category.get("path") or "").strip()
    if not category_path:
        page_ref = str(wiki_page.get("page_ref") or "")
        marker = "oy-vault://categories/"
        if page_ref.startswith(marker):
            category_path = page_ref.removeprefix(marker).rsplit("/", 1)[0]
    segments = [segment for segment in category_path.split("/") if segment]
    continent = segments[0] if segments else "unknown"
    mountain = " / ".join(segments[:2]) if len(segments) >= 2 else continent
    forest = " / ".join(segments[:3]) if len(segments) >= 3 else mountain
    tree = str(wiki_page.get("canonical_title") or "this article")
    return (
        f"Continent는 `{continent}`입니다. Mountain은 `{mountain}`이고, Forest는 `{forest}`입니다. "
        f"Tree는 `{tree}`라는 사람이 읽는 wiki article입니다. Branch는 이 article 안의 판단 경로와 "
        "적용 조건이고, Leaf는 실제 답변에 재사용되는 최소 구분입니다. Chloroplast는 그 Leaf를 살리는 "
        "원본 근거 장치이므로 본문에서 결론처럼 보이지 않고 appendix에 묶입니다."
    )


def _core_distinction_text(*, core_rule: str) -> str:
    return (
        f"{core_rule} 같은 이름을 공유하는 항목이라도 하는 일이 다르면 같은 칸에 넣지 않습니다. "
        "실행 방식, 정의가 공급되는 위치, 자동으로 발화되는 조건, 모델이 읽는 절차, 외부 시스템 연결, "
        "배포 단위는 서로 다른 축입니다. 이 page는 그 축들을 섞지 않기 위한 기준선입니다."
    )


def _decision_path_text(*, core_rule: str, wiki_page: Mapping[str, Any]) -> str:
    distinctions = _strings(wiki_page.get("important_distinctions") or [])
    first_distinction = distinctions[0] if distinctions else "제목이 비슷하다는 이유만으로 인접 주제를 합치지 않습니다."
    return (
        "1. 먼저 질문이 어떤 일을 결정하려는지 봅니다. 실행 방식인지, 정의 위치인지, 자동 실행인지, "
        "모델이 읽는 절차인지, 외부 연결인지, 배포 단위인지 분리합니다.\n"
        f"2. 질문이 이 page의 중심 규칙과 맞으면 `{core_rule}`를 기준으로 답합니다.\n"
        f"3. 인접 주제와 겹쳐 보이면 `{first_distinction}`라는 경계를 먼저 적용합니다.\n"
        "4. 이후 source가 이 경계를 바꾸면 기존 문장을 덮어쓰지 않고 timeline과 maintenance note로 바꾼 이유를 남깁니다."
    )


def _common_confusion_lines(*, wiki_page: Mapping[str, Any]) -> list[str]:
    distinctions = _strings(wiki_page.get("important_distinctions") or [])
    lines = [
        "- 이름이 비슷한 항목을 같은 category로 합치면 안 됩니다.",
        "- 실행 모델과 정의 공급 위치를 같은 축으로 놓으면 나중에 MF1 recall이 엉뚱한 support를 반환할 수 있습니다.",
        "- Provider가 이 page를 본문 그대로 사용자에게 보여주는 것이 아니라, 현재 질문에 맞는 결론으로 재판단해야 합니다.",
    ]
    for item in distinctions[:3]:
        lines.append(f"- {item}")
    return lines


def _time_direction_text(*, wiki_page: Mapping[str, Any]) -> str:
    timeline = str(wiki_page.get("time_direction") or "").strip()
    return (
        "- 초기: 사용자의 질문에서 반복될 수 있는 혼동 축이 드러납니다.\n"
        "- 중반: MS1은 그 혼동이 단일 취향인지, 나중에 다시 쓸 지식인지, 인접 주제와 분리해야 하는지 판단합니다.\n"
        "- 후반: category, community, related page, maintenance 상태가 붙으면서 이 article이 Tree 단위로 안정화됩니다.\n"
        f"- 현재 lineage: {timeline or 'accepted source와 storage admission만 확인됐고, 이후 revision은 아직 없습니다.'}"
    )


def _community_growth_note_text(*, wiki_page: Mapping[str, Any]) -> str:
    growth = str(wiki_page.get("community_growth_summary") or "").strip()
    return (
        f"{growth} 이 community는 시차가 있는 source가 들어올 때마다 무조건 merge하지 않고 "
        "attach, child, sibling, split, reject, bridge 중 하나로 기록해야 합니다. discontinuous update가 들어오면 "
        "기존 결론을 조용히 바꾸지 말고 어떤 Branch가 바뀌었는지 남깁니다."
    )


def _default_open_questions() -> list[str]:
    return [
        "- 나중에 들어온 source가 이 page를 attach해야 하는지, child page로 내려야 하는지 확인해야 합니다.",
        "- 비슷한 title의 sibling page와 overmerge될 위험이 있는지 Janitor가 주기적으로 봐야 합니다.",
        "- MF1이 이 page를 support로 쓸 때 현재 질문과 category boundary가 여전히 맞는지 확인해야 합니다.",
    ]


def _maintenance_note_lines() -> list[str]:
    return [
        "- stale: 나중에 공식 문서나 대화 기준이 바뀌면 기존 문장을 덮어쓰지 말고 revision으로 남깁니다.",
        "- split/merge: 인접 topic과 합치거나 나눌 때는 title 유사도가 아니라 source-backed decision을 기준으로 합니다.",
        "- tombstone/repair: 잘못 붙은 page는 삭제 대신 tombstone 또는 repair note를 남겨 MF1 final support에서 제외합니다.",
        "- lint: proof scaffold, local path, mailbox id, quality self-claim이 본문으로 올라오면 production support를 막습니다.",
    ]


def _category_placement_text(
    *,
    machine_appendix: Mapping[str, Any] | None,
    wiki_page: Mapping[str, Any],
) -> str:
    appendix = machine_appendix if isinstance(machine_appendix, Mapping) else {}
    category = appendix.get("semantic_category_path") if isinstance(appendix.get("semantic_category_path"), Mapping) else {}
    category_path = str(category.get("path") or "").strip()
    if not category_path:
        page_ref = str(wiki_page.get("page_ref") or "")
        marker = "oy-vault://categories/"
        if page_ref.startswith(marker):
            category_path = page_ref.removeprefix(marker).rsplit("/", 1)[0]
    if not category_path:
        return "No accepted category path has been attached yet; keep this page candidate-only for placement decisions."
    segments = [segment for segment in category_path.split("/") if segment]
    if not segments:
        return "No accepted category path has been attached yet; keep this page candidate-only for placement decisions."
    continent = segments[0]
    mountain = " / ".join(segments[:2]) if len(segments) >= 2 else continent
    forest = " / ".join(segments[:3]) if len(segments) >= 3 else mountain
    tree_area = category_path
    return (
        f"This page is filed under `{tree_area}`. "
        f"Continent: `{continent}`. Mountain: `{mountain}`. Forest: `{forest}`. "
        "Use this placement to decide whether a later source should attach here, become a child page, split as a sibling, or stay rejected."
    )


def _retrieval_surface_lines(*, wiki_page: Mapping[str, Any]) -> list[str]:
    terms = _strings(wiki_page.get("retrieval_terms") or [])
    if not terms:
        terms = _strings(wiki_page.get("key_points") or [])[:4]
    if not terms:
        return ["- No accepted retrieval terms yet; keep recall conservative."]
    return [f"- {term}" for term in terms[:12]]


def _timeline_summary(events: Iterable[Mapping[str, Any]]) -> str:
    rows = list(events)
    if not rows:
        return ""
    labels: list[str] = []
    for row in rows[:5]:
        owner = str(row.get("decision_owner") or row.get("owner") or "system")
        kind = str(row.get("decision_kind") or row.get("event_kind") or "decision")
        labels.append(f"{owner}:{kind}")
    return "Decision lineage so far: " + " -> ".join(labels) + "."


def _community_growth_summary(events: Iterable[Mapping[str, Any]]) -> str:
    rows = list(events)
    if not rows:
        return "No accepted community growth event yet."
    kinds = [str(row.get("event_kind") or "event") for row in rows[:5]]
    return "Community growth recorded as: " + ", ".join(kinds) + "."


def _example_from_decision(decision: str) -> str:
    text = str(decision or "").strip()
    if not text:
        return ""
    return f"When a later question asks this same distinction, start from: {text}"


def _example_from_reuse_condition(reuse_condition: str) -> str:
    text = str(reuse_condition or "").strip()
    if not text:
        return ""
    return f"Reuse condition: {text}"


def _source_synthesis_text(*, wiki_page: Mapping[str, Any], source_cells: Iterable[Mapping[str, Any]]) -> str:
    cells = list(source_cells)
    if not cells:
        return "No accepted source cell has been attached, so this page must stay candidate-only."
    supports: list[str] = []
    limits: list[str] = []
    for cell in cells:
        supports.extend(str(item).strip() for item in cell.get("supports") or [] if str(item).strip())
        limits.extend(str(item).strip() for item in cell.get("does_not_support") or [] if str(item).strip())
    support_text = supports[0] if supports else str(wiki_page.get("what_it_is") or "the page claim")
    return (
        "The conversation source supplies the user's recurring confusion, the stabilized distinction, and the reuse need.\n\n"
        "The raw source is not copied into the article; it is reduced into the smallest durable rule that can survive later context loss.\n\n"
        f"The current source supports this reusable distinction: {support_text}. It does not support nearby topics by title similarity alone, and it does not claim documentation coverage unless later source notes add that evidence.\n\n"
        "Source notes, documentation references, and future raw conversation cells should extend this section only when they change the decision path, boundary, or maintenance state."
    )


def lint_wiki_page_markdown(markdown: str) -> dict[str, Any]:
    body, marker, _appendix = markdown.partition("## Machine Appendix")
    missing_sections = [section for section in REQUIRED_WIKI_SECTIONS if section not in markdown]
    proof_markers_in_body = [
        marker_text
        for marker_text in PROOF_FIRST_MARKERS
        if marker_text.lower() in body.lower()
    ]
    result = {
        "schema_version": "wiki_page_lint_result.v1",
        "status": "pass" if not missing_sections and not proof_markers_in_body and marker else "fail",
        "missing_sections": missing_sections,
        "proof_markers_in_body": proof_markers_in_body,
        "hard_nonclaims": [
            "lint_pass_is_not_live_ux_proof",
            "lint_pass_is_not_production_ready",
        ],
    }
    return result


__all__ = [
    "RAW_SOURCE_SCHEMA",
    "SOURCE_CELL_SCHEMA",
    "SUPPORT_BUNDLE_V2_SCHEMA",
    "WIKI_INDEX_ENTRY_SCHEMA",
    "WIKI_INGEST_TICKET_SCHEMA",
    "WIKI_LOG_ENTRY_SCHEMA",
    "WIKI_PAGE_MUTATION_SCHEMA",
    "WIKI_PAGE_SCHEMA",
    "build_index_entry",
    "build_log_entry",
    "build_source_cell",
    "build_wiki_page_from_ring_node",
    "lint_wiki_page_markdown",
    "render_wiki_page_markdown",
    "validate_index_entry",
    "validate_log_entry",
    "validate_raw_source",
    "validate_source_cell",
    "validate_support_bundle_v2",
    "validate_wiki_ingest_ticket",
    "validate_wiki_page",
    "validate_wiki_page_mutation",
]
