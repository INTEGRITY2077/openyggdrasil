from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from reasoning.reasoning_lease_contracts import validate_reasoning_lease_request, validate_reasoning_lease_result


WORKER_HARDENING_POLICY_VERSION = "worker-hardening-policy.v1"
DEFAULT_PREVIEW_MAX_CHARS = 512

DEFAULT_WORKER_TOOL_ALLOWLIST = (
    "read_input_source_refs",
    "emit_structured_lease_result",
    "write_result_source_ref",
)

REQUIRED_WORKER_CONSTRAINTS = (
    "scoped_tool_allowlist_required",
    "recursive_reasoning_lease_spawning_disabled",
    "structured_result_envelope_required",
    "bounded_preview_required",
    "source_ref_and_digest_required",
    "no_raw_worker_trace_or_tool_output_copy",
)

RAW_MATERIAL_FLAGS = (
    "raw_transcript_copied",
    "raw_session_copied",
    "state_db_result_harvested",
    "foreground_context_appended",
    "raw_worker_prompt_copied",
    "raw_worker_trace_copied",
    "raw_tool_output_copied",
    "raw_lease_result_payload_copied",
)


@dataclass(frozen=True)
class WorkerHardeningPolicy:
    schema_version: str
    tool_allowlist: tuple[str, ...]
    recursive_lease_spawning_allowed_by_default: bool
    structured_result_envelope_required: bool
    preview_max_chars: int
    required_constraints: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_allowlist": list(self.tool_allowlist),
            "recursive_lease_spawning_allowed_by_default": self.recursive_lease_spawning_allowed_by_default,
            "structured_result_envelope_required": self.structured_result_envelope_required,
            "preview_max_chars": self.preview_max_chars,
            "required_constraints": list(self.required_constraints),
        }


@dataclass(frozen=True)
class WorkerHardeningEvaluation:
    schema_version: str
    ok: bool
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "reason_codes": list(self.reason_codes),
        }


def build_worker_hardening_policy() -> WorkerHardeningPolicy:
    return WorkerHardeningPolicy(
        schema_version=WORKER_HARDENING_POLICY_VERSION,
        tool_allowlist=DEFAULT_WORKER_TOOL_ALLOWLIST,
        recursive_lease_spawning_allowed_by_default=False,
        structured_result_envelope_required=True,
        preview_max_chars=DEFAULT_PREVIEW_MAX_CHARS,
        required_constraints=REQUIRED_WORKER_CONSTRAINTS,
    )


def worker_hardening_constraints(existing_constraints: Iterable[str] = ()) -> list[str]:
    constraints: list[str] = []
    for constraint in tuple(existing_constraints) + REQUIRED_WORKER_CONSTRAINTS:
        value = str(constraint).strip()
        if value and value not in constraints:
            constraints.append(value)
    return constraints


def evaluate_worker_lease_request(request: Mapping[str, Any]) -> WorkerHardeningEvaluation:
    validate_reasoning_lease_request(request)
    constraints = {str(value) for value in request.get("constraints") or []}
    reason_codes: list[str] = []
    for required_constraint in REQUIRED_WORKER_CONSTRAINTS:
        if required_constraint not in constraints:
            reason_codes.append(f"missing_constraint:{required_constraint}")
    return WorkerHardeningEvaluation(
        schema_version=WORKER_HARDENING_POLICY_VERSION,
        ok=not reason_codes,
        reason_codes=tuple(reason_codes),
    )


def evaluate_worker_lease_result(result: Mapping[str, Any]) -> WorkerHardeningEvaluation:
    validate_reasoning_lease_result(result)
    reason_codes: list[str] = []
    output = dict(result.get("output") or {})

    if result.get("lease_status") != "completed":
        return WorkerHardeningEvaluation(
            schema_version=WORKER_HARDENING_POLICY_VERSION,
            ok=True,
            reason_codes=("non_completed_lease_result_not_staged_as_worker_output",),
        )

    if not result.get("worker_ref") and not output.get("worker_ref"):
        reason_codes.append("missing_worker_ref")
    if not output.get("schema_version"):
        reason_codes.append("missing_structured_result_envelope_schema_version")
    if not output.get("result_source_ref"):
        reason_codes.append("missing_result_source_ref")
    if not output.get("result_digest_sha256"):
        reason_codes.append("missing_result_digest_sha256")
    if not output.get("source_refs"):
        reason_codes.append("missing_or_empty_source_refs")
    if output.get("recursive_lease_spawning_allowed") is True:
        reason_codes.append("recursive_lease_spawning_not_allowed_by_default")

    preview_max_chars = int(output.get("preview_max_chars") or DEFAULT_PREVIEW_MAX_CHARS)
    result_preview = output.get("result_preview")
    if preview_max_chars > DEFAULT_PREVIEW_MAX_CHARS:
        reason_codes.append("preview_budget_exceeds_default_max")
    if isinstance(result_preview, str) and len(result_preview) > preview_max_chars:
        reason_codes.append("result_preview_exceeds_budget")

    for flag_name in RAW_MATERIAL_FLAGS:
        if output.get(flag_name) is True:
            reason_codes.append(f"raw_material_flag_set:{flag_name}")

    return WorkerHardeningEvaluation(
        schema_version=WORKER_HARDENING_POLICY_VERSION,
        ok=not reason_codes,
        reason_codes=tuple(reason_codes),
    )
