from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


GRAPH_QUALITY_CONTRACT_SCHEMAS = (
    "answer_quality_signal.v1.schema.json",
    "capability_lane_trace.v1.schema.json",
    "category_tree_transaction.v1.schema.json",
    "follow_up_production_request_candidate.v1.schema.json",
    "graph_non_sot_hint.v1.schema.json",
    "graph_quality_feedback_package.v1.schema.json",
    "graph_structure_quality_gate.v1.schema.json",
    "hermes_real_session_usage_probe.v1.schema.json",
    "index_delta.v1.schema.json",
    "log_delta.v1.schema.json",
    "mailbox_intent.v1.schema.json",
    "module_anchor_mapping.v1.schema.json",
    "producer_consumer_smoke.v1.schema.json",
)


def contracts_root() -> Path:
    return Path(__file__).resolve().parents[2] / "contracts"


def load_graph_quality_contract_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in GRAPH_QUALITY_CONTRACT_SCHEMAS:
        raise ValueError("schema_name is not part of the graph quality contract registry")
    return json.loads((contracts_root() / schema_name).read_text(encoding="utf-8"))


def validate_graph_quality_payload(schema_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    schema = load_graph_quality_contract_schema(schema_name)
    try:
        from jsonschema import Draft202012Validator
    except Exception as exc:  # noqa: BLE001 - runtime should fail closed without optional validator.
        return {
            "schema_version": "graph_quality_contract_validation.v1",
            "schema_name": schema_name,
            "status": "typed_unavailable",
            "reason_codes": [f"jsonschema_unavailable:{type(exc).__name__}"],
        }

    errors = sorted(Draft202012Validator(schema).iter_errors(dict(payload)), key=lambda err: list(err.path))
    return {
        "schema_version": "graph_quality_contract_validation.v1",
        "schema_name": schema_name,
        "status": "pass" if not errors else "typed_unavailable",
        "reason_codes": [error.message for error in errors],
        "hard_nonclaims": [
            "graph_quality_contract_validation_is_not_graphify_canonical_authority",
            "schema_validation_is_not_live_provider_rejudgment",
            "schema_validation_is_not_production_ready_by_itself",
        ],
    }


__all__ = [
    "GRAPH_QUALITY_CONTRACT_SCHEMAS",
    "load_graph_quality_contract_schema",
    "validate_graph_quality_payload",
]
