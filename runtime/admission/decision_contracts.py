from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping

import jsonschema


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"


def _load_schema(filename: str) -> Dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_decision_surface_schema() -> Dict[str, Any]:
    return _load_schema("decision_surface.v1.schema.json")


@lru_cache(maxsize=1)
def load_decision_candidate_schema() -> Dict[str, Any]:
    return _load_schema("decision_candidate.v1.schema.json")


@lru_cache(maxsize=1)
def load_admission_verdict_schema() -> Dict[str, Any]:
    return _load_schema("admission_verdict.v1.schema.json")


@lru_cache(maxsize=1)
def load_engraved_seed_schema() -> Dict[str, Any]:
    return _load_schema("engraved_seed.v1.schema.json")


@lru_cache(maxsize=1)
def load_planting_decision_schema() -> Dict[str, Any]:
    return _load_schema("planting_decision.v1.schema.json")


@lru_cache(maxsize=1)
def load_cultivated_decision_schema() -> Dict[str, Any]:
    return _load_schema("cultivated_decision.v1.schema.json")


def validate_decision_surface(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_decision_surface_schema())


def validate_decision_candidate(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_decision_candidate_schema())


def validate_admission_verdict(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_admission_verdict_schema())


def validate_engraved_seed(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_engraved_seed_schema())


def validate_planting_decision(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_planting_decision_schema())


def validate_cultivated_decision(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_cultivated_decision_schema())
