from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from harness_common import DEFAULT_VAULT
from episode_semantic_edges import evaluate_episode_semantic_edges
from map_identity import build_claim_id


PROVENANCE_ROOT = DEFAULT_VAULT / "_meta" / "provenance"


def provenance_relative_path(*, topic_id: str) -> str:
    topic_key = topic_id.split(":", 1)[1]
    return f"_meta/provenance/{topic_key}.md"


def _replace_or_add_frontmatter_line(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^(?P<indent>\s*){re.escape(key)}:\s*.*$", flags=re.MULTILINE)
    replacement = f"{key}: {value}"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if text.startswith("---\n"):
        return text.replace("---\n", f"---\n{replacement}\n", 1)
    return text


def _merge_sources_line(text: str, source_rel: str) -> str:
    match = re.search(r"^sources:\s*\[(?P<body>[^\]]*)\]\s*$", text, flags=re.MULTILINE)
    if not match:
        return _replace_or_add_frontmatter_line(text, "sources", f"[{source_rel}]")
    items = [item.strip() for item in match.group("body").split(",") if item.strip()]
    if source_rel not in items:
        items.append(source_rel)
    merged = f"sources: [{', '.join(items)}]"
    return text[: match.start()] + merged + text[match.end() :]


def parse_provenance_records(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"<!-- provenance:(?P<episode_id>[^:]+:[^:]+:[^:]+):start -->\s*"
        r"## Episode [^\n]+\s*"
        r"```json\s*(?P<payload>\{.*?\})\s*```"
        r"\s*<!-- provenance:(?P=episode_id):end -->",
        flags=re.DOTALL,
    )
    rows: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        payload = json.loads(match.group("payload"))
        rows.append(payload)
    return rows


def _record_block(record: Mapping[str, Any]) -> str:
    episode_id = str(record["episode_id"])
    episode_label = episode_id.split(":")[-1]
    return (
        f"<!-- provenance:{episode_id}:start -->\n"
        f"## Episode {episode_label}\n\n"
        "```json\n"
        f"{json.dumps(dict(record), ensure_ascii=False, indent=2)}\n"
        "```\n"
        f"<!-- provenance:{episode_id}:end -->\n"
    )


def _replace_or_append_record(text: str, *, record: Mapping[str, Any]) -> str:
    episode_id = str(record["episode_id"])
    pattern = re.compile(
        rf"<!-- provenance:{re.escape(episode_id)}:start -->.*?<!-- provenance:{re.escape(episode_id)}:end -->\n?",
        flags=re.DOTALL,
    )
    block = _record_block(record)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    marker = "## Episodes\n\n"
    if marker not in text:
        return text.rstrip() + "\n\n## Episodes\n\n" + block
    return text.replace(marker, marker + block + "\n", 1)


def build_episode_provenance_record(
    *,
    placement_verdict: Mapping[str, Any],
    source_rel: str,
    question: str,
    answer: str,
    previous_episode_id: str | None = None,
    next_episode_id: str | None = None,
    supports: list[str] | None = None,
    supersedes: list[str] | None = None,
    contradicts: list[str] | None = None,
) -> dict[str, Any]:
    topic_id = str(placement_verdict["topic_id"])
    episode_id = str(placement_verdict["episode_id"])
    page_id = str(placement_verdict["page_id"])
    claim_id = build_claim_id(topic_id=topic_id, claim_key=f"{episode_id}:summary")
    return {
        "topic_id": topic_id,
        "episode_id": episode_id,
        "claim_id": claim_id,
        "page_id": page_id,
        "belongs_to_topic": topic_id,
        "belongs_to_episode": episode_id,
        "promoted_from": source_rel,
        "derived_from": source_rel,
        "stored_in_page": page_id,
        "previous_episode": previous_episode_id,
        "next_episode": next_episode_id,
        "supports": list(supports or []),
        "supersedes": list(supersedes or []),
        "contradicts": list(contradicts or []),
        "question_summary": " ".join((question or "").split())[:240],
        "answer_summary": " ".join((answer or "").split())[:240],
    }


def render_provenance_page(
    *,
    existing_text: str | None,
    placement_verdict: Mapping[str, Any],
    source_rel: str,
    question: str,
    answer: str,
    created: str,
    edge_evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> str:
    topic_id = str(placement_verdict["topic_id"])
    page_id = str(placement_verdict["page_id"])
    topic_title = str(placement_verdict["topic_title"])
    current_episode_id = str(placement_verdict["episode_id"])

    existing_records = parse_provenance_records(existing_text) if existing_text else []
    existing_by_episode = {str(record["episode_id"]): dict(record) for record in existing_records}
    ordered_episode_ids = sorted(existing_by_episode)

    previous_episode_id = None
    if ordered_episode_ids:
        if current_episode_id in ordered_episode_ids:
            index = ordered_episode_ids.index(current_episode_id)
            if index > 0:
                previous_episode_id = ordered_episode_ids[index - 1]
        else:
            prior_ids = [episode_id for episode_id in ordered_episode_ids if episode_id < current_episode_id]
            if prior_ids:
                previous_episode_id = prior_ids[-1]

    previous_candidates = [existing_by_episode[episode_id] for episode_id in sorted(existing_by_episode)]
    semantic_edges = evaluate_episode_semantic_edges(
        topic_id=topic_id,
        current_question=question,
        current_answer=answer,
        previous_candidates=previous_candidates,
        evaluator=edge_evaluator,
    )

    current_record = build_episode_provenance_record(
        placement_verdict=placement_verdict,
        source_rel=source_rel,
        question=question,
        answer=answer,
        previous_episode_id=previous_episode_id,
        next_episode_id=existing_by_episode.get(current_episode_id, {}).get("next_episode"),
        supports=list(semantic_edges["supports"]),
        supersedes=list(semantic_edges["supersedes"]),
        contradicts=list(semantic_edges["contradicts"]),
    )
    existing_by_episode[current_episode_id] = current_record

    if previous_episode_id and previous_episode_id in existing_by_episode:
        previous_record = dict(existing_by_episode[previous_episode_id])
        previous_record["next_episode"] = current_episode_id
        existing_by_episode[previous_episode_id] = previous_record

    ordered_records = [existing_by_episode[episode_id] for episode_id in sorted(existing_by_episode)]
    provenance_rel = provenance_relative_path(topic_id=topic_id)

    if not existing_text:
        text = (
            "---\n"
            f"title: Provenance {topic_title}\n"
            f"created: {created}\n"
            f"updated: {created}\n"
            "type: summary\n"
            f"topic_id: {topic_id}\n"
            f"page_id: {page_id}\n"
            "tags: [provenance, hermes, topic]\n"
            f"sources: [{source_rel}]\n"
            "---\n\n"
            f"# Provenance {topic_title}\n\n"
            "## Topic\n\n"
            f"- topic_id: `{topic_id}`\n"
            f"- page_id: `{page_id}`\n"
            f"- canonical_page: `queries/{topic_id.split(':', 1)[1]}.md`\n"
            f"- provenance_page: `{provenance_rel}`\n\n"
            "## Episodes\n\n"
        )
    else:
        text = existing_text
        text = _replace_or_add_frontmatter_line(text, "updated", created)
        text = _merge_sources_line(text, source_rel)

    if existing_text:
        for record in ordered_records:
            text = _replace_or_append_record(text, record=record)
        return text

    for record in ordered_records:
        text += _record_block(record)
    return text


def provenance_page_path(*, vault_root: Path, topic_id: str) -> Path:
    return vault_root / provenance_relative_path(topic_id=topic_id)
