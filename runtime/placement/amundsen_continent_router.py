from __future__ import annotations

from typing import Any, Mapping, Sequence

from runtime.memory.semantic_category_path import build_semantic_category_path


def route_amundsen_continent(
    *,
    payload: Mapping[str, Any],
    topic_title: str,
    basis_refs: Sequence[str],
    candidate_categories: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not basis_refs:
        return {
            "schema_version": "amundsen_continent_route.v1",
            "route_status": "typed_unavailable",
            "reason_codes": ["amundsen_basis_refs_required"],
            "semantic_category_path": None,
            "graphify_used_as_sot": False,
        }
    selected = None
    for candidate in candidate_categories or ():
        if str(candidate.get("category_ref") or candidate.get("basis_ref") or "") in set(str(ref) for ref in basis_refs):
            selected = candidate
            break
    category_path = build_semantic_category_path(
        {**dict(payload), **(dict(selected) if isinstance(selected, Mapping) else {})},
        topic_title=topic_title,
        authority_owner="amundsen",
        decision_ref=str((selected or {}).get("category_ref") or ""),
        basis_refs=basis_refs,
    )
    return {
        "schema_version": "amundsen_continent_route.v1",
        "route_status": "routed",
        "semantic_category_path": category_path,
        "decision_branch": "existing_category" if selected else "inferred_category_with_basis_refs",
        "basis_refs": [str(ref) for ref in basis_refs],
        "graphify_used_as_sot": False,
        "reason_codes": [
            "amundsen_basis_refs_present",
            "graphify_advisory_only",
        ],
    }


__all__ = ["route_amundsen_continent"]
