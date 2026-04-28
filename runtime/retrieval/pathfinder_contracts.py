from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
PATHFINDER_SCHEMA_PATH = OPENYGGDRASIL_ROOT / "contracts" / "pathfinder.v1.schema.json"
PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT / "contracts" / "pathfinder_retrieval_result.v1.schema.json"
)
PATHFINDER_PRODUCT_ROUTE_RESULT_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT / "contracts" / "pathfinder_product_route_result.v1.schema.json"
)
PRODUCT_ROUTE_GRAPHIFY_HINT_STATUSES = {
    "used_non_sot_hint",
    "unavailable_fallback",
    "not_requested",
}
PRODUCT_ROUTE_FORBIDDEN_TEXT = (
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    "file://",
    "api_key",
    "apikey",
    "password",
    "secret",
    "credential",
    "auth.json",
    ".env",
    "transcript.txt",
    "transcripts/",
)


@lru_cache(maxsize=1)
def load_pathfinder_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_SCHEMA_PATH.read_text(encoding="utf-8"))

@lru_cache(maxsize=1)
def load_pathfinder_retrieval_result_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_RETRIEVAL_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))

@lru_cache(maxsize=1)
def load_pathfinder_product_route_result_schema() -> dict[str, Any]:
    return json.loads(PATHFINDER_PRODUCT_ROUTE_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))

def validate_pathfinder_bundle(bundle: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(bundle), schema=load_pathfinder_schema())

def validate_pathfinder_retrieval_result(payload: Mapping[str, Any]) -> None:
    result = dict(payload)
    jsonschema.validate(instance=result, schema=load_pathfinder_retrieval_result_schema())
    default_product_route = result.get("default_product_route")
    if result.get("status") == "completed":
        if not isinstance(default_product_route, Mapping):
            raise ValueError("completed Pathfinder retrieval requires default_product_route")
        validate_pathfinder_product_route_result(default_product_route)
    elif default_product_route is not None:
        raise ValueError("stopped Pathfinder retrieval must not include default_product_route")

def validate_pathfinder_product_route_result(payload: Mapping[str, Any]) -> None:
    product_route = dict(payload)
    jsonschema.validate(
        instance=product_route,
        schema=load_pathfinder_product_route_result_schema(),
    )
    normalized = json.dumps(product_route, sort_keys=True).lower().replace("\\", "/")
    for forbidden in PRODUCT_ROUTE_FORBIDDEN_TEXT:
        if forbidden.lower().replace("\\", "/") in normalized:
            raise ValueError(f"pathfinder product route result contains forbidden text: {forbidden}")
