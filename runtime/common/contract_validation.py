from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"


@lru_cache(maxsize=64)
def load_contract_schema(filename: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


def _inline_local_refs(value: Any, *, seen: frozenset[str] = frozenset()) -> Any:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.endswith(".schema.json") and "://" not in ref and "#" not in ref:
            if ref in seen:
                return value
            return _inline_local_refs(load_contract_schema_copy(ref), seen=seen | {ref})
        return {key: _inline_local_refs(child, seen=seen) for key, child in value.items()}
    if isinstance(value, list):
        return [_inline_local_refs(item, seen=seen) for item in value]
    return value


@lru_cache(maxsize=64)
def load_contract_schema_for_validation(filename: str) -> dict[str, Any]:
    return _inline_local_refs(load_contract_schema_copy(filename), seen=frozenset({filename}))


def validate_contract_payload(payload: Mapping[str, Any], filename: str) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_contract_schema_for_validation(filename))


def load_contract_schema_copy(filename: str) -> dict[str, Any]:
    return copy.deepcopy(load_contract_schema(filename))


__all__ = [
    "CONTRACTS_ROOT",
    "OPENYGGDRASIL_ROOT",
    "load_contract_schema",
    "load_contract_schema_copy",
    "load_contract_schema_for_validation",
    "validate_contract_payload",
]
