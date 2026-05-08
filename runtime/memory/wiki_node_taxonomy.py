from __future__ import annotations

import re
from typing import Any, Mapping


SCHEMA_VERSION = "wiki_node_taxonomy.v1"

ALLOWED_CONTINENTS = (
    "concepts",
    "entities",
    "comparisons",
    "queries",
    "communities",
    "provenance",
)
ALLOWED_NODE_TYPES = (
    "entity",
    "tool",
    "concept",
    "domain",
    "policy",
    "procedure",
    "workflow",
    "runbook",
    "task",
    "decision",
    "contract",
    "claim",
    "evidence",
    "source",
    "dataset",
    "metric",
    "event",
    "artifact",
    "issue",
    "proposal",
    "plan",
    "result",
    "report",
    "query_pattern",
    "evaluation",
    "comparison",
    "community",
    "unknown",
)
ALLOWED_TOPOGRAPHY_LEVELS = (
    "continent",
    "mountain",
    "forest",
    "tree",
    "branch",
    "leaf",
    "chloroplast",
)
ALLOWED_COMMUNITY_ROLES = (
    "forest",
    "hub",
    "bridge",
    "member",
    "outlier",
    "none",
)

NODE_TYPE_ALIASES = {
    "product": "entity",
    "person": "entity",
    "people": "entity",
    "company": "entity",
    "organization": "entity",
    "org": "entity",
    "place": "entity",
    "location": "entity",
    "service": "tool",
    "framework": "tool",
    "library": "tool",
    "cli": "tool",
    "command": "tool",
    "script": "tool",
    "docs": "source",
    "documentation": "source",
    "doc": "source",
    "data": "dataset",
    "kpi": "metric",
    "score": "metric",
    "incident": "event",
    "release": "event",
    "object": "artifact",
    "file": "artifact",
    "workflow": "workflow",
    "job": "task",
    "todo": "task",
    "question_pattern": "query_pattern",
    "question": "query_pattern",
    "pattern": "query_pattern",
    "eval": "evaluation",
    "assessment": "evaluation",
    "compare": "comparison",
}


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^0-9a-z_/-]+", "_", text)
    text = text.strip("_-/")
    return NODE_TYPE_ALIASES.get(text, text)


def _first_token(payload: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str, str]:
    for key in keys:
        value = payload.get(key)
        token = _token(value)
        if token:
            return token, key
    return "", ""


def normalize_node_type(value: Any, *, default: str = "unknown") -> str:
    token = _token(value)
    if token in ALLOWED_NODE_TYPES:
        return token
    fallback = _token(default)
    return fallback if fallback in ALLOWED_NODE_TYPES else "unknown"


def normalize_continent(value: Any, *, default: str = "concepts") -> str:
    token = _token(value)
    if token in ALLOWED_CONTINENTS:
        return token
    fallback = _token(default)
    return fallback if fallback in ALLOWED_CONTINENTS else "concepts"


def normalize_topography_level(value: Any, *, node_type: str = "concept") -> str:
    token = _token(value)
    if token in ALLOWED_TOPOGRAPHY_LEVELS:
        return token
    if node_type == "community":
        return "forest"
    if node_type in {"evidence", "source"}:
        return "chloroplast"
    if node_type in {"dataset", "metric"}:
        return "chloroplast"
    if node_type in {"claim", "decision", "event", "artifact"}:
        return "leaf"
    if node_type in {"issue", "proposal", "plan", "result", "report", "evaluation", "task"}:
        return "branch"
    return "tree"


def normalize_community_role(value: Any, *, node_type: str = "concept", topography_level: str = "tree") -> str:
    token = _token(value)
    if token in ALLOWED_COMMUNITY_ROLES:
        return token
    if node_type == "community" or topography_level == "forest":
        return "forest"
    return "member"


