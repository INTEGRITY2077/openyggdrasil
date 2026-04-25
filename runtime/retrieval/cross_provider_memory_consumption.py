from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso

from .pathfinder import validate_pathfinder_retrieval_result


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
CROSS_PROVIDER_MEMORY_CONSUMPTION_RESULT_SCHEMA_PATH = (
    CONTRACTS_ROOT / "cross_provider_memory_consumption_result.v1.schema.json"
)


@lru_cache(maxsize=1)
def load_cross_provider_memory_consumption_result_schema() -> dict[str, Any]:
    return json.loads(CROSS_PROVIDER_MEMORY_CONSUMPTION_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_cross_provider_memory_consumption_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_cross_provider_memory_consumption_result_schema(),
    )


def _required_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _source_refs(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = [dict(ref) for ref in record.get("source_refs") or [] if isinstance(ref, Mapping) and dict(ref)]
    if not refs:
        raise ValueError("source_refs are required for cross-provider consumption")
    for ref in refs:
        path_hint = str(ref.get("path_hint") or "").strip()
        if not path_hint or path_hint == "missing-source-ref":
            raise ValueError("forwarded source_refs are required for cross-provider consumption")
    return refs


def _provider_provenance(record: Mapping[str, Any]) -> dict[str, Any]:
    provenance = dict(record.get("provenance") or {})
    return {
        "provider_id": _required_text("provenance.provider_id", provenance.get("provider_id")),
        "provider_profile": _required_text("provenance.provider_profile", provenance.get("provider_profile")),
        "provider_session_id": _required_text(
            "provenance.provider_session_id",
            provenance.get("provider_session_id"),
        ),
        "session_uid": _required_text("provenance.session_uid", provenance.get("session_uid")),
        "source_provenance": provenance,
    }


def _confidence(record: Mapping[str, Any]) -> dict[str, Any]:
    provenance = dict(record.get("provenance") or {})
    confidence = provenance.get("confidence")
    if isinstance(confidence, Mapping):
        score = confidence.get("confidence_score")
        source = confidence.get("confidence_source")
    else:
        score = provenance.get("confidence_score")
        source = provenance.get("confidence_source")
    if score is None:
        raise ValueError("confidence_score is required for cross-provider consumption")
    confidence_score = float(score)
    if confidence_score < 0.0 or confidence_score > 1.0:
        raise ValueError("confidence_score must be between 0 and 1")
    return {
        "confidence_score": confidence_score,
        "confidence_source": _required_text("confidence_source", source),
    }


def _retrieval_result_ref(pathfinder_retrieval_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "retrieval_result_id": _required_text(
            "retrieval_result_id",
            pathfinder_retrieval_result.get("retrieval_result_id"),
        ),
        "query_text": _required_text("query_text", pathfinder_retrieval_result.get("query_text")),
        "lifecycle_filter_mode": _required_text(
            "lifecycle_filter_mode",
            pathfinder_retrieval_result.get("lifecycle_filter_mode"),
        ),
        "source_ref_authority": _required_text(
            "source_ref_authority",
            pathfinder_retrieval_result.get("source_ref_authority"),
        ),
    }


def _consumed_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_record_id": _required_text("lifecycle_record_id", record.get("lifecycle_record_id")),
        "canonical_record_id": _required_text("canonical_record_id", record.get("canonical_record_id")),
        "lifecycle_state": _required_text("lifecycle_state", record.get("lifecycle_state")),
        "canonical_ref": dict(record.get("canonical_ref") or {}),
        "provider_provenance": _provider_provenance(record),
        "confidence": _confidence(record),
        "source_refs": _source_refs(record),
        "valid_from": _required_text("valid_from", record.get("valid_from")),
        "valid_until": record.get("valid_until"),
        "archive_trace_refs": [
            dict(ref)
            for ref in record.get("archive_trace_refs") or []
            if isinstance(ref, Mapping) and dict(ref)
        ],
    }


