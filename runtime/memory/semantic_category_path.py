from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "semantic_category_path.v1"
SAFE_SEGMENT_RE = re.compile(r"[^\w-]+", re.UNICODE)


def normalize_category_segment(value: object) -> str:
    text = str(value or "").strip().lower()
    text = SAFE_SEGMENT_RE.sub("-", text)
    text = re.sub(r"-+", "-", text).strip("-._")
    return text or "uncategorized"


def _as_segments(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"\s*(?:/|>|::)\s*", value)
        return [normalize_category_segment(item) for item in raw if str(item).strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [normalize_category_segment(item) for item in value if str(item).strip()]
    return []


def infer_semantic_category_segments(payload: Mapping[str, Any], *, topic_title: str = "") -> list[str]:
    explicit = (
        _as_segments(payload.get("semantic_category_path"))
        or _as_segments(payload.get("category_path"))
    )
    if explicit:
        return explicit[:8]

    text = " ".join(
        str(payload.get(key) or "")
        for key in (
            "topic_hint",
            "canonical_topic_title",
            "decision",
            "context",
            "conclusion",
            "community",
            "category_community_hint",
        )
    )
    text = f"{topic_title} {text}".lower()
    if "claude code" in text or "claude-code" in text:
        segments = ["software-development", "claude-code"]
        if any(term in text for term in ("hook", "skill", "mcp", "plugin", "agent")):
            segments.append("extension-placement")
        if "agent" in text:
            segments.append("agents")
        elif "hook" in text or "skill" in text or "mcp" in text or "plugin" in text:
            segments.append("hooks-skills-mcp-plugins")
        return segments

    node_type = str(payload.get("node_type") or payload.get("category") or "concept")
    return [normalize_category_segment(node_type)]


def build_semantic_category_path(
    payload: Mapping[str, Any],
    *,
    topic_title: str = "",
    authority_owner: str = "amundsen",
    decision_ref: str | None = None,
    basis_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    segments = infer_semantic_category_segments(payload, topic_title=topic_title)
    return {
        "schema_version": SCHEMA_VERSION,
        "segments": segments,
        "path": "/".join(segments),
        "category_authority": {
            "owner": authority_owner,
            "decision_ref": decision_ref,
            "basis_refs": [str(item) for item in (basis_refs or []) if str(item).strip()],
        },
        "physical_storage_is_not_semantic_category": True,
        "reason_codes": [
            "semantic_category_path_separate_from_physical_continent",
            f"category_authority:{authority_owner}",
        ],
    }


def category_page_relative_path(category_path: Mapping[str, Any], *, slug: str) -> str:
    segments = [normalize_category_segment(item) for item in category_path.get("segments") or []]
    safe_slug = normalize_category_segment(slug)
    if not segments:
        segments = ["uncategorized"]
    if segments[-1] == safe_slug:
        return "categories/" + "/".join(segments) + ".md"
    return "categories/" + "/".join([*segments, safe_slug]) + ".md"


__all__ = [
    "SCHEMA_VERSION",
    "build_semantic_category_path",
    "category_page_relative_path",
    "infer_semantic_category_segments",
    "normalize_category_segment",
]
