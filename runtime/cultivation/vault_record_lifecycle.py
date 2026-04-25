from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
VAULT_RECORD_LIFECYCLE_SCHEMA_PATH = CONTRACTS_ROOT / "vault_record_lifecycle.v1.schema.json"


@lru_cache(maxsize=1)
def load_vault_record_lifecycle_schema() -> dict[str, Any]:
    return json.loads(VAULT_RECORD_LIFECYCLE_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_vault_record_lifecycle(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_vault_record_lifecycle_schema())


def _require_mapping(name: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not dict(value):
        raise ValueError(f"{name} is required")
    return dict(value)


def _require_refs(name: str, values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs = [dict(value) for value in values if isinstance(value, Mapping) and dict(value)]
    if not refs:
        raise ValueError(f"{name} are required")
    return refs


def _archive_refs(
    *,
    source_refs: list[dict[str, Any]],
    archive_trace_refs: Sequence[Mapping[str, Any]] | None,
    source_promotion_request_id: str | None,
) -> list[dict[str, Any]]:
    refs = [dict(ref) for ref in archive_trace_refs or [] if isinstance(ref, Mapping) and dict(ref)]
    if source_promotion_request_id:
        refs.append({"kind": "promotion_request", "ref": source_promotion_request_id})
    refs.extend({"kind": "source_ref", "ref": ref} for ref in source_refs[:8])
    return refs or [{"kind": "lifecycle_record", "ref": "traceability_preserved"}]


def build_active_vault_record_lifecycle(
    *,
    canonical_record_id: str,
    canonical_ref: Mapping[str, Any],
    source_promotion_request_id: str | None,
    source_refs: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    valid_from: str | None = None,
    archive_trace_refs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    active_source_refs = _require_refs("source_refs", source_refs)
    created_at = valid_from or utc_now_iso()
    record = {
        "schema_version": "vault_record_lifecycle.v1",
        "lifecycle_record_id": uuid.uuid4().hex,
        "canonical_record_id": str(canonical_record_id).strip(),
        "lifecycle_state": "ACTIVE",
        "canonical_ref": _require_mapping("canonical_ref", canonical_ref),
        "source_promotion_request_id": source_promotion_request_id,
        "source_refs": active_source_refs,
        "provenance": _require_mapping("provenance", provenance),
        "valid_from": created_at,
        "valid_until": None,
        "invalidated_by": None,
        "superseded_by": None,
        "superseded_at": None,
        "supersession_reason": None,
        "archive_trace_refs": _archive_refs(
            source_refs=active_source_refs,
            archive_trace_refs=archive_trace_refs,
            source_promotion_request_id=source_promotion_request_id,
        ),
        "deletion_policy": "soft_delete_only",
        "physical_delete_allowed": False,
        "traceability_preserved": True,
        "created_at": created_at,
        "updated_at": created_at,
    }
    if not record["canonical_record_id"]:
        raise ValueError("canonical_record_id is required")
    validate_vault_record_lifecycle(record)
    return record


def _require_active_record(record: Mapping[str, Any]) -> dict[str, Any]:
    active = dict(record)
    validate_vault_record_lifecycle(active)
    if active.get("lifecycle_state") != "ACTIVE":
        raise ValueError("only ACTIVE records can transition through this builder")
    if active.get("physical_delete_allowed") is not False:
        raise ValueError("physical deletion is not allowed")
    return active


def mark_vault_record_superseded(
    record: Mapping[str, Any],
    *,
    superseded_by: str,
    supersession_reason: str,
    invalidated_by: Mapping[str, Any],
    superseded_at: str | None = None,
) -> dict[str, Any]:
    active = _require_active_record(record)
    transition_at = superseded_at or utc_now_iso()
    successor = str(superseded_by).strip()
    reason = str(supersession_reason).strip()
    if not successor:
        raise ValueError("superseded_by is required")
    if not reason:
        raise ValueError("supersession_reason is required")
    transitioned = {
        **active,
        "lifecycle_state": "SUPERSEDED",
        "valid_until": transition_at,
        "invalidated_by": _require_mapping("invalidated_by", invalidated_by),
        "superseded_by": successor,
        "superseded_at": transition_at,
        "supersession_reason": reason,
        "archive_trace_refs": list(active["archive_trace_refs"])
        + [
            {
                "kind": "lifecycle_transition",
                "from_state": "ACTIVE",
                "to_state": "SUPERSEDED",
                "successor": successor,
                "reason": reason,
            }
        ],
        "deletion_policy": "soft_delete_only",
        "physical_delete_allowed": False,
        "traceability_preserved": True,
        "updated_at": transition_at,
    }
    validate_vault_record_lifecycle(transitioned)
    return transitioned


def mark_vault_record_stale(
    record: Mapping[str, Any],
    *,
    supersession_reason: str,
    invalidated_by: Mapping[str, Any],
    stale_at: str | None = None,
) -> dict[str, Any]:
    active = _require_active_record(record)
    transition_at = stale_at or utc_now_iso()
    reason = str(supersession_reason).strip()
    if not reason:
        raise ValueError("supersession_reason is required")
    transitioned = {
        **active,
        "lifecycle_state": "STALE",
        "valid_until": transition_at,
        "invalidated_by": _require_mapping("invalidated_by", invalidated_by),
        "superseded_by": None,
        "superseded_at": None,
        "supersession_reason": reason,
        "archive_trace_refs": list(active["archive_trace_refs"])
        + [
            {
                "kind": "lifecycle_transition",
                "from_state": "ACTIVE",
                "to_state": "STALE",
                "reason": reason,
            }
        ],
        "deletion_policy": "soft_delete_only",
        "physical_delete_allowed": False,
        "traceability_preserved": True,
        "updated_at": transition_at,
    }
    validate_vault_record_lifecycle(transitioned)
    return transitioned