def infer_node_type(payload: Mapping[str, Any], *, default: str = "policy") -> tuple[str, str]:
    explicit, source = _first_token(payload, ("node_type", "type", "category"))
    if explicit:
        return normalize_node_type(explicit, default=default), source

    text = " ".join(
        str(payload.get(key) or "")
        for key in (
            "canonical_topic_title",
            "topic_title",
            "topic_hint",
            "intent_field",
            "decision",
            "surface_reason",
            "category_community_hint",
        )
    ).lower()
    marker_map = (
        (("runbook", "playbook"), "runbook"),
        (("workflow", "flow"), "workflow"),
        (("task", "todo", "job"), "task"),
        (("procedure", "checklist", "smoke", "first-run", "install check"), "procedure"),
        (("contract", "sot"), "contract"),
        (("issue", "risk", "bug", "gap"), "issue"),
        (("proposal",), "proposal"),
        (("plan",), "plan"),
        (("result", "report", "proof"), "report"),
        (("evaluation", "scorecard", "rubric"), "evaluation"),
        (("metric", "kpi", "score"), "metric"),
        (("dataset", "data table"), "dataset"),
        (("event", "incident", "release"), "event"),
        (("artifact", "file", "output"), "artifact"),
        (("domain", "taxonomy"), "domain"),
        (("entity", "product", "company", "framework", "library"), "entity"),
        (("comparison", "versus", "vs "), "comparison"),
    )
    for markers, node_type in marker_map:
        if any(marker in text for marker in markers):
            return node_type, "inferred_from_text"
    return normalize_node_type(default, default="policy"), "default"


def build_node_taxonomy(
    payload: Mapping[str, Any] | None,
    *,
    physical_continent: str = "concepts",
    default_node_type: str = "policy",
) -> dict[str, Any]:
    payload = dict(payload or {})
    node_type, source = infer_node_type(payload, default=default_node_type)
    continent = normalize_continent(payload.get("continent") or payload.get("physical_continent"), default=physical_continent)
    topography_level = normalize_topography_level(payload.get("topography_level"), node_type=node_type)
    community_role = normalize_community_role(payload.get("community_role"), node_type=node_type, topography_level=topography_level)
    return {
        "schema_version": SCHEMA_VERSION,
        "continent": continent,
        "physical_continent": continent,
        "node_type": node_type,
        "topography_level": topography_level,
        "community_role": community_role,
        "classification_source": source,
        "taxonomy_status": "valid",
    }


def build_community_node_taxonomy(community_id: str) -> dict[str, Any]:
    taxonomy = build_node_taxonomy(
        {
            "node_type": "community",
            "continent": "communities",
            "topography_level": "forest",
            "community_role": "forest",
            "community_id": community_id,
        },
        physical_continent="communities",
        default_node_type="community",
    )
    taxonomy["classification_source"] = "community_node"
    return taxonomy


def validate_node_taxonomy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"valid": False, "reason_code": "not_mapping"}
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    if value.get("continent") not in ALLOWED_CONTINENTS:
        errors.append("invalid_continent")
    if value.get("node_type") not in ALLOWED_NODE_TYPES:
        errors.append("invalid_node_type")
    if value.get("topography_level") not in ALLOWED_TOPOGRAPHY_LEVELS:
        errors.append("invalid_topography_level")
    if value.get("community_role") not in ALLOWED_COMMUNITY_ROLES:
        errors.append("invalid_community_role")
    return {"valid": not errors, "reason_codes": errors}


def coerce_node_taxonomy(
    value: Any,
    *,
    fallback_payload: Mapping[str, Any] | None = None,
    physical_continent: str = "concepts",
    default_node_type: str = "concept",
) -> dict[str, Any]:
    if isinstance(value, Mapping) and validate_node_taxonomy(value)["valid"]:
        return dict(value)
    taxonomy = build_node_taxonomy(
        fallback_payload or {},
        physical_continent=physical_continent,
        default_node_type=default_node_type,
    )
    taxonomy["classification_source"] = "coerced_from_legacy_fields"
    return taxonomy


__all__ = [
    "ALLOWED_COMMUNITY_ROLES",
    "ALLOWED_CONTINENTS",
    "ALLOWED_NODE_TYPES",
    "ALLOWED_TOPOGRAPHY_LEVELS",
    "SCHEMA_VERSION",
    "build_community_node_taxonomy",
    "build_node_taxonomy",
    "coerce_node_taxonomy",
    "normalize_node_type",
    "validate_node_taxonomy",
]