def _base_result(
    *,
    consumer_provider_id: str,
    consumer_provider_profile: str,
    consumer_session_uid: str,
    pathfinder_retrieval_result: Mapping[str, Any],
    status: str,
    stop_reason: str | None,
    consumed_records: list[dict[str, Any]],
    reason_codes: list[str],
) -> dict[str, Any]:
    result = {
        "schema_version": "cross_provider_memory_consumption_result.v1",
        "consumption_id": uuid.uuid4().hex,
        "consumer_provider_id": consumer_provider_id,
        "consumer_provider_profile": consumer_provider_profile,
        "consumer_session_uid": consumer_session_uid,
        "status": status,
        "stop_reason": stop_reason,
        "retrieval_result_ref": _retrieval_result_ref(pathfinder_retrieval_result),
        "consumed_records": consumed_records,
        "consumption_policy": {
            "provider_boundary": "cross_provider_only_with_explicit_provenance",
            "source_ref_policy": "required_forward_only",
            "confidence_policy": "required_at_retrieval_time",
            "lifecycle_policy": "visible_at_retrieval_time",
            "blind_global_bucket_policy": "rejected",
        },
        "blind_global_bucket_read": False,
        "reason_codes": reason_codes,
        "created_at": utc_now_iso(),
    }
    validate_cross_provider_memory_consumption_result(result)
    return result


def build_cross_provider_memory_consumption_result(
    *,
    consumer_provider_id: str,
    consumer_provider_profile: str,
    consumer_session_uid: str,
    pathfinder_retrieval_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a retrieval payload for cross-provider memory consumption.

    The function refuses blind global-bucket reads by consuming only lifecycle
    records already surfaced by Pathfinder and only when each cross-provider
    record carries explicit provider/session/source provenance plus confidence.
    """

    consumer_id = _required_text("consumer_provider_id", consumer_provider_id)
    consumer_profile = _required_text("consumer_provider_profile", consumer_provider_profile)
    session_uid = _required_text("consumer_session_uid", consumer_session_uid)
    validate_pathfinder_retrieval_result(pathfinder_retrieval_result)

    if pathfinder_retrieval_result.get("status") != "completed":
        return _base_result(
            consumer_provider_id=consumer_id,
            consumer_provider_profile=consumer_profile,
            consumer_session_uid=session_uid,
            pathfinder_retrieval_result=pathfinder_retrieval_result,
            status="stopped",
            stop_reason="pathfinder_retrieval_not_completed",
            consumed_records=[],
            reason_codes=[
                "pathfinder_retrieval_not_completed",
                "blind_global_bucket_read_rejected",
            ],
        )

    consumed: list[dict[str, Any]] = []
    for record in pathfinder_retrieval_result.get("lifecycle_records") or []:
        provider = _provider_provenance(record)
        if provider["provider_id"] == consumer_id:
            continue
        consumed.append(_consumed_record(record))

    if not consumed:
        return _base_result(
            consumer_provider_id=consumer_id,
            consumer_provider_profile=consumer_profile,
            consumer_session_uid=session_uid,
            pathfinder_retrieval_result=pathfinder_retrieval_result,
            status="stopped",
            stop_reason="no_cross_provider_records_with_explicit_provenance",
            consumed_records=[],
            reason_codes=[
                "no_cross_provider_records_with_explicit_provenance",
                "blind_global_bucket_read_rejected",
            ],
        )

    return _base_result(
        consumer_provider_id=consumer_id,
        consumer_provider_profile=consumer_profile,
        consumer_session_uid=session_uid,
        pathfinder_retrieval_result=pathfinder_retrieval_result,
        status="completed",
        stop_reason=None,
        consumed_records=consumed,
        reason_codes=[
            "cross_provider_records_consumed",
            "explicit_provider_provenance_visible",
            "confidence_visible",
            "lifecycle_state_visible",
            "blind_global_bucket_read_rejected",
        ],
    )
