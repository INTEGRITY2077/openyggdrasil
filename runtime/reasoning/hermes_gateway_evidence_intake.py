from __future__ import annotations

import hashlib
import json
import uuid
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_common import utc_now_iso
from reasoning.hermes_gateway_evidence_package import (
    CLASSIFIER_SCHEMA_VERSION,
    CLASSIFIER_VERDICTS,
    TYPED_UNAVAILABLE_LIVE_PROOF,
    classify_p0_official_hermes_gateway_evidence_package,
    classify_p0_provider_owned_hermes_gateway_evidence_package,
    validate_p0_official_hermes_gateway_evidence_classification,
    validate_p0_provider_owned_hermes_gateway_evidence_classification,
)


INTAKE_SCHEMA_VERSION = "p0_provider_owned_hermes_gateway_evidence_intake.v1"

RAW_MATERIAL_KEYS = {
    "candidate",
    "candidate_json",
    "credential",
    "credential_material",
    "env_exports",
    "foreground_env_injection",
    "private_env_injection",
    "profile_material",
    "provider_credential",
    "provider_material",
    "provider_profile",
    "provider_state_db",
    "raw_candidate",
    "raw_prompt",
    "raw_provider_material",
    "raw_provider_task_output",
    "raw_session_transcript",
    "raw_transcript",
    "state_db_material",
    "stdin_injection",
    "transcript_text",
}


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _path_fingerprint(path: Path) -> str:
    normalized = str(path.resolve(strict=False)).replace("\\", "/").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _safe_source_ref(candidate_path: Path, source_ref: str | None = None) -> str:
    if source_ref and "://" in source_ref and "\\" not in source_ref:
        lowered = source_ref.lower()
        if not any(fragment in lowered for fragment in ("state.db", ".env", "transcript", "prompt")):
            return source_ref
    return f"candidate-json-ref://openyggdrasil/p0-g4/{_path_fingerprint(candidate_path)}"


def _typed_unavailable_classification(reason_code: str) -> dict[str, Any]:
    intake_id = uuid.uuid4().hex
    return {
        "schema_version": CLASSIFIER_SCHEMA_VERSION,
        "evidence_package_id": intake_id,
        "verdict": TYPED_UNAVAILABLE_LIVE_PROOF,
        "source_kind": "json_file",
        "contract_status": "typed_unavailable",
        "unavailable_condition": reason_code,
        "reject_condition": None,
        "reason_codes": [reason_code],
        "safety_reject_reasons": [],
        "contract": None,
        "safe_portable_refs": [
            f"typed-unavailable-ref://openyggdrasil/p0-g4/{intake_id}"
        ],
        "provider_gateway_called": False,
        "raw_candidate_material_included": False,
        "static_classifier_only": True,
        "created_at": utc_now_iso(),
    }


