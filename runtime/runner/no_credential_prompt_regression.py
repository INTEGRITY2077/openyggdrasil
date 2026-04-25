from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"

PROVIDER_DECLINED_VISIBILITY_REF = (
    "D:\\0_PROJECT\\openyggdrasil\\history\\core\\2026-04-25\\"
    "2026-04-25_phase-4-provider-declined-runner-visibility.md"
)

P4_CR1_ACTION = "P4.CR1.phase-close-code-review"

BOOLEAN_PROMPT_KEYS = {
    "credential_prompted": "credential_prompt",
    "api_key_prompted": "api_key_prompt",
    "apikey_prompted": "api_key_prompt",
    "oauth_prompted": "oauth_prompt",
    "stored_credential_requested": "stored_credential_request",
}

TEXT_PROMPT_KEYS = {
    "credential_prompt": "credential_prompt",
    "credential_prompt_text": "credential_prompt",
    "credential_request": "credential_prompt",
    "api_key_prompt": "api_key_prompt",
    "api_key_request": "api_key_prompt",
    "apikey_prompt": "api_key_prompt",
    "oauth_prompt": "oauth_prompt",
    "oauth_prompt_url": "oauth_prompt",
    "oauth_url": "oauth_prompt",
    "stored_credential_request": "stored_credential_request",
}

TEXT_PROMPT_PATTERNS = {
    "enter api key": "api_key_prompt",
    "provide api key": "api_key_prompt",
    "paste api key": "api_key_prompt",
    "enter your api key": "api_key_prompt",
    "oauth login": "oauth_prompt",
    "authorize oauth": "oauth_prompt",
    "please enter credential": "credential_prompt",
    "provide credential": "credential_prompt",
    "paste credential": "credential_prompt",
    "use stored credential": "stored_credential_request",
}

FALSE_FLAG_KEYS = {
    "credential_prompted",
    "api_key_prompted",
    "apikey_prompted",
    "oauth_prompted",
    "raw_session_copied",
    "foreground_context_appended",
}


@lru_cache(maxsize=1)
def load_no_credential_prompt_regression_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "no_credential_prompt_regression_result.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_no_credential_prompt_regression(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_no_credential_prompt_regression_schema(),
    )


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _prompt_kind_for_text(value: str) -> list[str]:
    normalized = value.lower()
    return _unique(
        [
            prompt_kind
            for pattern, prompt_kind in TEXT_PROMPT_PATTERNS.items()
            if pattern in normalized
        ]
    )


def _scan_surface(value: Any, *, path: str = "$") -> tuple[list[str], list[str], list[str]]:
    prompt_kinds: list[str] = []
    false_flags: list[str] = []
    constraints: list[str] = []

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).lower()
            if normalized_key == "constraints" and isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                constraints.extend(str(item) for item in child if str(item).strip())

            if normalized_key in BOOLEAN_PROMPT_KEYS:
                if child is True:
                    prompt_kinds.append(BOOLEAN_PROMPT_KEYS[normalized_key])
                elif child is False and normalized_key in FALSE_FLAG_KEYS:
                    false_flags.append(f"{normalized_key}=false")

            if normalized_key in TEXT_PROMPT_KEYS and child not in (None, False, "", [], {}):
                prompt_kinds.append(TEXT_PROMPT_KEYS[normalized_key])

            child_prompts, child_false_flags, child_constraints = _scan_surface(
                child,
                path=f"{path}.{key}",
            )
            prompt_kinds.extend(child_prompts)
            false_flags.extend(child_false_flags)
            constraints.extend(child_constraints)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prompts, child_false_flags, child_constraints = _scan_surface(
                child,
                path=f"{path}[{index}]",
            )
            prompt_kinds.extend(child_prompts)
            false_flags.extend(child_false_flags)
            constraints.extend(child_constraints)
    elif isinstance(value, str):
        prompt_kinds.extend(_prompt_kind_for_text(value))

    return _unique(prompt_kinds), _unique(false_flags), _unique(constraints)


def build_no_credential_prompt_regression_result(
    surfaces: Sequence[Mapping[str, Any]],
    *,
    evidence_refs: Sequence[str] = (PROVIDER_DECLINED_VISIBILITY_REF,),
) -> dict[str, Any]:
    """Scan runtime-facing Phase 4 payloads for credential/API/OAuth prompts."""

    surface_results: list[dict[str, Any]] = []
    all_prompt_kinds: list[str] = []
    all_false_flags: list[str] = []
    all_constraints: list[str] = []

    for index, surface in enumerate(surfaces):
        surface_id = str(surface.get("schema_version") or surface.get("producer_role") or f"surface_{index}")
        prompt_kinds, false_flags, constraints = _scan_surface(surface)
        all_prompt_kinds.extend(prompt_kinds)
        all_false_flags.extend(false_flags)
        all_constraints.extend(constraints)
        surface_results.append(
            {
                "surface_id": surface_id[:160],
                "status": "failed" if prompt_kinds else "passed",
                "prompt_attempt_kinds": _unique(prompt_kinds),
                "explicit_false_flags": _unique(false_flags),
            }
        )

    prompt_attempt_kinds = _unique(all_prompt_kinds)
    prompt_attempt_count = sum(len(row["prompt_attempt_kinds"]) for row in surface_results)
    status = "failed" if prompt_attempt_kinds else "passed"
    payload = {
        "schema_version": "no_credential_prompt_regression_result.v1",
        "regression_id": uuid.uuid4().hex,
        "status": status,
        "scanned_surface_count": len(surface_results),
        "surface_results": surface_results,
        "runtime_boundary_constraints": _unique(all_constraints),
        "explicit_false_flags": _unique(all_false_flags),
        "prompt_attempt_count": prompt_attempt_count,
        "prompt_attempt_kinds": prompt_attempt_kinds,
        "credential_prompt_detected": "credential_prompt" in prompt_attempt_kinds,
        "api_key_prompt_detected": "api_key_prompt" in prompt_attempt_kinds,
        "oauth_prompt_detected": "oauth_prompt" in prompt_attempt_kinds,
        "stored_credential_request_detected": "stored_credential_request" in prompt_attempt_kinds,
        "openyggdrasil_owned_credentials_required": False,
        "credential_prompted": False,
        "api_key_prompted": False,
        "oauth_prompted": False,
        "raw_session_copied": False,
        "foreground_context_appended": False,
        "source_refs": [str(ref) for ref in evidence_refs][:32],
        "next_action": P4_CR1_ACTION,
        "checked_at": utc_now_iso(),
    }
    validate_no_credential_prompt_regression(payload)
    return payload
