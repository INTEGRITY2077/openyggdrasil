from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable


REPRESENTATIVE_SCHEMA_VERSION = "wiki_article.v1"
REPRESENTATIVE_ARTICLE_ROLE = "representative_tree"
LOCKED_FIXTURE_STATUS = "locked_quality_fixture"

LATIN1_ARTIFACT_CODEPOINTS = (0x00C3,)

CONTROL_OPENING_MARKERS = (
    "llm anchor block",
    "use_when:",
    "do_not_use_when:",
    "this page preserves a reusable, source-backed boundary from a provider discussion",
    "this is the production-facing wiki page for a source-backed openyggdrasil memory",
    "mf1 must not return final support",
)

SELF_QUALITY_MARKERS = (
    "quality_verdict: pass",
    "quality verdict: pass",
    "quality_assessment",
    "confidence: 0.88",
    "confidence: 0.97",
    "human_evaluator_not_executed",
)

BODY_CONTAMINATION_MARKERS = (
    "이 저장 내용이",
    "저장 처리 완료",
    "저장됨이라고 말할 수",
    "이 소스가 노드에 충분한 이유",
    "추출된 주장",
    "커뮤니티와의 연결 방식",
    "이것이 증명하지 못하는 것",
    "receipt",
    "produced_count",
    "mail_id",
    "work_order_id",
    "source_ref_status",
    "quality verdict",
    "production-ready",
    "production ready",
    "production readiness",
)

PROOF_PATH_DUMP_RE = re.compile(
    r"\b(receipt|produced_count|source_ref_status|work_order|mail_id)\s*[:=]"
    r"|\b(work_order|mail_id)[_-]id\b"
)

ARTICLE_SECTION_GROUPS = {
    "intro": (
        "## What This Page Decides",
        "## What Problem This Solves",
        "## What It Is",
        "## What This Page Explains",
        "## What This Page Is",
    ),
    "core": (
        "## Core Distinction",
        "## Core Rule",
        "## Operating Rule",
        "## Key Points",
    ),
    "examples": ("## Examples",),
    "change": (
        "## How This Changed",
        "## How This Changed Over The Conversation",
        "## How This Changed Over Time",
        "## Time Direction",
        "## Log",
        "## Decision Timeline",
    ),
    "sources": ("## Source Notes", "## Sources", "## Source Synthesis"),
    "related": ("## Related Pages",),
    "appendix": ("## Machine Appendix",),
}


def classify_wiki_artifact(markdown: str, *, path_hint: str = "") -> str:
    text = markdown.lower()
    normalized_path = path_hint.replace("\\", "/").lower()
    frontmatter = _frontmatter(markdown)
    if has_mojibake(markdown):
        return "invalid_mojibake"
    if "/concepts/n-" in normalized_path or "/concepts/prn-" in normalized_path:
        return "machine_mirror"
    if "/queries/" in normalized_path:
        return "query_projection"
    if "/_meta/" in normalized_path or "/sources/" in normalized_path or "/provenance/" in normalized_path:
        return "provenance_node"
    if any(marker in text[:2400] for marker in CONTROL_OPENING_MARKERS):
        return "retrieval_guard_card"
    if "## Active Safe Nodes" in markdown or "## Community Growth" in markdown and "## Knowledge Edges" in markdown:
        return "category_index"
    if _is_locked_fixture(frontmatter):
        return "wiki_article_fixture"
    if _is_representative_article(frontmatter):
        return "wiki_article"
    if _looks_like_article(markdown):
        return "article_shaped_unclassified"
    return "unclassified_markdown"


def has_mojibake(markdown: str) -> bool:
    if "\ufffd" in markdown:
        return True
    if any(0x80 <= ord(char) <= 0x9F for char in markdown):
        return True
    if any(chr(codepoint) in markdown for codepoint in LATIN1_ARTIFACT_CODEPOINTS):
        return True
    known_bad_fragments = (
        "?쒓",
        "?먮",
        "?꾨",
        "?섏",
        "?댁",
        "吏",
        "湲",
        "怨",
        "蹂",
        "諛",
        "媛",
        "瑜",
        "濡",
    )
    if any(fragment in markdown for fragment in known_bad_fragments):
        return True
    cjk_count = sum(1 for char in markdown if "\u4e00" <= char <= "\u9fff")
    suspicious_question_count = len(re.findall(r"\?[^\s\n]{1,8}", markdown))
    return cjk_count >= 3 or suspicious_question_count >= 5


