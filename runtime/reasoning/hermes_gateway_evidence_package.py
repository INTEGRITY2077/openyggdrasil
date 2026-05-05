from __future__ import annotations

import json
import uuid
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from reasoning.hermes_provider_owned_gateway_contract import (
    build_p0_provider_owned_hermes_gateway_contract,
    validate_p0_provider_owned_hermes_gateway_contract,
)


CLASSIFIER_SCHEMA_VERSION = "p0_provider_owned_hermes_gateway_evidence_package_classifier.v1"

PASS_SAFE_PROVIDER_GATEWAY_EVIDENCE = "PASS_SAFE_PROVIDER_GATEWAY_EVIDENCE"
TYPED_UNAVAILABLE_LIVE_PROOF = "TYPED_UNAVAILABLE_LIVE_PROOF"
REJECT_UNSAFE_GATEWAY_CANDIDATE = "REJECT_UNSAFE_GATEWAY_CANDIDATE"

CLASSIFIER_VERDICTS = {
    PASS_SAFE_PROVIDER_GATEWAY_EVIDENCE,
    TYPED_UNAVAILABLE_LIVE_PROOF,
    REJECT_UNSAFE_GATEWAY_CANDIDATE,
}

CONTRACT_STATUS_TO_VERDICT = {
    "static_contract_ready": PASS_SAFE_PROVIDER_GATEWAY_EVIDENCE,
    "typed_unavailable": TYPED_UNAVAILABLE_LIVE_PROOF,
    "reject": REJECT_UNSAFE_GATEWAY_CANDIDATE,
}

