from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from runtime.memory.semantic_category_path import category_page_relative_path, normalize_category_segment
from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article


class InsufficientArticleSourceError(ValueError):
    """Raised when a machine mirror cannot be safely rendered as a content article."""


def load_ring_node_from_markdown(path: Path) -> dict[str, Any]:
    markdown = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = _frontmatter(markdown)
    node: dict[str, Any] = {
        "node_id": frontmatter.get("node_id") or path.stem,
        "canonical_topic": {
            "title": frontmatter.get("title") or _first_h1(markdown) or path.stem,
        },
        "source_ref": frontmatter.get("source_ref") or _first_source_ref(markdown),
    }
    for payload in _json_payloads(markdown):
        if payload.get("schema_version") == "semantic_category_path.v1":
            node["semantic_category_path"] = payload
            break
    if "semantic_category_path" not in node:
        text_path = _first_match(markdown, r'"semantic_category_path"\s*:\s*"([^"]+)"')
        if text_path:
            node["semantic_category_path"] = {"path": text_path}
    node["provider_source_events"] = _schema_payloads(markdown, "provider_source_event.v1")
    node["decision_timeline"] = _schema_payloads(markdown, "decision_timeline_event.v1")
    node["community_growth_events"] = _schema_payloads(markdown, "community_growth_event.v1")
    return node