def evaluate_content_first_wiki_article(markdown: str, *, path_hint: str = "") -> dict[str, Any]:
    artifact_kind = classify_wiki_artifact(markdown, path_hint=path_hint)
    score = 0
    blockers: list[str] = []
    reason_codes: list[str] = []

    def add(condition: bool, points: int, pass_code: str, fail_code: str) -> None:
        nonlocal score
        if condition:
            score += points
            reason_codes.append(pass_code)
        else:
            blockers.append(fail_code)

    lower = markdown.lower()
    body_before_appendix = markdown.partition("## Machine Appendix")[0]
    body_lower = body_before_appendix.lower()
    first_body = _first_content_block(markdown).lower()
    machine_appendix_index = lower.find("## machine appendix")
    missing_groups = [
        group
        for group, candidates in ARTICLE_SECTION_GROUPS.items()
        if not any(candidate in markdown for candidate in candidates)
    ]

    representative_kind = artifact_kind in {"wiki_article", "wiki_article_fixture"}
    add(representative_kind, 10, "artifact_kind_wiki_article", f"artifact_kind:{artifact_kind}")
    add(not has_mojibake(markdown), 10, "no_mojibake", "mojibake_detected")
    add(
        _production_article_path(path_hint) or artifact_kind == "wiki_article_fixture",
        10,
        "production_facing_or_locked_fixture_path",
        "not_production_facing_category_path",
    )
    add(_content_first_opening(first_body), 13, "content_first_opening", "control_or_proof_first_opening")
    add(not missing_groups, 14, "required_section_groups_present", "missing_section_groups:" + ",".join(missing_groups))
    add(_source_synthesis_is_contentful(markdown), 10, "source_synthesis_contentful", "source_synthesis_pointer_only_or_missing")
    add(_has_time_direction(markdown), 10, "time_direction_present", "time_direction_missing")
    add(_related_pages_are_semantic(markdown), 8, "semantic_related_pages", "related_pages_are_internal_ids_or_missing")
    add(_machine_appendix_is_late(markdown, machine_appendix_index), 5, "machine_appendix_late", "machine_appendix_missing_or_too_early")
    add(not any(marker in body_lower for marker in SELF_QUALITY_MARKERS), 5, "no_self_quality_claim", "self_quality_claim_present")
    add(not _has_proof_path_dump(first_body), 5, "mf_safe_user_surface", "proof_or_mailbox_terms_in_opening")
    add(not _has_body_contamination(body_before_appendix), 10, "no_body_contamination", "body_contains_proof_or_storage_self_talk")

    verdict = "pass" if score >= 90 and not blockers else "fail"
    return {
        "schema_version": "content_first_wiki_article_gate.v1",
        "artifact_kind": artifact_kind,
        "verdict": verdict,
        "score": min(score, 100),
        "raw_score": score,
        "blockers": blockers,
        "reason_codes": reason_codes,
        "path_hint": path_hint,
        "hard_nonclaims": [
            "content_first_gate_is_not_full_production_ready",
            "wiki_article_pass_does_not_prove_mf_recall_or_provider_rejudgment",
            "guard_card_or_category_index_must_not_be_representative_article",
        ],
    }


def audit_content_first_wiki_artifacts(paths: Iterable[Path]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in paths:
        markdown = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        result = evaluate_content_first_wiki_article(markdown, path_hint=str(path))
        result["path"] = str(path)
        results.append(result)
    return results


def _first_content_block(markdown: str) -> str:
    without_frontmatter = re.sub(r"\A---\n.*?\n---\n", "", markdown, flags=re.DOTALL)
    return without_frontmatter[:2400]


def _frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", markdown, flags=re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _is_locked_fixture(frontmatter: dict[str, str]) -> bool:
    return frontmatter.get("status") == LOCKED_FIXTURE_STATUS and bool(frontmatter.get("fixture_id"))


def _is_representative_article(frontmatter: dict[str, str]) -> bool:
    return (
        frontmatter.get("schema_version") == REPRESENTATIVE_SCHEMA_VERSION
        and frontmatter.get("article_role") == REPRESENTATIVE_ARTICLE_ROLE
    )


def _looks_like_article(markdown: str) -> bool:
    present_groups = sum(
        any(candidate in markdown for candidate in candidates)
        for candidates in ARTICLE_SECTION_GROUPS.values()
    )
    return present_groups >= 5


def _production_article_path(path_hint: str) -> bool:
    normalized = path_hint.replace("\\", "/").lower()
    return "/categories/" in normalized and not normalized.endswith("/agents.md")


def _content_first_opening(first_body: str) -> bool:
    if any(marker in first_body for marker in CONTROL_OPENING_MARKERS):
        return False
    if _has_proof_path_dump(first_body):
        return False
    return True


def _has_proof_path_dump(text: str) -> bool:
    return bool(PROOF_PATH_DUMP_RE.search(text))


def _has_body_contamination(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered or marker in text for marker in BODY_CONTAMINATION_MARKERS)


def _source_synthesis_is_contentful(markdown: str) -> bool:
    section = _section_text(markdown, "Source Synthesis") or _section_text(markdown, "Source Notes") or _section_text(markdown, "Sources")
    if not section:
        return False
    lowered = section.lower()
    pointer_count = sum(token in lowered for token in ("source_ref", "origin_locator", "provider_source_ref", "hermes-session-json"))
    prose_lines = [
        line.strip()
        for line in section.splitlines()
        if len(line.strip()) >= 40 and not line.strip().startswith(("-", "|", "{", "}", '"'))
    ]
    return bool(prose_lines) and pointer_count < 3


def _has_time_direction(markdown: str) -> bool:
    lowered = markdown.lower()
    return any(
        marker in lowered
        for marker in (
            "how this changed",
            "time direction",
            "decision timeline",
            "log",
            "later turns",
            "earlier turns",
        )
    )


def _related_pages_are_semantic(markdown: str) -> bool:
    section = _section_text(markdown, "Related Pages")
    if not section:
        return False
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("-")]
    if not lines:
        return False
    if any(re.search(r"\bN-[a-f0-9]{8,}\b", line) for line in lines):
        return False
    return any(sum(1 for char in line if char.isalnum()) >= 3 for line in lines)


def _machine_appendix_is_late(markdown: str, machine_appendix_index: int) -> bool:
    if machine_appendix_index < 0:
        return False
    preceding_groups = {
        group: candidates
        for group, candidates in ARTICLE_SECTION_GROUPS.items()
        if group != "appendix"
    }
    return all(
        any(
            (index := markdown.find(section)) >= 0 and index < machine_appendix_index
            for section in candidates
        )
        for candidates in preceding_groups.values()
    )


def _section_text(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_match = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(markdown)
    return markdown[match.end() : end].strip()


__all__ = [
    "audit_content_first_wiki_artifacts",
    "classify_wiki_artifact",
    "evaluate_content_first_wiki_article",
    "has_mojibake",
]