REF_FIELDS_TO_RETURN = (
    "contract_ref",
    "typed_task_id",
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "provider_gateway_evidence_ref",
    "provider_gateway_proof_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)

SETUP_REPORT_PROOF_REF_FIELDS = (
    "typed_result_ref",
    "typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "provider_gateway_evidence_ref",
    "provider_gateway_proof_ref",
    "producer_receipt_ref",
    "consumer_usage_ref",
)

SETUP_REPORT_MARKERS = (
    "setup report",
    "setup-report",
    "setup_report",
    "runtime setup",
    "runtime-setup",
    "runtime_setup",
)


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _contains_setup_report_marker(value: Any) -> bool:
    lowered = str(value).lower()
    return any(marker in lowered for marker in SETUP_REPORT_MARKERS)


def _setup_report_relabeled_as_proof(candidate: Mapping[str, Any]) -> bool:
    for field in SETUP_REPORT_PROOF_REF_FIELDS:
        value = candidate.get(field)
        if value is not None and _contains_setup_report_marker(value):
            return True
    return False


def _candidate_for_contract(candidate: Mapping[str, Any]) -> dict[str, Any]:
    contract_candidate = dict(candidate)
    if _setup_report_relabeled_as_proof(contract_candidate):
        contract_candidate["setup_report_as_typed_proof"] = True
    return contract_candidate


def _typed_unavailable_classification(
    *,
    reason_code: str,
    unavailable_condition: str,
    source_kind: str,
) -> dict[str, Any]:
    package_id = uuid.uuid4().hex
    return {
        "schema_version": CLASSIFIER_SCHEMA_VERSION,
        "evidence_package_id": package_id,
        "verdict": TYPED_UNAVAILABLE_LIVE_PROOF,
        "source_kind": source_kind,
        "contract_status": "typed_unavailable",
        "unavailable_condition": unavailable_condition,
        "reject_condition": None,
        "reason_codes": [reason_code],
        "safety_reject_reasons": [],
        "contract": None,
        "safe_portable_refs": [
            f"typed-unavailable-ref://openyggdrasil/p0-g3/{package_id}"
        ],
        "provider_gateway_called": False,
        "raw_candidate_material_included": False,
        "static_classifier_only": True,
        "created_at": utc_now_iso(),
    }


def _load_json_candidate(path: str | PathLike[str]) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return None, "candidate_package_json_unavailable"
    except json.JSONDecodeError:
        return None, "candidate_package_json_invalid"
    if not isinstance(loaded, Mapping):
        return None, "candidate_package_json_not_object"
    return loaded, None


def _candidate_from_input(
    candidate_package: Mapping[str, Any] | str | PathLike[str],
) -> tuple[Mapping[str, Any] | None, str, str | None]:
    if isinstance(candidate_package, Mapping):
        return candidate_package, "mapping", None
    if isinstance(candidate_package, (str, PathLike)):
        candidate, load_error = _load_json_candidate(candidate_package)
        return candidate, "json_file", load_error
    return None, "unsupported", "unsupported_candidate_package_shape"


def classify_p0_provider_owned_hermes_gateway_evidence_package(
    candidate_package: Mapping[str, Any] | str | PathLike[str],
) -> dict[str, Any]:
    """Classify a candidate gateway evidence package through the P0-G2 contract.

    This is a static classifier. It never invokes Hermes, reads provider state,
    stores raw provider transcript/prompt material, or treats setup reports as
    gateway proof.
    """

    candidate, source_kind, input_error = _candidate_from_input(candidate_package)
    if input_error is not None:
        return _typed_unavailable_classification(
            reason_code=input_error,
            unavailable_condition=input_error,
            source_kind=source_kind,
        )

    try:
        contract = build_p0_provider_owned_hermes_gateway_contract(
            gateway_proof=_candidate_for_contract(candidate or {})
        )
        validate_p0_provider_owned_hermes_gateway_contract(contract)
    except Exception:
        return _typed_unavailable_classification(
            reason_code="p0_g2_contract_validation_failed",
            unavailable_condition="p0_g2_contract_validation_failed",
            source_kind=source_kind,
        )

    contract_status = str(contract.get("gateway_status") or "")
    verdict = CONTRACT_STATUS_TO_VERDICT.get(contract_status, TYPED_UNAVAILABLE_LIVE_PROOF)
    unavailable_condition = contract.get("unavailable_condition")
    reject_condition = contract.get("reject_condition")
    reason_codes = _string_list(contract.get("reason_codes"))
    safety_reject_reasons = _string_list(contract.get("safety_reject_reasons"))

    refs = [
        str(contract[field])
        for field in REF_FIELDS_TO_RETURN
        if contract.get(field) is not None
    ]

    return {
        "schema_version": CLASSIFIER_SCHEMA_VERSION,
        "evidence_package_id": uuid.uuid4().hex,
        "verdict": verdict,
        "source_kind": source_kind,
        "contract_status": contract_status,
        "unavailable_condition": unavailable_condition,
        "reject_condition": reject_condition,
        "reason_codes": reason_codes,
        "safety_reject_reasons": safety_reject_reasons,
        "contract": contract,
        "safe_portable_refs": refs,
        "provider_gateway_called": False,
        "raw_candidate_material_included": False,
        "static_classifier_only": True,
        "created_at": utc_now_iso(),
    }


def validate_p0_provider_owned_hermes_gateway_evidence_classification(
    classification: Mapping[str, Any],
) -> None:
    if classification.get("schema_version") != CLASSIFIER_SCHEMA_VERSION:
        raise ValueError("invalid P0 gateway evidence classifier schema_version")
    if classification.get("verdict") not in CLASSIFIER_VERDICTS:
        raise ValueError("invalid P0 gateway evidence classifier verdict")
    if classification.get("provider_gateway_called") is not False:
        raise ValueError("P0 gateway evidence classifier must not call provider gateway")
    if classification.get("raw_candidate_material_included") is not False:
        raise ValueError("P0 gateway evidence classifier must not include raw candidate material")

    contract = classification.get("contract")
    if contract is not None:
        if not isinstance(contract, Mapping):
            raise ValueError("P0 gateway evidence classifier contract must be mapping or null")
        validate_p0_provider_owned_hermes_gateway_contract(contract)

    verdict = classification.get("verdict")
    contract_status = classification.get("contract_status")
    if verdict == PASS_SAFE_PROVIDER_GATEWAY_EVIDENCE and contract_status != "static_contract_ready":
        raise ValueError("P0 gateway evidence PASS requires static contract ready")
    if verdict == TYPED_UNAVAILABLE_LIVE_PROOF and contract_status != "typed_unavailable":
        raise ValueError("P0 gateway evidence typed unavailable requires typed_unavailable contract")
    if verdict == REJECT_UNSAFE_GATEWAY_CANDIDATE and contract_status != "reject":
        raise ValueError("P0 gateway evidence reject requires reject contract")