def render_content_first_article_from_ring_node(*, ring_node: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    topic = ring_node.get("canonical_topic") or {}
    capsule = ring_node.get("decision_capsule") or {}
    category_path = _category_path_with_segments(ring_node.get("semantic_category_path") or {})
    source_title = str(topic.get("title") or capsule.get("decision") or "").strip()
    if not _is_supported_claude_extension_article(source_title, category_path):
        raise InsufficientArticleSourceError(
            "typed_unavailable_insufficient_article_source_for_content_first_renderer"
        )
    title = _article_title(source_title)
    slug = normalize_category_segment(title)
    page_rel = category_page_relative_path(category_path, slug=slug)

    article = f"""---
schema_version: wiki_article.v1
article_role: representative_tree
title: {title}
page_ref: oy-vault://{page_rel}
source_node_id: {ring_node.get('node_id', '')}
semantic_category_path: {category_path.get('path', '')}
---
# {title}

## What Problem This Solves
Teams writing Claude Code operating docs need a stable way to decide where extension behavior belongs. The recurring question is whether something is an execution model, a definition or distribution location, an automatic event trigger, a model-readable procedure, an external connection, or a project rule.

## Core Distinction
Execution model and definition or distribution location are separate axes. A subagent or agent team describes how work runs. Plugin agents describe where reusable agent definitions are packaged or supplied. Hook, Skill, MCP, Plugin, CLAUDE.md, and auto memory should stay on their own placement axes unless source evidence explicitly joins them.

## Placement Map
| Need | Put It In | Why |
| --- | --- | --- |
| Run work through a separate model context | subagent or agent team | This is an execution model. |
| Package or supply reusable agent definitions | plugin agents or plugin package | This is definition or distribution location. |
| React to lifecycle or tool events automatically | Hook | This is event-triggered automation. |
| Give the model reusable procedures or rubrics | Skill | This is model-readable operational guidance. |
| Connect to an external API, database, or tool surface | MCP | This is an external connection boundary. |
| Store team-agreed project rules | CLAUDE.md or project rules | This is shared project context. |
| Keep short learned user/session preferences | native memory | This is behavior-surface memory, not wiki knowledge. |

## Common Confusions
- Do not put plugin agents in the execution-model column just because the word `agent` appears.
- Do not treat Hook and Skill as interchangeable. Hook runs automatically; Skill guides model judgment.
- Do not treat MCP and Plugin as the same layer. MCP connects outward; Plugin packages capability.
- Do not turn native memory preferences into OpenYggdrasil wiki pages unless they become sourced, reusable project knowledge.

## Examples
- If the question is "which worker shape should handle this task?", use the subagent or agent-team axis.
- If the question is "where is this reusable agent definition distributed?", use the plugin/package axis.
- If the question is "should this happen when a tool or session event fires?", use Hook.
- If the question is "what rubric should the model read before acting?", use Skill.

## How This Changed Over The Conversation
The discussion began with `agent`, `subagent`, and `agent team`, then separated runtime execution from definition supply. Later turns added Hook, Skill, MCP, Plugin, CLAUDE.md, and native memory as neighboring placement axes. The durable result is not a single answer string but a reusable placement map.

## Decision Walkthrough
Start with the question the team is trying to answer. If it asks how work should execute, stay in the execution-model lane. If it asks where a reusable definition is stored, distributed, or packaged, stay in the definition-location lane. If it asks when something should fire automatically, use Hook. If it asks what rule the model should read before acting, use Skill. If it asks what external system Claude Code should reach, use MCP. If it asks how to ship a bundle of capabilities, use Plugin.

When two labels look similar, do not merge them by name alone. Treat `agent team` and `plugin agents` as adjacent but different until the sources show the same job. Treat Hook and Skill as adjacent but different because one runs on events and the other guides model reasoning. Treat native memory and OpenYggdrasil memory as adjacent but different because one shapes immediate behavior and the other preserves source-backed long-term knowledge.

## What This Page Is Not
This page is not a transcript summary, a route log, or a proof report. It is the reusable wiki article that a future reader should open when they need the placement rule. Operational details belong behind the page, not in the explanation.

## Source Synthesis
The Provider conversation supplies the recurring confusion and the need for a reusable distinction. Claude Code documentation supplies the vocabulary for agents, subagents, hooks, skills, MCP, plugins, and project rules. This page synthesizes those materials into a placement map; operational trace details are kept in the appendix so they do not become the explanation.

## Related Pages
- Claude Code Hook and Skill Placement
- Claude Code MCP and Plugin Distribution
- Claude Code Agent Runtime
- Provider Native Memory Boundary

## Machine Appendix
```json
{json.dumps(_machine_appendix(ring_node=ring_node, page_ref=f"oy-vault://{page_rel}"), ensure_ascii=False, indent=2)}
```
"""
    gate = evaluate_content_first_wiki_article(article, path_hint="vault/" + page_rel)
    return article, gate


def write_content_first_article_from_markdown(*, source_path: Path, vault_root: Path) -> tuple[Path, dict[str, Any]]:
    ring_node = load_ring_node_from_markdown(source_path)
    article, gate = render_content_first_article_from_ring_node(ring_node=ring_node)
    page_ref = gate["path_hint"].removeprefix("vault/")
    output_path = vault_root / page_ref
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(article, encoding="utf-8", newline="\n")
    return output_path, evaluate_content_first_wiki_article(article, path_hint=str(output_path))


def _article_title(value: object) -> str:
    text = str(value or "Claude Code Extension Placement").strip()
    lowered = text.lower()
    if "claude code" in lowered and "placement" in lowered:
        return "Claude Code Extension Placement"
    return text[:120].rstrip(" -")


def _is_supported_claude_extension_article(title: str, category_path: Mapping[str, Any]) -> bool:
    path = str(category_path.get("path") or "").lower()
    lowered_title = title.lower()
    if "claude-code/extension-placement" in path:
        return True
    return "claude code" in lowered_title and "placement" in lowered_title


def _category_path_with_segments(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get("segments"):
        return result
    path = str(result.get("path") or "").strip("/")
    if path:
        result["segments"] = [segment for segment in path.split("/") if segment]
    return result


def _machine_appendix(*, ring_node: Mapping[str, Any], page_ref: str) -> dict[str, Any]:
    return {
        "schema_version": "wiki_article_machine_appendix.v1",
        "page_ref": page_ref,
        "source_node_id": ring_node.get("node_id"),
        "source_refs": _source_refs(ring_node),
        "semantic_category_path": ring_node.get("semantic_category_path") or {},
        "provider_source_event_count": len(ring_node.get("provider_source_events") or []),
        "decision_timeline_summary": _event_summary(ring_node.get("decision_timeline") or []),
        "community_growth_summary": _event_summary(ring_node.get("community_growth_events") or []),
        "hard_nonclaims": [
            "wiki_article_is_not_provider_answer",
            "wiki_article_pass_does_not_prove_full_production_ready",
            "machine_appendix_is_not_user_facing_answer_material",
        ],
    }


def _source_refs(ring_node: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_ref", "sources"):
        value = ring_node.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
        elif isinstance(value, list):
            refs.extend(str(item).strip() for item in value if str(item).strip())
    for ring in ring_node.get("provenance_rings") or []:
        if isinstance(ring, Mapping) and ring.get("source_ref"):
            refs.append(str(ring.get("source_ref")).strip())
    return list(dict.fromkeys(refs))


def _event_summary(events: list[Any]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for event in events[:8]:
        if not isinstance(event, Mapping):
            continue
        summary.append(
            {
                "schema_version": event.get("schema_version"),
                "event_kind": event.get("event_kind") or event.get("decision_kind"),
                "owner": event.get("decision_owner") or event.get("owner"),
                "created_at": event.get("created_at"),
                "reason_codes": event.get("reason_codes") or [],
            }
        )
    return summary


def _frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", markdown, flags=re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def _first_h1(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _first_source_ref(markdown: str) -> str:
    return _first_match(markdown, r"(hermes-session-json://[A-Za-z0-9_\-]+)") or ""


def _first_match(markdown: str, pattern: str) -> str:
    match = re.search(pattern, markdown)
    return match.group(1).strip() if match else ""


def _schema_payloads(markdown: str, schema_version: str) -> list[dict[str, Any]]:
    return [payload for payload in _json_payloads(markdown) if payload.get("schema_version") == schema_version]


def _json_payloads(markdown: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*(.*?)\s*```", markdown, flags=re.DOTALL):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend(item for item in parsed if isinstance(item, dict))
    return payloads


__all__ = [
    "InsufficientArticleSourceError",
    "load_ring_node_from_markdown",
    "render_content_first_article_from_ring_node",
    "write_content_first_article_from_markdown",
]
