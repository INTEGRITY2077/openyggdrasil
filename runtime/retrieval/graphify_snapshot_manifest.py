from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso
from retrieval.graphify_snapshot_adapter import validate_graphify_snapshot_adapter_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "contracts" / "graphify_snapshot_manifest.v1.schema.json"


@lru_cache(maxsize=1)
def load_graphify_snapshot_manifest_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_graphify_snapshot_manifest(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_graphify_snapshot_manifest_schema())
    if payload.get("status") == "available":
        if payload.get("summary") is None:
            raise ValueError("Available Graphify manifest requires summary")
        if payload.get("failure") is not None:
            raise ValueError("Available Graphify manifest must not carry failure")
    elif payload.get("status") == "unavailable":
        if payload.get("summary") is not None:
            raise ValueError("Unavailable Graphify manifest must not carry summary")
        if payload.get("failure") is None:
            raise ValueError("Unavailable Graphify manifest requires failure")


def build_graphify_snapshot_manifest(
    *,
    adapter_payload: Mapping[str, Any],
    manifest_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_graphify_snapshot_adapter_payload(adapter_payload)
    payload = {
        "schema_version": "graphify_snapshot_manifest.v1",
        "manifest_id": manifest_id or f"graphify-snapshot:{uuid.uuid4().hex}",
        "source_adapter_schema_version": str(adapter_payload["schema_version"]),
        "status": str(adapter_payload["status"]),
        "snapshot_role": str(adapter_payload["source_role"]),
        "canonicality": str(adapter_payload["canonicality"]),
        "mutation_policy": str(adapter_payload["mutation_policy"]),
        "graph_path": adapter_payload.get("graph_path"),
        "summary_path": adapter_payload.get("summary_path"),
        "graphify_manifest_path": adapter_payload.get("manifest_path"),
        "vault_root": str(adapter_payload["vault_root"]),
        "summary": adapter_payload.get("summary"),
        "freshness": dict(adapter_payload.get("freshness") or {}),
        "failure": adapter_payload.get("failure"),
        "provenance_policy": {
            "graphify_is_sot": False,
            "must_verify_against_sot": True,
            "raw_session_copy_allowed": False,
            "provider_may_answer_from_graphify_alone": False,
        },
        "generated_at": generated_at or str(adapter_payload.get("generated_at") or utc_now_iso()),
    }
    validate_graphify_snapshot_manifest(payload)
    return payload
