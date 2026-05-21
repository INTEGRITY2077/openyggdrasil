from __future__ import annotations

import json

from runtime.wiki.article_quality_normalizer import normalize_active_wiki_article, normalize_safe_cursor_articles
from runtime.wiki.best_case_alignment_gate import evaluate_best_case_mock_alignment
from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article, has_mojibake


def test_normalizer_repairs_active_article_without_domain_hardcoding() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
status: ACTIVE
title: Domestic Dog Ecology
root_claim: Domestic Dog Ecology explains dogs in human environments.
page_ref: oy-vault://categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md
semantic_category_path: biology/animal-ecology/domestic-dogs
source_ref: hermes-session-json://dog-test
message_index_range: 10..14
anchor_hash: abc123
confidence: 0.88
hard_nonclaims: [not_live_full_production_ready]
---
# Domestic Dog Ecology

## What This Page Is
Domestic Dog Ecology explains walking, sniffing, routine, and stress in human-managed environments.

## Why It Matters
The same conversation can drift into welfare, wildlife, or veterinary topics.

## Operating Rule
Use this page for ordinary dog ecology; split welfare and urban wildlife questions.

## Source Synthesis
- source_ref `hermes-session-json://dog-test` resolved with message_index_range `10..14`.
- The source is enough because it contains the whole proof.

## Related Pages
- claim:N-abc123 and ring-abc
- [[Urban Animal Ecology]]

## Data Gaps
- This is not production-ready.

## Machine Appendix
{}
"""

    repaired, gate = normalize_active_wiki_article(
        markdown,
        path_hint="vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
        run_id="unit-normalizer",
    )

    assert gate["verdict"] == "pass"
    body = repaired.partition("## Machine Appendix")[0].lower()
    assert "production-ready" not in body
    assert "receipt" not in body
    assert "source_ref" not in body
    assert "message_index_range" not in body
    assert "hard_nonclaims" not in body
    assert "claim:n-" not in body
    assert "## examples" in body
    assert "## how this changed" in body
    assert "earlier turns" in body
    assert "Urban Animal Ecology" in repaired
    assert "??" not in repaired

    best_case = evaluate_best_case_mock_alignment(
        repaired,
        path_hint="vault/categories/biology/animal-ecology/domestic-dogs/domestic-dog-ecology.md",
    )
    assert best_case["verdict"] == "pass"
    assert "Continent" in repaired
    assert "Mountain" in repaired
    assert "Forest" in repaired
    assert "Tree" in repaired
    assert "Branch" in repaired
    assert "Leaf" in repaired
    assert "Chloroplast" in repaired


def test_normalizer_records_source_lineage_in_machine_appendix() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
title: Claude Code Extension Placement
root_claim: Extension placement separates Hook, Skill, MCP, and Plugin.
page_ref: oy-vault://categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-extension-placement-criteria.md
semantic_category_path: software-development/claude-code/extension-placement/hooks-skills-mcp-plugins
source_ref: hermes-session-json://claude-test
message_index_range: 1..8
anchor_hash: def456
reason_codes: ['source_ref_resolved']
---
# Claude Code Extension Placement

## What Problem This Solves
Teams need to place extension behavior without mixing runtime, packaging, and rules.

## Core Distinction
Hook is automatic event behavior, Skill is model-readable procedure, MCP is external connection, and Plugin is distribution.

## Related Pages
- Claude Code Agent Runtime

## Machine Appendix
{}
"""

    repaired, gate = normalize_active_wiki_article(
        markdown,
        path_hint="vault/categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-extension-placement-criteria.md",
        run_id="unit-normalizer",
    )

    assert gate["verdict"] == "pass"
    appendix_raw = repaired.split("```json", 1)[1].split("```", 1)[0]
    appendix = json.loads(appendix_raw)
    assert appendix["source_ref"] == "hermes-session-json://claude-test"
    assert appendix["message_index_range"] == "1..8"
    assert appendix["anchor_hash"] == "def456"
    assert appendix["repair"]["run_id"] == "unit-normalizer"
    assert appendix["lineage_contracts"]["provider_source_event"]["schema_version"] == "provider_source_event.v1"
    assert appendix["lineage_contracts"]["decision_timeline_event"]["schema_version"] == "decision_timeline_event.v1"
    assert appendix["lineage_contracts"]["semantic_category_path"]["schema_version"] == "semantic_category_path.v1"
    assert appendix["lineage_contracts"]["community_growth_event"]["schema_version"] == "community_growth_event.v1"
    assert appendix["lineage_contracts"]["wiki_continent_page"]["schema_version"] == "wiki_continent_page.v1"
    assert "C:/" not in appendix["original_path_hint"]


