from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from runtime.common.contract_validation import validate_contract_payload


SCHEMA_VERSION = "semantic_category_path.v1"
SEMANTIC_CATEGORY_PATH_SCHEMA = "semantic_category_path.v1.schema.json"
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


def _category_text(payload: Mapping[str, Any], *, topic_title: str = "") -> str:
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
            "reuse_condition",
        )
    )
    return f"{topic_title} {text}".lower()


def _claude_code_segments(text: str) -> list[str] | None:
    if "claude code" not in text and "claude-code" not in text:
        return None
    segments = ["software-development", "claude-code"]
    if any(
        term in text
        for term in (
            "permission",
            "approval",
            "allowed tool",
            "tool access",
            "tool exposure",
            "security",
            "mcp exposure",
            "external connection exposure",
        )
    ):
        return [*segments, "security-permissions", "tool-access"]
    if any(term in text for term in ("hook", "skill", "mcp", "plugin", "agent")):
        segments.append("extension-placement")
    if "agent" in text:
        segments.append("agents")
    elif any(term in text for term in ("hook", "skill", "mcp", "plugin")):
        segments.append("hooks-skills-mcp-plugins")
    return segments


def _animal_ecology_segments(text: str) -> list[str] | None:
    if not any(
        term in text
        for term in (
            "dog",
            "dogs",
            "puppy",
            "breed",
            "husky",
            "chihuahua",
            "canine",
            "강아지",
            "개",
            "반려견",
            "품종",
        )
    ):
        return None
    segments = ["biology", "animal-ecology"]
    if any(term in text for term in ("domestic dog ecology", "dog walking", "walk", "smell", "odor", "routine", "산책", "후각", "냄새", "루틴")):
        return [*segments, "domestic-dogs"]
    if any(term in text for term in ("welfare", "punishment", "training", "ethic", "stress", "체벌", "훈련", "복지", "스트레스")):
        return [*segments, "companion-animal-welfare"]
    if any(term in text for term in ("wildlife", "urban", "park", "habitat", "도시", "공원", "야생동물", "서식지")):
        return [*segments, "urban-animal-ecology"]
    return [*segments, "domestic-dogs"]


def _memory_system_segments(text: str) -> list[str] | None:
    if not any(term in text for term in ("memory", "wiki ring", "openyggdrasil", "provider", "mf1", "ms1", "janitor", "메모리", "위키", "기억")):
        return None
    segments = ["memory-systems", "openyggdrasil"]
    if any(term in text for term in ("wiki ring", "node", "article", "vault", "노드", "문서")):
        return [*segments, "wiki-ring"]
    if any(term in text for term in ("provider", "ms1", "mf1", "postman", "janitor")):
        return [*segments, "memory-roles"]
    return segments


def infer_semantic_category_segments(payload: Mapping[str, Any], *, topic_title: str = "") -> list[str]:
    explicit = (
        _as_segments(payload.get("semantic_category_path"))
        or _as_segments(payload.get("category_path"))
    )
    if explicit:
        return explicit[:8]

    text = _category_text(payload, topic_title=topic_title)

    # Domain-specific user topics outrank generic capture metadata. Provider,
    # MS1, MF1, and OpenYggdrasil words often appear in machine fields and must
    # not pull a Claude Code or biology article into memory-system topology.
    for classifier in (_animal_ecology_segments, _claude_code_segments, _memory_system_segments):
        segments = classifier(text)
        if segments:
            return segments[:8]

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
    basis = [str(item) for item in (basis_refs or []) if str(item).strip()]
    if not basis:
        basis = [str(decision_ref or "category-basis://openyggdrasil/inferred-from-topic")]
    result = {
        "schema_version": SCHEMA_VERSION,
        "segments": segments,
        "path": "/".join(segments),
        "category_authority": {
            "owner": authority_owner,
            "decision_ref": decision_ref,
            "basis_refs": basis,
        },
        "physical_storage_is_not_semantic_category": True,
        "reason_codes": [
            "semantic_category_path_separate_from_physical_continent",
            f"category_authority:{authority_owner}",
        ],
    }
    validate_semantic_category_path(result)
    return result


def validate_semantic_category_path(payload: Mapping[str, Any]) -> None:
    validate_contract_payload(payload, SEMANTIC_CATEGORY_PATH_SCHEMA)


def category_page_relative_path(category_path: Mapping[str, Any], *, slug: str) -> str:
    segments = [normalize_category_segment(item) for item in category_path.get("segments") or []]
    safe_slug = normalize_category_segment(slug)
    if not segments:
        segments = ["uncategorized"]
    if segments[-1] == safe_slug:
        return "categories/" + "/".join(segments) + ".md"
    return "categories/" + "/".join([*segments, safe_slug]) + ".md"


__all__ = [
    "SEMANTIC_CATEGORY_PATH_SCHEMA",
    "SCHEMA_VERSION",
    "build_semantic_category_path",
    "category_page_relative_path",
    "infer_semantic_category_segments",
    "normalize_category_segment",
    "validate_semantic_category_path",
]