def _load_candidate_json(candidate_path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        loaded = json.loads(candidate_path.read_text(encoding="utf-8"))
    except OSError:
        return None, "candidate_package_json_unavailable"
    except json.JSONDecodeError:
        return None, "candidate_package_json_invalid"
    if not isinstance(loaded, Mapping):
        return None, "candidate_package_json_not_object"
    return loaded, None


def _redacted_artifact(
    *,
    candidate_path: Path,
    classification: Mapping[str, Any],
    source_ref: str | None = None,
) -> dict[str, Any]:
    artifact = {
        "schema_version": INTAKE_SCHEMA_VERSION,
        "intake_id": uuid.uuid4().hex,
        "source_ref": _safe_source_ref(candidate_path, source_ref),
        "classifier_schema_version": CLASSIFIER_SCHEMA_VERSION,
        "classification_id": classification.get("evidence_package_id"),
        "verdict": classification.get("verdict"),
        "contract_status": classification.get("contract_status"),
        "reason_codes": _string_list(classification.get("reason_codes")),
        "unavailable_condition": classification.get("unavailable_condition"),
        "reject_condition": classification.get("reject_condition"),
        "safety_reject_reasons": _string_list(classification.get("safety_reject_reasons")),
        "safe_portable_refs": _string_list(classification.get("safe_portable_refs")),
        "created_at": utc_now_iso(),
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_candidate_material_included": False,
        "raw_provider_material_included": False,
        "redacted": True,
        "static_intake_only": True,
    }
    validate_p0_provider_owned_hermes_gateway_evidence_intake(artifact)
    return artifact


def run_p0_provider_owned_hermes_gateway_evidence_intake(
    candidate_json_path: str | PathLike[str],
    *,
    output_path: str | PathLike[str] | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Classify a candidate JSON file and optionally write a redacted artifact.

    Candidate JSON is treated as data, not instructions. The runner does not
    call Hermes, execute candidate-provided commands, read provider state, or
    persist raw candidate/provider material.
    """

    candidate_path = Path(candidate_json_path)
    candidate, load_error = _load_candidate_json(candidate_path)
    if load_error is not None:
        classification = _typed_unavailable_classification(load_error)
    else:
        classification = classify_p0_provider_owned_hermes_gateway_evidence_package(candidate or {})
    validate_p0_provider_owned_hermes_gateway_evidence_classification(classification)

    artifact = _redacted_artifact(
        candidate_path=candidate_path,
        classification=classification,
        source_ref=source_ref,
    )

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return artifact


def run_p0_official_hermes_gateway_evidence_intake(
    candidate_json_path: str | PathLike[str],
    *,
    output_path: str | PathLike[str] | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Compatibility alias for the older P0 "official Hermes gateway" wording."""

    candidate_path = Path(candidate_json_path)
    candidate, load_error = _load_candidate_json(candidate_path)
    if load_error is not None:
        classification = _typed_unavailable_classification(load_error)
    else:
        classification = classify_p0_official_hermes_gateway_evidence_package(candidate or {})
    validate_p0_official_hermes_gateway_evidence_classification(classification)
    artifact = _redacted_artifact(
        candidate_path=candidate_path,
        classification=classification,
        source_ref=source_ref,
    )
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return artifact


def validate_p0_provider_owned_hermes_gateway_evidence_intake(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") != INTAKE_SCHEMA_VERSION:
        raise ValueError("invalid P0 gateway evidence intake schema_version")
    if artifact.get("classifier_schema_version") != CLASSIFIER_SCHEMA_VERSION:
        raise ValueError("invalid P0 gateway evidence intake classifier schema_version")
    if artifact.get("verdict") not in CLASSIFIER_VERDICTS:
        raise ValueError("invalid P0 gateway evidence intake verdict")
    if artifact.get("provider_gateway_called") is not False:
        raise ValueError("P0 gateway evidence intake must not call Hermes")
    if artifact.get("provider_state_read") is not False:
        raise ValueError("P0 gateway evidence intake must not read provider state")
    if artifact.get("raw_candidate_material_included") is not False:
        raise ValueError("P0 gateway evidence intake must not include raw candidate material")
    if artifact.get("raw_provider_material_included") is not False:
        raise ValueError("P0 gateway evidence intake must not include raw provider material")
    if artifact.get("redacted") is not True:
        raise ValueError("P0 gateway evidence intake artifact must be redacted")
    if artifact.get("static_intake_only") is not True:
        raise ValueError("P0 gateway evidence intake must remain static-only")
    for raw_key in RAW_MATERIAL_KEYS:
        if raw_key in artifact:
            raise ValueError(f"P0 gateway evidence intake raw material key present: {raw_key}")


def validate_p0_official_hermes_gateway_evidence_intake(artifact: Mapping[str, Any]) -> None:
    """Compatibility alias for the older P0 "official Hermes gateway" wording."""

    validate_p0_provider_owned_hermes_gateway_evidence_intake(artifact)