def test_normalizer_best_case_gate_generalizes_to_memory_system_article() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
title: Provider Durable Reuse Boundary
root_claim: Provider should trigger long-term memory only for reusable sourced knowledge.
page_ref: oy-vault://categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md
semantic_category_path: memory-systems/openyggdrasil/wiki-ring
source_ref: hermes-session-json://memory-test
message_index_range: 20..24
anchor_hash: abc789
---
# Provider Durable Reuse Boundary

## What This Page Is
This page records when Provider should ask for long-term memory support.

## Operating Rule
Use only for reusable, sourced, non-preference knowledge.

## Source Synthesis
The operation notes and conversation source define the boundary.

## Related Pages
- [[OpenYggdrasil Memory Community]]

## Machine Appendix
{}
"""

    repaired, gate = normalize_active_wiki_article(
        markdown,
        path_hint="vault/categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md",
        run_id="unit-normalizer",
    )

    best_case = evaluate_best_case_mock_alignment(
        repaired,
        path_hint="vault/categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md",
    )

    assert gate["verdict"] == "pass"
    assert best_case["verdict"] == "pass"
    assert "Canid" not in repaired
    assert "??" not in repaired


def test_safe_cursor_normalizer_skips_guard_card_without_counting_as_failed(tmp_path) -> None:
    vault = tmp_path
    (vault / "_meta").mkdir(parents=True)
    (vault / "categories" / "software-development" / "claude-code").mkdir(parents=True)
    guard = vault / "categories" / "software-development" / "claude-code" / "agents.md"
    guard.write_text(
        """---
id: N-guard
title: Claude Code agent and extension placement boundary
semantic_category_path: software-development/claude-code/extension-placement/agents
---
# Claude Code agent and extension placement boundary

## What This Page Is
This is the production-facing wiki page for a source-backed OpenYggdrasil memory.

## Maintenance Notes
- quality_verdict: pass
""",
        encoding="utf-8",
    )
    (vault / "_meta" / "safe_index_cursor.json").write_text(
        """{
  "schema_version": "safe_index_cursor.v1",
  "cursor_id": "cursor-test",
  "source": "unit",
  "committed_paths": ["vault/categories/software-development/claude-code/agents.md"]
}
""",
        encoding="utf-8",
    )

    receipt = normalize_safe_cursor_articles(vault, run_id="unit-skip-guard")

    assert receipt["repaired_count"] == 0
    assert receipt["failed_count"] == 0
    assert receipt["skipped_count"] == 1
    assert receipt["skipped"][0]["artifact_kind"] == "retrieval_guard_card"


def test_generic_production_facing_scaffold_is_not_article_body() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
status: ACTIVE
title: Claude Code Hook Boundary
root_claim: This is a production-facing wiki continent page.
page_ref: oy-vault://categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-hook-boundary.md
semantic_category_path: software-development/claude-code/extension-placement/hooks-skills-mcp-plugins
---
# Claude Code Hook Boundary

## What This Page Decides
This is a production-facing wiki continent page. It groups safe-indexed OpenYggdrasil memories by semantic category instead of exposing internal hash filenames.

## Operating Rule
Hook belongs to automatic event behavior.

## Source Synthesis
The source explains Hook placement in Claude Code documentation.

## Related Pages
- Claude Code Skill Boundary

## How This Changed Over Time
- Early: the boundary was first captured.
- Middle: the category was attached.
- Later: the page stayed active.

## Examples
- Use this page for Hook placement.

## Maintenance Notes
- Run lint before final support.

## Machine Appendix
{}
"""

    result = evaluate_content_first_wiki_article(
        markdown,
        path_hint="vault/categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-hook-boundary.md",
    )

    assert result["verdict"] == "fail"
    assert "body_contains_proof_or_storage_self_talk" in result["blockers"]


