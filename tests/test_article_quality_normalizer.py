from __future__ import annotations

import json

from runtime.wiki.article_quality_normalizer import normalize_active_wiki_article


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
