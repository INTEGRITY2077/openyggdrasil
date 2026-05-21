from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article, has_mojibake


def _u(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


BEST_CASE_SECTION_GROUPS = {
    "summary": (_u("## \\ud575\\uc2ec \\uc694\\uc57d"), "## What This Page Explains", "## What This Page Decides"),
    "durability": (
        _u("## \\uc65c \\uc774 \\uc8fc\\uc81c\\uac00 \\uc7a5\\uae30 \\uc9c0\\uc2dd\\uc778\\uac00"),
        "## Why This Becomes Durable Knowledge",
        "## Why It Matters",
    ),
    "ontology": (_u("## \\uc628\\ud1a8\\ub85c\\uc9c0 \\uc704\\uce58"), "## Ontology Position"),
    "decision_path": (_u("## \\ud310\\ub2e8 \\uacbd\\ub85c"), "## Decision Path"),
    "confusions": (_u("## \\uc790\\uc8fc \\ud5f7\\uac08\\ub9ac\\ub294 \\uc9c0\\uc810"), "## Common Confusions", "## Failure Cases"),
    "examples": (_u("## \\uc608\\uc2dc"), "## Examples"),
    "time": (_u("## \\uc2dc\\uac04\\uc5d0 \\ub530\\ub978 \\ud310\\ub2e8 \\ubcc0\\ud654"), "## How This Changed Over Time"),
    "community": ("## Community Growth Notes", _u("## \\ucee4\\ubba4\\ub2c8\\ud2f0 \\uc131\\uc7a5 \\uae30\\ub85d")),
    "sources": ("## Source Synthesis", "## Sources"),
    "related": ("## Related Pages",),
    "open_questions": ("## Open Questions", _u("## \\uc5f4\\ub9b0 \\uc9c8\\ubb38")),
    "maintenance": ("## Maintenance Notes", _u("## \\uc720\\uc9c0\\ubcf4\\uc218 \\uba54\\ubaa8")),
    "appendix": ("## Machine Appendix",),
}

ONTOLOGY_LAYER_TERMS = (
    "Continent",
    "Mountain",
    "Forest",
    "Tree",
    "Branch",
    "Leaf",
    "Chloroplast",
)

PROPER_NOUN_TERMS = (
    "Claude Code",
    "Agent",
    "Hook",
    "Skill",
    "MCP",
    "Plugin",
    "CLAUDE.md",
    "OpenYggdrasil",
    "Hermes",
)


def evaluate_best_case_mock_alignment(markdown: str, *, path_hint: str = "") -> dict[str, Any]:
    base_gate = evaluate_content_first_wiki_article(markdown, path_hint=path_hint)
    score = 0
    blockers: list[str] = []
    reason_codes: list[str] = []

    def add(condition: bool, points: int, pass_code: str, fail_code: str, *, hard: bool = False) -> None:
        nonlocal score
        if condition:
            score += points
            reason_codes.append(pass_code)
        else:
            blockers.append(fail_code)
            if hard:
                blockers.append("hard:" + fail_code)

    before_appendix = markdown.split("## Machine Appendix", 1)[0]
    missing_sections = [
        name
        for name, candidates in BEST_CASE_SECTION_GROUPS.items()
        if not any(candidate in markdown for candidate in candidates)
    ]

    add(base_gate["verdict"] == "pass", 8, "base_content_first_gate_pass", "base_content_first_gate_fail", hard=True)
    add(not has_mojibake(markdown), 8, "no_mojibake", "mojibake_detected", hard=True)
    add(_has_korean_context(before_appendix), 10, "korean_context_present", "korean_context_too_weak")
    add(_proper_nouns_preserved(markdown), 5, "english_proper_nouns_preserved", "english_proper_nouns_missing")
    add(not missing_sections, 12, "best_case_sections_present", "missing_best_case_sections:" + ",".join(missing_sections))
    add(_ontology_layers_present(markdown), 10, "continent_to_chloroplast_layers_present", "ontology_layers_missing")
    add(_time_direction_rich(markdown), 8, "time_direction_rich", "time_direction_too_shallow")
    add(_source_synthesis_rich(markdown), 8, "source_synthesis_rich", "source_synthesis_too_shallow")
    add(_community_growth_signal(markdown), 7, "community_growth_signal_present", "community_growth_signal_missing")
    add(_open_questions_actionable(markdown), 5, "open_questions_actionable", "open_questions_missing_or_thin")
    add(_maintenance_notes_actionable(markdown), 5, "maintenance_notes_actionable", "maintenance_notes_missing_or_thin")
    add(_no_proof_terms_before_appendix(before_appendix), 9, "proof_terms_absent_before_appendix", "proof_terms_before_appendix")
    add(_machine_appendix_late(markdown), 5, "machine_appendix_late", "machine_appendix_missing_or_early")

    hard_failure = any(item.startswith("hard:") for item in blockers)
    verdict = "pass" if score >= 90 and not hard_failure and not missing_sections and not blockers else "fail"
    return {
        "schema_version": "best_case_mock_alignment_gate.v1",
        "verdict": verdict,
        "score": min(score, 100),
        "raw_score": score,
        "blockers": blockers,
        "reason_codes": reason_codes,
        "base_gate": base_gate,
        "path_hint": path_hint,
        "hard_nonclaims": [
            "best_case_alignment_is_not_full_production_ready",
            "one_article_alignment_does_not_prove_full_vault_quality",
            "alignment_gate_does_not_prove_live_mf_recall_or_provider_rejudgment",
        ],
    }


def audit_best_case_alignment(paths: list[Path]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in paths:
        markdown = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        result = evaluate_best_case_mock_alignment(markdown, path_hint=str(path))
        result["path"] = str(path)
        results.append(result)
    return results


def _has_korean_context(markdown: str) -> bool:
    hangul_count = sum(1 for char in markdown if 0xAC00 <= ord(char) <= 0xD7A3)
    cjk_count = sum(1 for char in markdown if 0x4E00 <= ord(char) <= 0x9FFF)
    reader_prose_lines = _prose_lines(markdown)
    return (hangul_count >= 600 and cjk_count <= 2) or len(reader_prose_lines) >= 45


def _proper_nouns_preserved(markdown: str) -> bool:
    if "Domestic Dog Ecology" in markdown:
        return all(term in markdown for term in ("Domestic Dog Ecology", "Canid", "Urban Animal Ecology"))
    title = _first_title(markdown)
    title_terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,}", title)
        if term.lower() not in {"the", "and", "for", "with", "from", "this", "page"}
    ]
    if title_terms:
        preserved = sum(term in markdown for term in title_terms)
        return preserved >= max(2, min(len(title_terms), 4))
    return sum(term in markdown for term in PROPER_NOUN_TERMS) >= 4


