from __future__ import annotations

from dataclasses import dataclass
import importlib


PATHFINDER_IMPLEMENTATION_MODULE = "runtime.retrieval.pathfinder_tools"
COLLECT_CLAIM_IDS_IMPLEMENTATION_MODULE = "runtime.retrieval.ptc_tools.collect_claim_ids"


@dataclass(frozen=True)
class PreambleFacade:
    facade_name: str
    ipc_method: str
    implementation_name: str
    signature: str
    call_kwargs: str
    docstring: str
    implementation_module: str = PATHFINDER_IMPLEMENTATION_MODULE

    def render_preamble_function(self) -> str:
        return (
            f"def {self.facade_name}({self.signature}):\n"
            f"    '''{self.docstring}'''\n"
            f"    return _ptc_call(\"{self.ipc_method}\", {self.call_kwargs})"
        )


PATHFINDER_FACADES: tuple[PreambleFacade, ...] = (
    PreambleFacade(
        facade_name="locate_region",
        ipc_method="locate_region",
        implementation_name="locate_region",
        signature="query_text",
        call_kwargs="query_text=query_text",
        docstring=(
            "Discover which Vault region the query belongs to.\n"
            "    Use this when: starting a new provenance trace.\n"
            "    Do NOT use when: you already have a topic_id -> skip to read_source_paths.\n"
            "    If ambiguous: always call this first before select_topic_anchor."
        ),
    ),
    PreambleFacade(
        facade_name="select_topic_anchor",
        ipc_method="select_topic_anchor",
        implementation_name="select_topic_anchor",
        signature="query_text, region_id=None",
        call_kwargs="query_text=query_text, region_id=region_id",
        docstring=(
            "Connect query to an existing Vault topic.\n"
            "    Use this when: you have a region and need to find the specific topic.\n"
            "    Do NOT use when: you already know the topic_id.\n"
            "    If ambiguous: call locate_region first, then this."
        ),
    ),
    PreambleFacade(
        facade_name="read_origin_claims",
        ipc_method="read_origin_claims",
        implementation_name="get_origin_claims",
        signature="topic_id, limit=1",
        call_kwargs="topic_id=topic_id, limit=limit",
        docstring=(
            "Read the original claims that established this topic.\n"
            "    Use this when: you need the earliest provenance records.\n"
            "    Do NOT use when: you only need recent updates -> use read_recent_claims.\n"
            "    Can be called in PARALLEL with read_recent_claims (no dependency)."
        ),
    ),
    PreambleFacade(
        facade_name="read_recent_claims",
        ipc_method="read_recent_claims",
        implementation_name="read_recent_claims",
        signature="topic_id, limit=3",
        call_kwargs="topic_id=topic_id, limit=limit",
        docstring=(
            "Read the most recent claims/updates for this topic.\n"
            "    Use this when: you need to see how knowledge evolved.\n"
            "    Do NOT use when: you only need origin -> use read_origin_claims.\n"
            "    Can be called in PARALLEL with read_origin_claims (no dependency)."
        ),
    ),
    PreambleFacade(
        facade_name="collect_claim_ids",
        ipc_method="collect_claim_ids",
        implementation_name="collect_claim_ids",
        implementation_module=COLLECT_CLAIM_IDS_IMPLEMENTATION_MODULE,
        signature="origin_rows=None, recent_rows=None",
        call_kwargs="origin_rows=origin_rows or [], recent_rows=recent_rows or []",
        docstring=(
            "Collect unique claim IDs from origin and recent rows.\n"
            "    Use this when: you have both origin and recent rows and need deduped IDs."
        ),
    ),
    PreambleFacade(
        facade_name="read_source_paths",
        ipc_method="read_source_paths",
        implementation_name="read_source_paths",
        signature="topic_id, claim_ids=None",
        call_kwargs="topic_id=topic_id, claim_ids=claim_ids",
        docstring=(
            "Get absolute source file paths for given claim IDs.\n"
            "    Use this when: you need to trace where knowledge came from.\n"
            "    Do NOT use when: you only need claim content -> use read_origin_claims."
        ),
    ),
    PreambleFacade(
        facade_name="assemble_support_bundle",
        ipc_method="assemble_support_bundle",
        implementation_name="build_support_bundle",
        signature="query_text, anchor, origin_rows=None, recent_rows=None, source_paths=None",
        call_kwargs=(
            "query_text=query_text, anchor=anchor, origin_rows=origin_rows or [], "
            "recent_rows=recent_rows or [], source_paths=source_paths or []"
        ),
        docstring=(
            "Assemble a bounded support bundle with full provenance.\n"
            "    Use this when: you have anchor + claims + sources and need final output.\n"
            "    This should be the LAST provenance call before result()."
        ),
    ),
    PreambleFacade(
        facade_name="assemble_unanchored_bundle",
        ipc_method="assemble_unanchored_bundle",
        implementation_name="assemble_unanchored_bundle",
        signature="query_text",
        call_kwargs="query_text=query_text",
        docstring=(
            "Return an honest \"nothing found\" bundle.\n"
            "    Use this when: select_topic_anchor returned anchor_type=\"none\".\n"
            "    Do NOT use when: you have a valid anchor -> use assemble_support_bundle."
        ),
    ),
)


PATHFINDER_FACADE_IMPLEMENTATION_MAP = {
    item.facade_name: item.implementation_name for item in PATHFINDER_FACADES
}

PATHFINDER_FACADE_METHOD_MAP = {
    item.facade_name: item.ipc_method for item in PATHFINDER_FACADES
}

PATHFINDER_PREAMBLE_METHODS = frozenset(item.ipc_method for item in PATHFINDER_FACADES)
PATHFINDER_PREAMBLE_FACADE_NAMES = frozenset(item.facade_name for item in PATHFINDER_FACADES)


def render_pathfinder_preamble_facades() -> str:
    return "\n\n".join(item.render_preamble_function() for item in PATHFINDER_FACADES)


def validate_pathfinder_facade_manifest() -> dict[str, object]:
    missing_implementations: list[str] = []
    for item in PATHFINDER_FACADES:
        module = importlib.import_module(item.implementation_module)
        if not hasattr(module, item.implementation_name):
            missing_implementations.append(
                f"{item.implementation_module}:{item.implementation_name}"
            )
    if missing_implementations:
        raise ValueError(
            "missing Pathfinder facade implementations: "
            + ", ".join(missing_implementations)
        )
    return {
        "facade_count": len(PATHFINDER_FACADES),
        "facade_names": sorted(PATHFINDER_PREAMBLE_FACADE_NAMES),
        "ipc_methods": sorted(PATHFINDER_PREAMBLE_METHODS),
    }


__all__ = [
    "COLLECT_CLAIM_IDS_IMPLEMENTATION_MODULE",
    "PATHFINDER_FACADE_IMPLEMENTATION_MAP",
    "PATHFINDER_FACADE_METHOD_MAP",
    "PATHFINDER_FACADES",
    "PATHFINDER_IMPLEMENTATION_MODULE",
    "PATHFINDER_PREAMBLE_FACADE_NAMES",
    "PATHFINDER_PREAMBLE_METHODS",
    "PreambleFacade",
    "render_pathfinder_preamble_facades",
    "validate_pathfinder_facade_manifest",
]
