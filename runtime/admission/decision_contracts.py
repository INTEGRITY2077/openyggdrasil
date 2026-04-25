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
def load_evaluator_verdict_schema() -> Dict[str, Any]:
    return _load_schema("evaluator_verdict.v1.schema.json")


@lru_cache(maxsize=1)
def load_admission_verdict_schema() -> Dict[str, Any]:
    return _load_schema("admission_verdict.v1.schema.json")


@lru_cache(maxsize=1)
def load_session_structure_signal_schema() -> Dict[str, Any]:
    return _load_schema("session_structure_signal.v1.schema.json")


@lru_cache(maxsize=1)
def load_session_admission_verdict_schema() -> Dict[str, Any]:
    return _load_schema("session_admission_verdict.v1.schema.json")


@lru_cache(maxsize=1)
def load_source_ref_resolution_result_schema() -> Dict[str, Any]:
    return _load_schema("source_ref_resolution_result.v1.schema.json")


@lru_cache(maxsize=1)
def load_provider_runtime_integrity_result_schema() -> Dict[str, Any]:
    return _load_schema("provider_runtime_integrity_result.v1.schema.json")


@lru_cache(maxsize=1)
def load_session_signal_runner_result_schema() -> Dict[str, Any]:
    return _load_schema("session_signal_runner_result.v1.schema.json")


@lru_cache(maxsize=1)
def load_thin_worker_chain_result_schema() -> Dict[str, Any]:
    return _load_schema("thin_worker_chain_result.v1.schema.json")


@lru_cache(maxsize=1)
def load_mailbox_support_result_schema() -> Dict[str, Any]:
    return _load_schema("mailbox_support_result.v1.schema.json")


@lru_cache(maxsize=1)
def load_engraved_seed_schema() -> Dict[str, Any]:
    return _load_schema("engraved_seed.v1.schema.json")


@lru_cache(maxsize=1)
def load_planting_decision_schema() -> Dict[str, Any]:
    return _load_schema("planting_decision.v1.schema.json")


@lru_cache(maxsize=1)
def load_cultivated_decision_schema() -> Dict[str, Any]:
    return _load_schema("cultivated_decision.v1.schema.json")


@lru_cache(maxsize=1)
def load_map_topography_schema() -> Dict[str, Any]:
    return _load_schema("map_topography.v1.schema.json")


@lru_cache(maxsize=1)
def load_community_topography_schema() -> Dict[str, Any]:
    return _load_schema("community_topography.v1.schema.json")


def validate_decision_surface(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_decision_surface_schema())


def validate_decision_candidate(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_decision_candidate_schema())


def validate_evaluator_verdict(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_evaluator_verdict_schema())


def validate_admission_verdict(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_admission_verdict_schema())


MAX_SIGNAL_TURN_SPAN = 12
FORBIDDEN_SIGNAL_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "summary",
    "claim",
    "claims",
    "canonical_claim",
    "canonical_path",
    "category_ref",
    "category_selection",
    "mailbox_packet",
    "mailbox_mutation",
    "sot_write",
    "decision_candidate",
}


def _raise_signal_validation_error(message: str) -> None:
    raise jsonschema.exceptions.ValidationError(message)


def _reject_forbidden_signal_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_SIGNAL_KEYS:
                _raise_signal_validation_error(
                    f"session_structure_signal.v1 forbids provider authority field {path}.{key}"
                )
            _reject_forbidden_signal_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_signal_keys(child, path=f"{path}[{index}]")


def _validate_signal_constraints(payload: Mapping[str, Any]) -> None:
    _reject_forbidden_signal_keys(payload)
    turn_range = payload.get("turn_range")
    if not isinstance(turn_range, Mapping):
        _raise_signal_validation_error("turn_range must be an object")
    turn_start = int(turn_range.get("from"))
    turn_end = int(turn_range.get("to"))
    if turn_end < turn_start:
        _raise_signal_validation_error("turn_range.to must be greater than or equal to turn_range.from")
    if (turn_end - turn_start + 1) > MAX_SIGNAL_TURN_SPAN:
        _raise_signal_validation_error(
            f"turn_range must cover at most {MAX_SIGNAL_TURN_SPAN} turns"
        )

    surface_reason = str(payload.get("surface_reason") or "").strip()
    if "\n" in surface_reason or "\r" in surface_reason:
        _raise_signal_validation_error("surface_reason must be one line")
    terminal_marks = sum(surface_reason.count(mark) for mark in ".!?")
    if terminal_marks > 1:
        _raise_signal_validation_error("surface_reason must be one sentence")


def validate_session_structure_signal(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_session_structure_signal_schema())
    _validate_signal_constraints(payload)


def validate_session_admission_verdict(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_session_admission_verdict_schema())


def validate_source_ref_resolution_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_source_ref_resolution_result_schema())


def validate_provider_runtime_integrity_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_provider_runtime_integrity_result_schema())


FORBIDDEN_RUNNER_RESULT_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "summary",
    "canonical_claim",
    "canonical_path",
    "mailbox_mutation",
    "sot_write",
}


def _reject_forbidden_runner_result_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_RUNNER_RESULT_KEYS:
                _raise_signal_validation_error(
                    f"session_signal_runner_result.v1 forbids raw/provider authority field {path}.{key}"
                )
            _reject_forbidden_runner_result_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_runner_result_keys(child, path=f"{path}[{index}]")


def validate_session_signal_runner_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_session_signal_runner_result_schema())
    _reject_forbidden_runner_result_keys(payload)


FORBIDDEN_THIN_CHAIN_RESULT_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "summary",
    "canonical_claim",
    "canonical_path",
    "mailbox_mutation",
    "sot_write",
}


def _reject_forbidden_thin_chain_result_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_THIN_CHAIN_RESULT_KEYS:
                _raise_signal_validation_error(
                    f"thin_worker_chain_result.v1 forbids raw/provider authority field {path}.{key}"
                )
            _reject_forbidden_thin_chain_result_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_thin_chain_result_keys(child, path=f"{path}[{index}]")


def validate_thin_worker_chain_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_thin_worker_chain_result_schema())
    _reject_forbidden_thin_chain_result_keys(payload)


FORBIDDEN_MAILBOX_SUPPORT_RESULT_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "summary",
    "canonical_claim",
    "canonical_path",
    "mailbox_mutation",
    "sot_write",
}


def _reject_forbidden_mailbox_support_result_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_MAILBOX_SUPPORT_RESULT_KEYS:
                _raise_signal_validation_error(
                    f"mailbox_support_result.v1 forbids raw/provider authority field {path}.{key}"
                )
            _reject_forbidden_mailbox_support_result_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_mailbox_support_result_keys(child, path=f"{path}[{index}]")


def validate_mailbox_support_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_mailbox_support_result_schema())
    _reject_forbidden_mailbox_support_result_keys(payload)


def validate_engraved_seed(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_engraved_seed_schema())


def validate_planting_decision(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_planting_decision_schema())


def validate_cultivated_decision(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_cultivated_decision_schema())


def validate_map_topography(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_map_topography_schema())


def validate_community_topography(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_community_topography_schema())