def _ontology_layers_present(markdown: str) -> bool:
    return all(term in markdown for term in ONTOLOGY_LAYER_TERMS)


def _time_direction_rich(markdown: str) -> bool:
    section = _section_text(markdown, _u("\\uc2dc\\uac04\\uc5d0 \\ub530\\ub978 \\ud310\\ub2e8 \\ubcc0\\ud654")) or _section_text(markdown, "How This Changed Over Time")
    markers = (
        _u("\\ucd08\\uae30"),
        _u("\\uc911\\ubc18"),
        _u("\\ud6c4\\ubc18"),
        "early",
        "middle",
        "later",
        "earlier",
        _u("\\ub2e4\\uc74c"),
    )
    return bool(section) and sum(marker.lower() in section.lower() for marker in markers) >= 3 and len(_bullet_lines(section)) >= 3


def _source_synthesis_rich(markdown: str) -> bool:
    section = _section_text(markdown, "Source Synthesis")
    lowered = section.lower()
    has_source_roles = sum(term in lowered for term in ("conversation", "documentation", "notes", "raw", "source"))
    return bool(section) and has_source_roles >= 2 and len(_prose_lines(section)) >= 3


def _community_growth_signal(markdown: str) -> bool:
    section = _section_text(markdown, "Community Growth Notes") or _section_text(markdown, _u("\\ucee4\\ubba4\\ub2c8\\ud2f0 \\uc131\\uc7a5 \\uae30\\ub85d"))
    lowered = section.lower()
    return (
        bool(section)
        and ("community" in lowered or "sibling" in lowered)
        and (_u("\\uc2dc\\uac04\\ucc28") in section or "discontinuous" in lowered)
        and ("attach" in lowered or "split" in lowered or _u("\\ubd84\\ub9ac") in section)
    )


def _open_questions_actionable(markdown: str) -> bool:
    section = _section_text(markdown, "Open Questions") or _section_text(markdown, _u("\\uc5f4\\ub9b0 \\uc9c8\\ubb38"))
    return len(_bullet_lines(section)) >= 3


def _maintenance_notes_actionable(markdown: str) -> bool:
    section = _section_text(markdown, "Maintenance Notes") or _section_text(markdown, _u("\\uc720\\uc9c0\\ubcf4\\uc218 \\uba54\\ubaa8"))
    lowered = section.lower()
    has_actions = sum(term in lowered for term in ("stale", "split", "merge", "tombstone", "lint", "repair"))
    enough_shape = len(_bullet_lines(section)) >= 3 or len(_prose_lines(section)) >= 2
    return enough_shape and has_actions >= 2


def _no_proof_terms_before_appendix(markdown: str) -> bool:
    lowered = markdown.lower()
    return not re.search(
        r"\b(receipt|work_order|mail_id|produced_count|source_ref_status|quality_assessment)\s*[:=]"
        r"|\b(work_order|mail_id)[_-]id\b",
        lowered,
    )


def _machine_appendix_late(markdown: str) -> bool:
    index = markdown.lower().find("## machine appendix")
    if index < 0:
        return False
    required_preceding = (
        "## What This Page Decides",
        "## Ontology Position",
        "## Decision Path",
        "## Source Synthesis",
        "## Maintenance Notes",
    )
    return all(markdown.find(heading) >= 0 and markdown.find(heading) < index for heading in required_preceding)


def _section_text(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_match = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(markdown)
    return markdown[match.end() : end].strip()


def _first_title(markdown: str) -> str:
    frontmatter_match = re.search(r"^title:\s*(.+)$", markdown, flags=re.MULTILINE)
    if frontmatter_match:
        return frontmatter_match.group(1).strip().strip('"')
    h1_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return h1_match.group(1).strip() if h1_match else ""


def _bullet_lines(section: str) -> list[str]:
    return [line.strip() for line in section.splitlines() if line.strip().startswith(("-", "*", "1.", "2.", "3.", "4."))]


def _prose_lines(section: str) -> list[str]:
    return [
        line.strip()
        for line in section.splitlines()
        if len(line.strip()) >= 45 and not line.strip().startswith(("-", "|", "{", "}", '"'))
    ]


__all__ = ["audit_best_case_alignment", "evaluate_best_case_mock_alignment"]