def test_normalizer_replaces_generic_page_scaffold_root_claim() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
title: Claude Code Hook and Slash Command Placement Boundary
root_claim: This is a production-facing wiki continent page.
page_ref: oy-vault://categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-hook-and-slash-command-placement-boundary.md
semantic_category_path: software-development/claude-code/extension-placement/hooks-skills-mcp-plugins
---
# Claude Code Hook and Slash Command Placement Boundary

## What This Page Is
This is a production-facing wiki continent page. It groups safe-indexed OpenYggdrasil memories by semantic category instead of exposing internal hash filenames.

## Operating Rule
Put automatic lifecycle behavior in Hook and model-readable procedures in Skill.

## Source Synthesis
The source explains Hook placement and slash command placement as separate operational surfaces.

## Related Pages
- Claude Code Skill Boundary

## Machine Appendix
{}
"""

    repaired, gate = normalize_active_wiki_article(
        markdown,
        path_hint="vault/categories/software-development/claude-code/extension-placement/hooks-skills-mcp-plugins/claude-code-hook-and-slash-command-placement-boundary.md",
        run_id="unit-normalizer",
    )

    assert gate["verdict"] == "pass"
    body = repaired.partition("## Machine Appendix")[0].lower()
    assert "this is a production-facing wiki continent page" not in body
    assert 'root_claim: "This is a production-facing wiki continent page.' not in repaired
    assert "Claude Code Hook and Slash Command Placement Boundary preserves the reusable boundary" in repaired


def test_normalizer_preserves_existing_machine_appendix_lineage() -> None:
    markdown = """---
schema_version: wiki_article.v1
article_role: representative_tree
title: Provider Durable Reuse Boundary
root_claim: Provider should trigger long-term memory only for reusable sourced knowledge.
page_ref: oy-vault://categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md
semantic_category_path: memory-systems/openyggdrasil/wiki-ring
---
# Provider Durable Reuse Boundary

## What This Page Is
This page records when Provider should ask for long-term memory support.

## Why It Matters
Provider should not become a wiki maintainer.

## Operating Rule
Use only for reusable, sourced, non-preference knowledge.

## Machine Appendix
```json
{
  "source_ref": "hermes-session-json://appendix-only",
  "message_index_range": "20..24",
  "anchor_hash": "abc789",
  "reason_codes": ["appendix_lineage"]
}
```
"""

    repaired, gate = normalize_active_wiki_article(
        markdown,
        path_hint="vault/categories/memory-systems/openyggdrasil/wiki-ring/provider-durable-reuse-boundary.md",
        run_id="unit-normalizer",
    )

    assert gate["verdict"] == "pass"
    appendix_raw = repaired.split("```json", 1)[1].split("```", 1)[0]
    appendix = json.loads(appendix_raw)
    assert appendix["source_ref"] == "hermes-session-json://appendix-only"
    assert appendix["message_index_range"] == "20..24"
    assert appendix["anchor_hash"] == "abc789"
    assert appendix["reason_codes"] == ["appendix_lineage"]


def test_mojibake_detector_rejects_garbled_korean_fragments() -> None:
    garbled = (
        "## What This Page Decides\n"
        "한국어 맥락처럼 보여도 ?쒓뎅??留λ씫 과 ?먮떒 같은 깨진 조각이 "
        "본문에 섞이면 wiki article 품질 gate를 통과하면 안 됩니다."
    )

    assert has_mojibake(garbled)
