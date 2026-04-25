from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping

import jsonschema

from reasoning.provider_capability_descriptor import background_reasoning_descriptor_implies_completed_support


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"


def _load_schema(filename: str) -> Dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_reasoning_lease_request_schema() -> Dict[str, Any]:
    return _load_schema("reasoning_lease_request.v1.schema.json")


@lru_cache(maxsize=1)
def load_reasoning_lease_result_schema() -> Dict[str, Any]:
    return _load_schema("reasoning_lease_result.v1.schema.json")


def validate_reasoning_lease_request(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_reasoning_lease_request_schema())


def validate_reasoning_lease_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_reasoning_lease_result_schema())


def provider_supports_background_reasoning(provider_descriptor: Mapping[str, Any]) -> bool:
    return background_reasoning_descriptor_implies_completed_support(provider_descriptor)


def lease_mode_for_provider(provider_descriptor: Mapping[str, Any]) -> str:
    if provider_supports_background_reasoning(provider_descriptor):
        return "provider_headless"
    return "deterministic_base_path"
