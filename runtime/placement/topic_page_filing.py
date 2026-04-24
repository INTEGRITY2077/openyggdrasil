from __future__ import annotations

import re
from typing import Mapping

from common.map_identity import build_claim_id
from provenance.provenance_store import provenance_relative_path

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


def _episode_block(*, placement_verdict: Mapping[str, object], source_rel: str, question: str, answer: str) -> str:
    topic_id = str(placement_verdict["topic_id"])
    episode_id = str(placement_verdict["episode_id"])
    episode_label = episode_id.split(":")[-1]
    session_id = str(placement_verdict["session_id"])
    profile = str(placement_verdict["profile"])
    page_id = str(placement_verdict["page_id"])
    claim_id = build_claim_id(topic_id=topic_id, claim_key=f"{episode_id}:summary")
    provenance_rel = provenance_relative_path(topic_id=topic_id)
    return (
        f"<!-- episode:{episode_id}:start -->\n"
        f"## Episode {episode_label}\n\n"
        f"- session_id: `{session_id}`\n"
        f"- profile: `{profile}`\n"
        f"- claim_id: `{claim_id}`\n"
        f"- topic_id: `{topic_id}`\n"
        f"- page_id: `{page_id}`\n"
        f"- source: `{source_rel}`\n\n"
        f"- provenance_note: `[[{provenance_rel[:-3]}]]`\n\n"
        f"### Question\n\n{question or '(empty question)'}\n\n"
        f"### Answer\n\n{answer or '(no assistant answer found)'}\n\n"
        f"<!-- episode:{episode_id}:end -->\n"
    )


def _replace_or_append_episode(text: str, *, episode_id: str, episode_block: str) -> str:
    pattern = re.compile(
        rf"<!-- episode:{re.escape(episode_id)}:start -->.*?<!-- episode:{re.escape(episode_id)}:end -->\n?",
        flags=re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(episode_block, text, count=1)
    marker = "## Episodes\n\n"
    if marker not in text:
        return text.rstrip() + "\n\n## Episodes\n\n" + episode_block
    return text.replace(marker, marker + episode_block + "\n", 1)


def render_topic_page(
    *,
    existing_text: str | None,
    placement_verdict: Mapping[str, object],
    source_rel: str,
    question: str,
    answer: str,
    created: str,
) -> str:
    topic_title = str(placement_verdict["topic_title"])
    page_id = str(placement_verdict["page_id"])
    topic_id = str(placement_verdict["topic_id"])
    episode_id = str(placement_verdict["episode_id"])
    episode_block = _episode_block(
        placement_verdict=placement_verdict,
        source_rel=source_rel,
        question=question,
        answer=answer,
    )

    if not existing_text:
        text = (
            "---\n"
            f"title: {topic_title}\n"
            f"created: {created}\n"
            f"updated: {created}\n"
            "type: query\n"
            f"page_id: {page_id}\n"
            f"topic_id: {topic_id}\n"
            "tags: [query, hermes, topic]\n"
            f"sources: [{source_rel}]\n"
            "---\n\n"
            f"# {topic_title}\n\n"
            "## Topic\n\n"
            f"- topic_id: `{topic_id}`\n"
            f"- page_id: `{page_id}`\n\n"
            "## Episodes\n\n"
        )
        return text + episode_block

    text = existing_text
    text = _replace_or_add_frontmatter_line(text, "updated", created)
    text = _merge_sources_line(text, source_rel)
    text = _replace_or_append_episode(text, episode_id=episode_id, episode_block=episode_block)
    return text
