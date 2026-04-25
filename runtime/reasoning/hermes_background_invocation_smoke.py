from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from attachments.provider_attachment import validate_provider_descriptor
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"

COMMON_RESULT_EVALUATION_REF = (
    "D:\\0_PROJECT\\codex\\automation\\2026-04-25-6\\"
    "phase-4-common-result-sot-evaluation.md"
)
HERMES_BACKGROUND_DESCRIPTOR_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-hermes-background-capability-descriptor.md"
)

P4_H1_ACTION = "P4.H1.hermes-background-explicit-invocation-smoke"
P4_H2_ACTION = "P4.H2.hermes-background-task-id-capture"

REQUIRED_GATEWAY_MARKERS = (
    "gateway_background_command_handler",
    "gateway_background_task_spawn",
    "gateway_bg_task_id_prefix",
    "gateway_active_history_non_append_policy",
    "gateway_background_command_test",
)

DEFAULT_SAFETY_FLAGS = {
    "foreground_injection": False,
    "raw_session_copied": False,
    "state_db_result_harvested": False,
    "openyggdrasil_credentials_requested": False,
    "main_active_conversation_appended": False,
}

UNSAFE_REASON_CODES = {
    "foreground_injection": "stealth_foreground_injection_not_allowed",
    "raw_session_copied": "raw_provider_session_copy_not_allowed",
    "state_db_result_harvested": "state_db_result_harvesting_not_allowed",
    "openyggdrasil_credentials_requested": "openyggdrasil_credential_request_not_allowed",
    "main_active_conversation_appended": "main_active_conversation_append_not_allowed",
}


@lru_cache(maxsize=1)
def load_hermes_background_invocation_smoke_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_background_invocation_smoke.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_background_invocation_smoke(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_background_invocation_smoke_schema(),
    )


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _has_all(text: str, needles: Sequence[str]) -> bool:
    return all(needle in text for needle in needles)


def scan_hermes_background_reference_root(reference_root: str | Path) -> dict[str, Any]:
    """Read Hermes reference code markers without touching provider runtime state."""

    root = Path(reference_root)
    gateway_run = root / "gateway" / "run.py"
    cli_py = root / "cli.py"
    gateway_test = root / "tests" / "gateway" / "test_background_command.py"

    gateway_text = _read_text(gateway_run)
    cli_text = _read_text(cli_py)
    gateway_test_text = _read_text(gateway_test)

    source_refs = [
        str(path)
        for path in (gateway_run, cli_py, gateway_test)
        if path.exists() and path.is_file()
    ]

    markers = {
        "gateway_background_command_handler": _has_all(
            gateway_text,
            (
                "async def _handle_background_command",
                "/background <prompt>",
            ),
        ),
        "gateway_background_task_spawn": _has_all(
            gateway_text,
            (
                "asyncio.create_task",
                "_run_background_task(prompt, source, task_id)",
            ),
        ),
        "gateway_bg_task_id_prefix": 'task_id = f"bg_' in gateway_text,
        "gateway_active_history_non_append_policy": _has_all(
            gateway_text,
            (
                "without",
                "modifying",
                "active session",
                "conversation history",
            ),
        ),
        "gateway_background_command_test": _has_all(
            gateway_test_text,
            (
                "test_valid_prompt_starts_task",
                "Background task started",
                "bg_",
            ),
        ),
        "cli_background_command_handler": _has_all(
            cli_text,
            (
                "def _handle_background_command",
                "/background <prompt>",
            ),
        ),
        "cli_background_thread_spawn": _has_all(
            cli_text,
            (
                "threading.Thread",
                "bg-task-{task_id}",
            ),
        ),
        "cli_bg_task_id_prefix": 'task_id = f"bg_' in cli_text,
    }

    return {
        "reference_root": str(root),
        "source_refs": source_refs,
        "markers": markers,
    }


def _background_descriptor(provider_descriptor: Mapping[str, Any]) -> Mapping[str, Any]:
    capabilities = provider_descriptor.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return {}
    detail = capabilities.get("background_reasoning_descriptor")
    return detail if isinstance(detail, Mapping) else {}


def _descriptor_allows_hermes_background_candidate(provider_descriptor: Mapping[str, Any]) -> bool:
    detail = _background_descriptor(provider_descriptor)
    return (
        provider_descriptor.get("provider_id") == "hermes"
        and detail.get("provider_surface") == "hermes_background_command"
        and detail.get("support_status") == "adapted_candidate"
        and detail.get("completion_status") == "not_proven"
        and detail.get("live_proof_required") is True
        and detail.get("invocation_surface") == "provider_owned_command_gateway"
    )


def _first_unsafe_reason(safety: Mapping[str, bool]) -> str | None:
    for flag_name, reason_code in UNSAFE_REASON_CODES.items():
        if safety.get(flag_name) is True:
            return reason_code
    return None


def build_hermes_background_invocation_smoke(
    *,
    provider_descriptor: Mapping[str, Any],
    reference_scan: Mapping[str, Any],
    evidence_refs: Sequence[str] = (
        COMMON_RESULT_EVALUATION_REF,
        HERMES_BACKGROUND_DESCRIPTOR_REF,
    ),
    safety_flags: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a P4.H1 smoke proof for the explicit Hermes /background surface.

    This is a static invocation-surface smoke, not a live provider run and not a
    completed reasoning lease result.
    """

    validate_provider_descriptor(provider_descriptor)
    markers = dict(reference_scan.get("markers") or {})
    source_refs = [str(ref) for ref in evidence_refs]
    source_refs.extend(str(ref) for ref in reference_scan.get("source_refs") or [])

    safety = dict(DEFAULT_SAFETY_FLAGS)
    safety.update(dict(safety_flags or {}))
    reason_code = _first_unsafe_reason(safety)

    missing_gateway_marker = not all(markers.get(marker) is True for marker in REQUIRED_GATEWAY_MARKERS)
    descriptor_ready = _descriptor_allows_hermes_background_candidate(provider_descriptor)

    if reason_code is not None:
        smoke_status = "blocked_unsafe_surface"
    elif not descriptor_ready:
        smoke_status = "typed_unavailable"
        reason_code = "hermes_background_candidate_descriptor_not_ready"
    elif missing_gateway_marker:
        smoke_status = "typed_unavailable"
        reason_code = "explicit_gateway_background_markers_missing"
    else:
        smoke_status = "explicit_surface_static_proven"

    explicit_surface = smoke_status == "explicit_surface_static_proven"
    payload = {
        "schema_version": "hermes_background_invocation_smoke.v1",
        "smoke_id": uuid.uuid4().hex,
        "provider_id": str(provider_descriptor.get("provider_id")),
        "provider_profile": str(provider_descriptor.get("provider_profile")),
        "provider_session_id": str(provider_descriptor.get("provider_session_id")),
        "smoke_status": smoke_status,
        "reason_code": reason_code,
        "command": "/background",
        "invocation_surface": "provider_owned_command_gateway" if explicit_surface else "none",
        "execution_mode": "static_reference_smoke" if explicit_surface else "not_executed",
        "live_provider_invoked": False,
        "lease_completion_claimed": False,
        "task_ref_status": (
            "bg_prefix_static_marker_present"
            if markers.get("gateway_bg_task_id_prefix") is True
            else "unavailable"
        ),
        "source_markers": markers,
        "safety": safety,
        "source_refs": source_refs[:16],
        "next_action": P4_H2_ACTION if explicit_surface else P4_H1_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_background_invocation_smoke(payload)
    return payload
