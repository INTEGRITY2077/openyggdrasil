from __future__ import annotations

from typing import Any, Mapping, Sequence

from cultivation.vault_record_lifecycle import validate_vault_record_lifecycle


ACTIVE_LIFECYCLE_STATE = "ACTIVE"
EXCLUDED_RETRIEVAL_LIFECYCLE_STATES = {"STALE", "SUPERSEDED"}


def _lifecycle_ref(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_record_id": str(record["lifecycle_record_id"]),
        "canonical_record_id": str(record["canonical_record_id"]),
        "lifecycle_state": str(record["lifecycle_state"]),
        "canonical_ref": dict(record["canonical_ref"]),
        "source_refs": [dict(ref) for ref in record["source_refs"]],
        "provenance": dict(record["provenance"]),
        "valid_from": record.get("valid_from"),
        "valid_until": record.get("valid_until"),
        "invalidated_by": dict(record["invalidated_by"]) if isinstance(record.get("invalidated_by"), Mapping) else None,
        "superseded_by": record.get("superseded_by"),
        "superseded_at": record.get("superseded_at"),
        "supersession_reason": record.get("supersession_reason"),
        "archive_trace_refs": [dict(ref) for ref in record["archive_trace_refs"]],
    }

def filter_lifecycle_records_for_retrieval(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    include_historical: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    filtered_inactive = 0
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        lifecycle_state = str(record.get("lifecycle_state") or "")
        if lifecycle_state != ACTIVE_LIFECYCLE_STATE and not include_historical:
            filtered_inactive += 1
            continue
        selected.append(_lifecycle_ref(record))
    return selected, filtered_inactive

def _lifecycle_rejection_reason(record: Mapping[str, Any]) -> dict[str, Any] | None:
    lifecycle_state = str(record.get("lifecycle_state") or "")
    if lifecycle_state == "SUPERSEDED":
        return {
            "canonical_record_id": str(record["canonical_record_id"]),
            "lifecycle_state": lifecycle_state,
            "reason_code": "superseded_record_filtered",
            "reason": str(record.get("supersession_reason") or "").strip(),
            "superseded_by": record.get("superseded_by"),
            "invalidated_by": dict(record["invalidated_by"])
            if isinstance(record.get("invalidated_by"), Mapping)
            else None,
        }
    if lifecycle_state == "STALE":
        return {
            "canonical_record_id": str(record["canonical_record_id"]),
            "lifecycle_state": lifecycle_state,
            "reason_code": "stale_record_filtered",
            "reason": str(record.get("supersession_reason") or "").strip(),
            "superseded_by": None,
            "invalidated_by": dict(record["invalidated_by"])
            if isinstance(record.get("invalidated_by"), Mapping)
            else None,
        }
    return None

def measure_lifecycle_rejection_ux_metrics(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    include_historical: bool = False,
) -> dict[str, Any]:
    """Measure UX-FS-04 lifecycle filtering and rejection visibility."""

    selected, inactive_filtered = filter_lifecycle_records_for_retrieval(
        lifecycle_records,
        include_historical=include_historical,
    )
    selected_states = [str(record.get("lifecycle_state") or "") for record in selected]
    stale_false_accept_count = selected_states.count("STALE")
    superseded_false_accept_count = selected_states.count("SUPERSEDED")

    rejection_reasons: list[dict[str, Any]] = []
    rejected_lifecycle_record_count = 0
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        lifecycle_state = str(record.get("lifecycle_state") or "")
        if lifecycle_state == ACTIVE_LIFECYCLE_STATE or include_historical:
            continue
        rejected_lifecycle_record_count += 1
        reason = _lifecycle_rejection_reason(record)
        if reason and reason["reason"] and reason["invalidated_by"]:
            rejection_reasons.append(reason)

    if rejected_lifecycle_record_count:
        rejection_reason_coverage: float | str = len(rejection_reasons) / rejected_lifecycle_record_count
    else:
        rejection_reason_coverage = "not_applicable"

    decision = (
        "green_passed"
        if (
            stale_false_accept_count == 0
            and superseded_false_accept_count == 0
            and (
                rejection_reason_coverage == 1.0
                or rejection_reason_coverage == "not_applicable"
            )
        )
        else "red_captured"
    )

    return {
        "surface_id": "UX-FS-04",
        "lifecycle_filter_mode": "historical_including_inactive"
        if include_historical
        else "active_only",
        "stale_false_accept_count": stale_false_accept_count,
        "superseded_false_accept_count": superseded_false_accept_count,
        "rejected_lifecycle_record_count": rejected_lifecycle_record_count,
        "rejection_reason_coverage": rejection_reason_coverage,
        "inactive_records_filtered": inactive_filtered,
        "rejection_reasons": rejection_reasons,
        "decision": decision,
    }

def measure_historical_intent_discriminator_metrics(
    lifecycle_records: Sequence[Mapping[str, Any]] | None,
    *,
    historical_intent: bool,
    selected_lifecycle_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure whether inactive memory is used only for historical-intent retrieval."""

    source_records: list[Mapping[str, Any]] = []
    for record in lifecycle_records or []:
        validate_vault_record_lifecycle(record)
        source_records.append(record)

    if selected_lifecycle_records is None:
        selected_records, _ = filter_lifecycle_records_for_retrieval(
            source_records,
            include_historical=historical_intent,
        )
    else:
        selected_records = [dict(record) for record in selected_lifecycle_records]

    candidate_inactive_ids = {
        str(record.get("canonical_record_id") or "")
        for record in source_records
        if str(record.get("lifecycle_state") or "") in EXCLUDED_RETRIEVAL_LIFECYCLE_STATES
    }
    selected_inactive_records = [
        record
        for record in selected_records
        if str(record.get("lifecycle_state") or "") in EXCLUDED_RETRIEVAL_LIFECYCLE_STATES
    ]
    selected_inactive_ids = {
        str(record.get("canonical_record_id") or "")
        for record in selected_inactive_records
    }
    stale_selected_count = sum(
        1 for record in selected_inactive_records if str(record.get("lifecycle_state") or "") == "STALE"
    )
    superseded_selected_count = sum(
        1 for record in selected_inactive_records if str(record.get("lifecycle_state") or "") == "SUPERSEDED"
    )
    stale_false_accept_count = 0 if historical_intent else stale_selected_count
    superseded_false_accept_count = 0 if historical_intent else superseded_selected_count
    historical_records_included = len(selected_inactive_records) if historical_intent else 0
    historical_context_missing_count = (
        max(0, len(candidate_inactive_ids - selected_inactive_ids))
        if historical_intent
        else 0
    )
    inactive_records_filtered = len(candidate_inactive_ids - selected_inactive_ids)

    if historical_records_included:
        visible_historical_records = sum(
            1
            for record in selected_inactive_records
            if record.get("source_refs") and record.get("provenance")
        )
        historical_evidence_visibility: float | str = visible_historical_records / historical_records_included
    else:
        historical_evidence_visibility = "not_applicable"

    if historical_intent:
        decision = (
            "green_passed"
            if (
                stale_false_accept_count == 0
                and superseded_false_accept_count == 0
                and historical_context_missing_count == 0
                and (
                    historical_evidence_visibility == 1.0
                    or historical_evidence_visibility == "not_applicable"
                )
            )
            else "red_captured"
        )
    else:
        decision = (
            "green_passed"
            if stale_false_accept_count == 0 and superseded_false_accept_count == 0
            else "red_captured"
        )

    return {
        "surface_id": "UX-FS-04",
        "scenario_id": "P9-S08",
        "intent_mode": "historical" if historical_intent else "current_truth",
        "historical_intent": historical_intent,
        "inactive_candidate_count": len(candidate_inactive_ids),
        "historical_records_included": historical_records_included,
        "historical_context_missing_count": historical_context_missing_count,
        "inactive_records_filtered": inactive_records_filtered,
        "stale_false_accept_count": stale_false_accept_count,
        "superseded_false_accept_count": superseded_false_accept_count,
        "historical_evidence_visibility": historical_evidence_visibility,
        "decision": decision,
    }
