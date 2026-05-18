from __future__ import annotations

import os
import sys


def _bootstrap_runtime_package_for_direct_script() -> None:
    if __package__:
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_dir = script_dir
    while os.path.basename(runtime_dir) != "runtime":
        parent = os.path.dirname(runtime_dir)
        if parent == runtime_dir:
            return
        runtime_dir = parent
    project_root = os.path.dirname(runtime_dir)
    normalized_runtime_dir = os.path.normcase(os.path.abspath(runtime_dir))
    normalized_project_root = os.path.normcase(os.path.abspath(project_root))
    sys.path[:] = [
        entry
        for entry in sys.path
        if os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_runtime_dir
    ]
    if all(
        os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_project_root
        for entry in sys.path
    ):
        sys.path[:0] = [project_root]


_bootstrap_runtime_package_for_direct_script()

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS
from runtime.common.portable_ref import looks_like_local_path
from runtime.harness_common import utc_now_iso


DEFAULT_SKILL_NAME = "openyggdrasil-reasoning-lease-bridge"
DEFAULT_SKILL_CATEGORY = "autonomous-ai-agents"
DEFAULT_PROVIDER_SKILL_REF = (
    "provider-skill-ref://hermes/openyggdrasil/reasoning-lease-bridge/v1"
)
DEFAULT_PROVIDER_SKILL_PACKAGE_REF = (
    "provider-skill-package-ref://hermes/openyggdrasil/reasoning-lease-bridge/v1"
)
DEFAULT_PROVIDER_SUBAGENT_SURFACE_REF = (
    "provider-subagent-surface-ref://hermes/openyggdrasil/reasoning-lease-bridge/v1"
)
ENTRYPOINT_RUNTIME_REF = (
    "runtime-module-ref://openyggdrasil/runtime/reasoning/"
    "hermes_provider_skill_bridge_entrypoint.py"
)
ENTRYPOINT_CONTRACT_REF = (
    "contract-ref://openyggdrasil/contracts/"
    "hermes_provider_skill_bridge_entrypoint.v1.schema.json"
)
PERSONA_OR_PROMPT_REF = "persona-ref://openyggdrasil/pathfinder/v1"
GLOBAL_HARD_NONCLAIMS_REF = "persona-ref://openyggdrasil/common/v1"
SELF_ASSESSMENT_CONTRACT_REF = (
    "contract-ref://openyggdrasil/contracts/"
    "provider_reasoning_self_assessment.v1.schema.json"
)
EFFORT_NORMALIZATION_CONTRACT_REF = (
    "contract-ref://openyggdrasil/contracts/"
    "provider_reasoning_effort_normalization.v1.schema.json"
)
RESULT_SCHEMA_VERSION = "hermes_reasoning_lease_bridge_skill_deploy_result.v1"
PACKAGE_SCHEMA_VERSION = "hermes_reasoning_lease_bridge_skill_package.v1"
BINDING_SCHEMA_VERSION = "hermes_reasoning_lease_bridge_skill_binding.v1"
ENVIRONMENT_SCHEMA_VERSION = "hermes_reasoning_lease_bridge_environment.v1"
ENVIRONMENT_FILENAME = "openyggdrasil_reasoning_lease_bridge.environment.v1.json"
BINDING_FILENAME = "openyggdrasil_reasoning_lease_bridge.binding.v1.json"

STATUS_PACKAGE_READY = "provider_skill_binding_package_ready"
STATUS_TYPED_UNAVAILABLE = "typed_unavailable_provider_skill_binding"
STATUS_REJECT_UNSAFE = "reject_unsafe_provider_skill_binding"

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s\\]+$")
UNSAFE_REF_FRAGMENTS = (
    ".env",
    ".skill.md",
    "auth.json",
    "credential",
    "local-private-workspace",
    "private",
    "profile",
    "prompt",
    "state-db",
    "state_db",
    "state.db",
    "transcript",
)
REQUIRED_WORKSPACE_FILES = (
    Path("runtime/reasoning/hermes_provider_skill_bridge_entrypoint.py"),
    Path("contracts/hermes_provider_skill_bridge_entrypoint.v1.schema.json"),
)
ENTRYPOINT_REQUIRED_FIELDS = (
    "provider_skill_ref",
    "provider_skill_package_ref",
    "provider_skill_invocation_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "reasoning_lease_ref",
    "typed_task_id",
    "typed_result_ref_or_typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "unsafe_flags_false",
    "producer_receipt_ref_when_usage_claimed",
    "consumer_usage_ref_when_usage_claimed",
)
ENVIRONMENT_REQUIRED_FIELDS = (
    "app_provider_binding_ref",
    "provider_skill_ref",
    "provider_skill_package_ref",
    "provider_subagent_surface_ref",
    "persona_or_prompt_ref",
    "schema_ref",
    "runtime_enforcement_ref",
    "global_hard_nonclaims_ref",
    "entrypoint_runtime_ref",
    "entrypoint_contract_ref",
    "typed_task_id",
    "typed_result_ref_or_typed_unavailable_ref",
    "before_main_context_window_ref",
    "after_main_context_window_ref",
    "unsafe_flags_false",
)
SAFE_ARTIFACT_METADATA_STRINGS = frozenset(
    (*ENTRYPOINT_REQUIRED_FIELDS, *ENVIRONMENT_REQUIRED_FIELDS)
)


def _is_safe_name(value: str) -> bool:
    return bool(SAFE_NAME_RE.match(value))


def _is_safe_ref(value: str) -> bool:
    stripped = str(value).strip()
    if not SAFE_REF_RE.match(stripped):
        return False
    if looks_like_local_path(stripped):
        return False
    lowered = stripped.lower()
    return not any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)


def _safe_string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value).strip()]


def _stable_ref_suffix(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:24]


def _markdown_digest(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def _json_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("json_payload_not_object")
    return payload


def _contains_unsafe_string_value(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        return any(_contains_unsafe_string_value(value) for value in payload.values())
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return any(_contains_unsafe_string_value(value) for value in payload)
    if isinstance(payload, str):
        if payload in SAFE_ARTIFACT_METADATA_STRINGS:
            return False
        lowered = payload.lower()
        return any(fragment in lowered for fragment in UNSAFE_REF_FRAGMENTS)
    return False


def _unsafe_name_reason(field: str, value: str | None) -> str | None:
    if not value:
        return f"{field}_absent"
    if not _is_safe_name(value):
        return f"unsafe_{field}"
    return None


def _unsafe_workspace_reason(workspace_root: Path) -> str | None:
    normalized = str(workspace_root.resolve(strict=False)).replace("\\", "/").lower()
    if "local-private-workspace" in normalized:
        return "private_workspace_root_not_allowed"
    if not workspace_root.exists():
        return "workspace_root_absent"
    if not workspace_root.is_dir():
        return "workspace_root_not_directory"
    missing = [
        relative_path.as_posix()
        for relative_path in REQUIRED_WORKSPACE_FILES
        if not (workspace_root / relative_path).exists()
    ]
    if missing:
        return "entrypoint_validation_files_absent"
    return None


def _unsafe_skill_dir_reason(profile_skill_dir: Path | None) -> str | None:
    if profile_skill_dir is None:
        return "hermes_profile_skill_dir_absent"
    normalized = str(profile_skill_dir.resolve(strict=False)).replace("\\", "/").lower()
    if "local-private-workspace" in normalized:
        return "private_profile_skill_dir_not_allowed"
    if not profile_skill_dir.exists():
        return "hermes_profile_skill_dir_absent"
    if not profile_skill_dir.is_dir():
        return "hermes_profile_skill_dir_not_directory"
    return None


def _unsafe_skill_dir_parent_reason(profile_skill_dir: Path | None) -> str | None:
    if profile_skill_dir is None:
        return "hermes_profile_skill_dir_absent"
    normalized = str(profile_skill_dir.resolve(strict=False)).replace("\\", "/").lower()
    if "local-private-workspace" in normalized:
        return "private_profile_skill_dir_not_allowed"
    if profile_skill_dir.exists() and not profile_skill_dir.is_dir():
        return "hermes_profile_skill_dir_not_directory"
    ancestor = profile_skill_dir.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if ancestor.exists() and not ancestor.is_dir():
        return "hermes_profile_parent_not_directory"
    return None


def _bounded_child(parent: Path, *parts: str) -> Path:
    target = parent.joinpath(*parts).resolve(strict=False)
    parent_resolved = parent.resolve(strict=False)
    try:
        target.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError("target path escapes Hermes profile skill directory") from exc
    return target


def _default_profile_skill_dir(*, profile_name: str, hermes_home: Path | None) -> Path:
    root = Path(hermes_home) if hermes_home is not None else Path.home() / ".hermes"
    return root / "profiles" / profile_name / "skills"


def _workspace_ref(workspace_root: Path) -> str:
    suffix = _stable_ref_suffix("workspace", str(workspace_root.resolve(strict=False)))
    return f"workspace-ref://openyggdrasil/public/{suffix}"


def build_cold_start_app_provider_binding_ref(
    *,
    profile_name: str,
    workspace_root: Path,
    skill_name: str = DEFAULT_SKILL_NAME,
) -> str:
    for field, value in {
        "profile_name": profile_name,
        "skill_name": skill_name,
    }.items():
        reason = _unsafe_name_reason(field, value)
        if reason is not None:
            raise ValueError(reason)
    suffix = _stable_ref_suffix(
        "hermes",
        profile_name,
        skill_name,
        str(Path(workspace_root).resolve(strict=False)),
    )
    return f"app-provider-binding-ref://openyggdrasil/hermes/reasoning-lease-bridge/{suffix}"


def _result_base(
    *,
    status: str,
    package_artifact: Mapping[str, Any] | None,
    binding_artifact: Mapping[str, Any] | None,
    missing_binding: str | None,
    reason_codes: Sequence[str],
    safety_reject_reasons: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "deploy_result_id": uuid.uuid4().hex,
        "deploy_status": status,
        "package_artifact": dict(package_artifact) if package_artifact else None,
        "binding_artifact": dict(binding_artifact) if binding_artifact else None,
        "missing_binding": missing_binding,
        "reason_codes": list(reason_codes),
        "safety_reject_reasons": list(safety_reject_reasons),
        "live_invocation_possible_now": False,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "raw_skill_markdown_in_result": False,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_profile_state_material_included": False,
        "private_file_material_included": False,
        "generic_gateway_surface_claimed": False,
        "mcp_gateway_surface_claimed": False,
        "agent_adapter_surface_claimed": False,
        "r9_real_session_pass_claimed": False,
        "r10_live_pass_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "created_at": utc_now_iso(),
    }


def build_hermes_reasoning_lease_bridge_skill_markdown(
    *,
    workspace_root: Path,
    skill_name: str = DEFAULT_SKILL_NAME,
    provider_skill_ref: str = DEFAULT_PROVIDER_SKILL_REF,
    provider_skill_package_ref: str = DEFAULT_PROVIDER_SKILL_PACKAGE_REF,
    provider_subagent_surface_ref: str = DEFAULT_PROVIDER_SUBAGENT_SURFACE_REF,
    environment_filename: str = ENVIRONMENT_FILENAME,
    environment_contract_ref: str | None = None,
) -> str:
    workspace_root = Path(workspace_root)
    workspace_reason = _unsafe_workspace_reason(workspace_root)
    if workspace_reason is not None:
        raise ValueError(workspace_reason)
    for field, value in {
        "skill_name": skill_name,
    }.items():
        reason = _unsafe_name_reason(field, value)
        if reason is not None:
            raise ValueError(reason)
    for field, value in {
        "provider_skill_ref": provider_skill_ref,
        "provider_skill_package_ref": provider_skill_package_ref,
        "provider_subagent_surface_ref": provider_subagent_surface_ref,
    }.items():
        if not _is_safe_ref(value):
            raise ValueError(f"unsafe_{field}")
    if not _is_safe_name(environment_filename):
        raise ValueError("unsafe_environment_filename")
    if environment_contract_ref is not None and not _is_safe_ref(environment_contract_ref):
        raise ValueError("unsafe_environment_contract_ref")

    environment_ref_line = (
        f"- environment_contract_ref: `{environment_contract_ref}`\n"
        if environment_contract_ref
        else ""
    )

    return f"""---
name: {skill_name}
description: Hermes provider-native entrypoint for openyggdrasil Reasoning Lease bridge typed handoff.
---

# openyggdrasil Reasoning Lease Bridge

Use this skill only when Hermes is voluntarily performing an openyggdrasil
Reasoning Lease bridge handoff through the provider-skill surface.

Provider refs:

- provider_skill_ref: `{provider_skill_ref}`
- provider_skill_package_ref: `{provider_skill_package_ref}`
- provider_subagent_surface_ref: `{provider_subagent_surface_ref}`
- persona_or_prompt_ref: `{PERSONA_OR_PROMPT_REF}`
- schema_ref: `{ENTRYPOINT_CONTRACT_REF}`
- runtime_enforcement_ref: `{ENTRYPOINT_RUNTIME_REF}`
- global_hard_nonclaims_ref: `{GLOBAL_HARD_NONCLAIMS_REF}`
- entrypoint_runtime_ref: `{ENTRYPOINT_RUNTIME_REF}`
- entrypoint_contract_ref: `{ENTRYPOINT_CONTRACT_REF}`
- provider_reasoning_self_assessment_contract_ref: `{SELF_ASSESSMENT_CONTRACT_REF}`
- provider_reasoning_effort_normalization_contract_ref: `{EFFORT_NORMALIZATION_CONTRACT_REF}`
{environment_ref_line}

LLM-facing contract:

Use this when:
- Hermes is voluntarily handing a typed task to openyggdrasil through this
  provider skill.

Do not use this when:
- the task needs raw transcript, raw prompt, credential/profile/state material,
  Hermes source patching, MCP, a generic gateway, or an agent-adapter.

If ambiguous:
- self-check local typed refs and return typed unavailable instead of guessing.

Typed unavailable when:
- provider skill refs, persona refs, schema refs, runtime enforcement refs,
  typed task/result refs, or before/after context refs cannot be named.

Required evidence refs:
- `provider_skill_ref`, `provider_subagent_surface_ref`,
  `persona_or_prompt_ref`, `schema_ref`, `runtime_enforcement_ref`,
  `reasoning_lease_ref`, typed task/result refs, and before/after context refs.

Hard nonclaims:
- this handoff is not R10 complete, Reasoning Lease solved, live readiness,
  production readiness, production PTC implemented, Hermes answer quality, or
  full product readiness.

Cold-start environment contract:

- load the adjacent `{environment_filename}` file when present
- use it only as a typed openyggdrasil environment contract
- do not treat it as credentials, provider state, raw prompt, raw transcript,
  or session material
- if the environment contract is absent or invalid, return `typed_unavailable_ref`
  instead of inventing a binding

Return contract:

- return one machine-checkable JSON object, not prose
- set `schema_version` to `p0_e6_typed_handoff_tollgate.v1`
- set `provider` to `hermes`
- return only typed refs and safe identifiers
- self-assess the current Hermes model and any Hermes subagent model before
  selecting reasoning effort
- mark that assessment as `self_assessed_only` unless a known model map,
  official doc, or calibrated probe ref is available
- do not claim the self-assessment is verified capability proof
- feed the selected self-assessed capability into provider-relative effort
  normalization before choosing `compensate_up`, `pass_through`, or
  `conserve_down`
- include `typed_task_id`
- include `typed_result_ref` or `typed_unavailable_ref`
- preserve `before_main_context_window_ref`
- preserve `after_main_context_window_ref`
- include `unsafe_flags: false`
- include `producer_receipt_ref` when producer usage is claimed
- include `consumer_usage_ref` when consumer usage is claimed
- if any required ref is unavailable, return `typed_unavailable_ref` and an
  unavailable condition instead of guessing
- a handoff is machine-checkable only when `typed_task_id`,
  `typed_result_ref` or `typed_unavailable_ref`,
  `provider_skill_invocation_ref`, before/after context-window refs, and
  `unsafe_flags: false` are present in that JSON object

Typed ref materialization:

- if Hermes does not already have a native typed ref for this handoff, materialize
  a safe portable ref for the current handoff boundary instead of omitting it
- use `provider-skill-invocation-ref://hermes/openyggdrasil/reasoning-lease-bridge/<typed_task_id>`
  for `provider_skill_invocation_ref`
- use `context-window-ref://hermes/openyggdrasil/reasoning-lease-bridge/<typed_task_id>/before`
  for `before_main_context_window_ref`
- use `context-window-ref://hermes/openyggdrasil/reasoning-lease-bridge/<typed_task_id>/after`
  for `after_main_context_window_ref`
- if no true `typed_result_ref` is available, materialize
  `typed-unavailable-ref://hermes/openyggdrasil/reasoning-lease-bridge/<typed_task_id>`
  for `typed_unavailable_ref`
- these materialized refs identify only the current provider-skill handoff
  boundary and context-window boundary; they must not encode local paths,
  provider state, private material, credentials, or copied session text

Hard rejects:

- do not return raw transcript text
- do not return raw prompt text
- do not return credentials, provider profiles, state DB rows, private files,
  or local path material
- do not patch Hermes source
- do not use foreground `.env` injection
- do not use stdin or session injection
- do not relabel MCP, a generic command gateway, or an agent-adapter as the
  current P0 provider-skill surface
- do not claim R9 live pass, R10 live pass, Reasoning Lease solved, live
  readiness, production readiness, or Hermes answer quality

This file is a generated Hermes provider-native package view. It is not a live
proof by itself.
"""


def build_hermes_reasoning_lease_bridge_package_artifact(
    *,
    workspace_root: Path,
    skill_markdown: str,
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_category: str = DEFAULT_SKILL_CATEGORY,
    provider_skill_ref: str = DEFAULT_PROVIDER_SKILL_REF,
    provider_skill_package_ref: str = DEFAULT_PROVIDER_SKILL_PACKAGE_REF,
    provider_subagent_surface_ref: str = DEFAULT_PROVIDER_SUBAGENT_SURFACE_REF,
) -> dict[str, Any]:
    package_id = _stable_ref_suffix(skill_name, provider_skill_package_ref)
    return {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "provider_id": "hermes",
        "skill_name": skill_name,
        "skill_category": skill_category,
        "provider_skill_ref": provider_skill_ref,
        "provider_skill_package_ref": provider_skill_package_ref,
        "provider_subagent_surface_ref": provider_subagent_surface_ref,
        "persona_or_prompt_ref": PERSONA_OR_PROMPT_REF,
        "schema_ref": ENTRYPOINT_CONTRACT_REF,
        "runtime_enforcement_ref": ENTRYPOINT_RUNTIME_REF,
        "global_hard_nonclaims_ref": GLOBAL_HARD_NONCLAIMS_REF,
        "skill_markdown_sha256": _markdown_digest(skill_markdown),
        "entrypoint_runtime_ref": ENTRYPOINT_RUNTIME_REF,
        "entrypoint_contract_ref": ENTRYPOINT_CONTRACT_REF,
        "entrypoint_required_fields": list(ENTRYPOINT_REQUIRED_FIELDS),
        "environment_required_fields": list(ENVIRONMENT_REQUIRED_FIELDS),
        "workspace_validation": "public_entrypoint_files_present",
        "raw_skill_markdown_included": False,
        "created_at": utc_now_iso(),
    }


def build_hermes_reasoning_lease_bridge_environment_contract(
    *,
    profile_name: str,
    workspace_root: Path,
    app_provider_binding_ref: str,
    package_artifact: Mapping[str, Any],
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_category: str = DEFAULT_SKILL_CATEGORY,
) -> dict[str, Any]:
    if not _is_safe_ref(app_provider_binding_ref):
        raise ValueError("unsafe_app_provider_binding_ref")
    workspace_ref = _workspace_ref(Path(workspace_root))
    provider_runtime_ref = (
        "provider-runtime-ref://hermes/openyggdrasil/"
        f"{_stable_ref_suffix(profile_name, skill_category, skill_name)}"
    )
    environment_contract_ref = (
        "provider-skill-environment-ref://hermes/openyggdrasil/"
        f"reasoning-lease-bridge/{_stable_ref_suffix(app_provider_binding_ref, workspace_ref)}"
    )
    return {
        "schema_version": ENVIRONMENT_SCHEMA_VERSION,
        "environment_contract_ref": environment_contract_ref,
        "provider_id": "hermes",
        "provider_runtime_ref": provider_runtime_ref,
        "workspace_ref": workspace_ref,
        "app_provider_binding_ref": app_provider_binding_ref,
        "provider_skill_ref": package_artifact["provider_skill_ref"],
        "provider_skill_package_ref": package_artifact["provider_skill_package_ref"],
        "provider_subagent_surface_ref": package_artifact["provider_subagent_surface_ref"],
        "persona_or_prompt_ref": package_artifact["persona_or_prompt_ref"],
        "schema_ref": package_artifact["schema_ref"],
        "runtime_enforcement_ref": package_artifact["runtime_enforcement_ref"],
        "global_hard_nonclaims_ref": package_artifact["global_hard_nonclaims_ref"],
        "entrypoint_runtime_ref": ENTRYPOINT_RUNTIME_REF,
        "entrypoint_contract_ref": ENTRYPOINT_CONTRACT_REF,
        "entrypoint_required_fields": list(ENTRYPOINT_REQUIRED_FIELDS),
        "environment_required_fields": list(ENVIRONMENT_REQUIRED_FIELDS),
        "typed_refs_only": True,
        "raw_transcript_included": False,
        "raw_prompt_included": False,
        "credential_profile_state_material_included": False,
        "private_file_material_included": False,
        "local_path_material_included": False,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "live_invocation_proven": False,
        "created_at": utc_now_iso(),
    }


def build_hermes_reasoning_lease_bridge_binding_artifact(
    *,
    app_provider_binding_ref: str,
    package_artifact: Mapping[str, Any],
    sync_artifact_ref: str | None,
    environment_contract_ref: str | None = None,
    environment_contract_sha256: str | None = None,
) -> dict[str, Any]:
    if not _is_safe_ref(app_provider_binding_ref):
        raise ValueError("unsafe_app_provider_binding_ref")
    if sync_artifact_ref is not None and not _is_safe_ref(sync_artifact_ref):
        raise ValueError("unsafe_sync_artifact_ref")
    if environment_contract_ref is not None and not _is_safe_ref(environment_contract_ref):
        raise ValueError("unsafe_environment_contract_ref")
    return {
        "schema_version": BINDING_SCHEMA_VERSION,
        "binding_id": uuid.uuid4().hex,
        "provider_id": "hermes",
        "app_provider_binding_ref": app_provider_binding_ref,
        "provider_skill_ref": package_artifact["provider_skill_ref"],
        "provider_skill_package_ref": package_artifact["provider_skill_package_ref"],
        "provider_subagent_surface_ref": package_artifact["provider_subagent_surface_ref"],
        "persona_or_prompt_ref": package_artifact["persona_or_prompt_ref"],
        "schema_ref": package_artifact["schema_ref"],
        "runtime_enforcement_ref": package_artifact["runtime_enforcement_ref"],
        "global_hard_nonclaims_ref": package_artifact["global_hard_nonclaims_ref"],
        "entrypoint_runtime_ref": ENTRYPOINT_RUNTIME_REF,
        "entrypoint_contract_ref": ENTRYPOINT_CONTRACT_REF,
        "entrypoint_required_fields": list(ENTRYPOINT_REQUIRED_FIELDS),
        "sync_artifact_ref": sync_artifact_ref,
        "environment_contract_ref": environment_contract_ref,
        "environment_contract_sha256": environment_contract_sha256,
        "binding_status": "bound_static_package",
        "typed_refs_only": True,
        "provider_gateway_called": False,
        "provider_state_read": False,
        "live_invocation_proven": False,
        "created_at": utc_now_iso(),
    }


def sync_hermes_reasoning_lease_bridge_skill(
    *,
    profile_name: str,
    workspace_root: Path,
    app_provider_binding_ref: str | None = None,
    profile_skill_dir: Path | None = None,
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_category: str = DEFAULT_SKILL_CATEGORY,
    provider_skill_ref: str = DEFAULT_PROVIDER_SKILL_REF,
    provider_skill_package_ref: str = DEFAULT_PROVIDER_SKILL_PACKAGE_REF,
    provider_subagent_surface_ref: str = DEFAULT_PROVIDER_SUBAGENT_SURFACE_REF,
    dry_run: bool = False,
) -> dict[str, Any]:
    workspace_root = Path(workspace_root)
    profile_skill_dir = Path(profile_skill_dir) if profile_skill_dir is not None else None

    unsafe_reasons = [
        reason
        for reason in (
            _unsafe_name_reason("profile_name", profile_name),
            _unsafe_name_reason("skill_name", skill_name),
            _unsafe_name_reason("skill_category", skill_category),
            _unsafe_workspace_reason(workspace_root),
        )
        if reason is not None
    ]
    for field, value in {
        "provider_skill_ref": provider_skill_ref,
        "provider_skill_package_ref": provider_skill_package_ref,
        "provider_subagent_surface_ref": provider_subagent_surface_ref,
    }.items():
        if not _is_safe_ref(value):
            unsafe_reasons.append(f"unsafe_{field}")
    if app_provider_binding_ref is not None and not _is_safe_ref(app_provider_binding_ref):
        unsafe_reasons.append("unsafe_app_provider_binding_ref")

    if unsafe_reasons:
        return _result_base(
            status=STATUS_REJECT_UNSAFE,
            package_artifact=None,
            binding_artifact=None,
            missing_binding=None,
            reason_codes=["unsafe_provider_skill_binding_request"],
            safety_reject_reasons=unsafe_reasons,
        )

    skill_markdown = build_hermes_reasoning_lease_bridge_skill_markdown(
        workspace_root=workspace_root,
        skill_name=skill_name,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
    )
    package_artifact = build_hermes_reasoning_lease_bridge_package_artifact(
        workspace_root=workspace_root,
        skill_markdown=skill_markdown,
        skill_name=skill_name,
        skill_category=skill_category,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
    )

    if app_provider_binding_ref is None:
        return _result_base(
            status=STATUS_TYPED_UNAVAILABLE,
            package_artifact=package_artifact,
            binding_artifact=None,
            missing_binding="app_provider_binding_ref_absent",
            reason_codes=["app_provider_binding_ref_absent"],
        )

    skill_dir_reason = _unsafe_skill_dir_reason(profile_skill_dir)
    if skill_dir_reason is not None:
        return _result_base(
            status=STATUS_TYPED_UNAVAILABLE,
            package_artifact=package_artifact,
            binding_artifact=None,
            missing_binding=skill_dir_reason,
            reason_codes=[skill_dir_reason],
        )

    assert profile_skill_dir is not None
    skill_root = _bounded_child(profile_skill_dir, skill_category, skill_name)
    skill_path = _bounded_child(skill_root, "SKILL.md")
    binding_path = _bounded_child(skill_root, "openyggdrasil_reasoning_lease_bridge.binding.v1.json")
    sync_artifact_ref = (
        "provider-skill-sync-ref://hermes/openyggdrasil/reasoning-lease-bridge/"
        f"{_stable_ref_suffix(profile_name, skill_category, skill_name)}"
    )
    binding_artifact = build_hermes_reasoning_lease_bridge_binding_artifact(
        app_provider_binding_ref=app_provider_binding_ref,
        package_artifact=package_artifact,
        sync_artifact_ref=sync_artifact_ref,
    )

    if not dry_run:
        skill_root.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(skill_markdown, encoding="utf-8")
        binding_path.write_text(
            json.dumps(binding_artifact, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    return _result_base(
        status=STATUS_PACKAGE_READY,
        package_artifact=package_artifact,
        binding_artifact=binding_artifact,
        missing_binding=None,
        reason_codes=[
            "provider_skill_package_built",
            "app_provider_binding_ref_present",
            "hermes_profile_skill_dir_present",
            "static_binding_artifact_ready",
        ],
    )


def cold_start_sync_hermes_reasoning_lease_bridge_skill(
    *,
    profile_name: str,
    workspace_root: Path,
    app_provider_binding_ref: str | None = None,
    profile_skill_dir: Path | None = None,
    hermes_home: Path | None = None,
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_category: str = DEFAULT_SKILL_CATEGORY,
    provider_skill_ref: str = DEFAULT_PROVIDER_SKILL_REF,
    provider_skill_package_ref: str = DEFAULT_PROVIDER_SKILL_PACKAGE_REF,
    provider_subagent_surface_ref: str = DEFAULT_PROVIDER_SUBAGENT_SURFACE_REF,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install the bridge skill and typed environment contract during cold start.

    This is the positive enablement path: openyggdrasil creates the bounded
    provider skill package/binding instead of waiting for an external binding
    to appear. It still never calls Hermes and never writes secrets.
    """
    workspace_root = Path(workspace_root)
    profile_skill_dir = (
        Path(profile_skill_dir)
        if profile_skill_dir is not None
        else _default_profile_skill_dir(profile_name=profile_name, hermes_home=hermes_home)
    )
    if app_provider_binding_ref is None:
        try:
            app_provider_binding_ref = build_cold_start_app_provider_binding_ref(
                profile_name=profile_name,
                workspace_root=workspace_root,
                skill_name=skill_name,
            )
        except ValueError as exc:
            return _result_base(
                status=STATUS_REJECT_UNSAFE,
                package_artifact=None,
                binding_artifact=None,
                missing_binding=None,
                reason_codes=["unsafe_cold_start_binding_request"],
                safety_reject_reasons=[str(exc)],
            )

    unsafe_reasons = [
        reason
        for reason in (
            _unsafe_name_reason("profile_name", profile_name),
            _unsafe_name_reason("skill_name", skill_name),
            _unsafe_name_reason("skill_category", skill_category),
            _unsafe_workspace_reason(workspace_root),
            _unsafe_skill_dir_parent_reason(profile_skill_dir),
        )
        if reason is not None
    ]
    for field, value in {
        "provider_skill_ref": provider_skill_ref,
        "provider_skill_package_ref": provider_skill_package_ref,
        "provider_subagent_surface_ref": provider_subagent_surface_ref,
        "app_provider_binding_ref": app_provider_binding_ref,
    }.items():
        if not _is_safe_ref(value):
            unsafe_reasons.append(f"unsafe_{field}")

    if unsafe_reasons:
        return _result_base(
            status=STATUS_REJECT_UNSAFE,
            package_artifact=None,
            binding_artifact=None,
            missing_binding=None,
            reason_codes=["unsafe_cold_start_provider_skill_binding_request"],
            safety_reject_reasons=unsafe_reasons,
        )

    package_seed_markdown = build_hermes_reasoning_lease_bridge_skill_markdown(
        workspace_root=workspace_root,
        skill_name=skill_name,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
    )
    package_artifact = build_hermes_reasoning_lease_bridge_package_artifact(
        workspace_root=workspace_root,
        skill_markdown=package_seed_markdown,
        skill_name=skill_name,
        skill_category=skill_category,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
    )
    environment_contract = build_hermes_reasoning_lease_bridge_environment_contract(
        profile_name=profile_name,
        workspace_root=workspace_root,
        app_provider_binding_ref=app_provider_binding_ref,
        package_artifact=package_artifact,
        skill_name=skill_name,
        skill_category=skill_category,
    )
    skill_markdown = build_hermes_reasoning_lease_bridge_skill_markdown(
        workspace_root=workspace_root,
        skill_name=skill_name,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
        environment_contract_ref=str(environment_contract["environment_contract_ref"]),
    )
    package_artifact = build_hermes_reasoning_lease_bridge_package_artifact(
        workspace_root=workspace_root,
        skill_markdown=skill_markdown,
        skill_name=skill_name,
        skill_category=skill_category,
        provider_skill_ref=provider_skill_ref,
        provider_skill_package_ref=provider_skill_package_ref,
        provider_subagent_surface_ref=provider_subagent_surface_ref,
    )
    environment_contract.update(
        {
            "provider_skill_ref": package_artifact["provider_skill_ref"],
            "provider_skill_package_ref": package_artifact["provider_skill_package_ref"],
            "provider_subagent_surface_ref": package_artifact["provider_subagent_surface_ref"],
            "persona_or_prompt_ref": package_artifact["persona_or_prompt_ref"],
            "schema_ref": package_artifact["schema_ref"],
            "runtime_enforcement_ref": package_artifact["runtime_enforcement_ref"],
            "global_hard_nonclaims_ref": package_artifact["global_hard_nonclaims_ref"],
        }
    )

    assert profile_skill_dir is not None
    skill_root = _bounded_child(profile_skill_dir, skill_category, skill_name)
    skill_path = _bounded_child(skill_root, "SKILL.md")
    binding_path = _bounded_child(skill_root, BINDING_FILENAME)
    environment_path = _bounded_child(skill_root, ENVIRONMENT_FILENAME)
    sync_artifact_ref = (
        "provider-skill-sync-ref://hermes/openyggdrasil/reasoning-lease-bridge/"
        f"{_stable_ref_suffix(profile_name, skill_category, skill_name)}"
    )
    binding_artifact = build_hermes_reasoning_lease_bridge_binding_artifact(
        app_provider_binding_ref=app_provider_binding_ref,
        package_artifact=package_artifact,
        sync_artifact_ref=sync_artifact_ref,
        environment_contract_ref=str(environment_contract["environment_contract_ref"]),
        environment_contract_sha256=_json_digest(environment_contract),
    )

    if not dry_run:
        skill_root.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(skill_markdown, encoding="utf-8")
        environment_path.write_text(
            json.dumps(environment_contract, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        binding_path.write_text(
            json.dumps(binding_artifact, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    result = _result_base(
        status=STATUS_PACKAGE_READY,
        package_artifact=package_artifact,
        binding_artifact=binding_artifact,
        missing_binding=None,
        reason_codes=[
            "cold_start_provider_skill_package_built",
            "cold_start_app_provider_binding_ref_generated",
            "cold_start_environment_contract_ready",
            "hermes_profile_skill_package_ready",
        ],
    )
    result["cold_start_environment_contract_ref"] = environment_contract[
        "environment_contract_ref"
    ]
    result["cold_start_environment_contract_sha256"] = _json_digest(environment_contract)
    result["cold_start_environment_contract_written"] = not dry_run
    return result


def warm_start_check_hermes_reasoning_lease_bridge_skill(
    *,
    profile_name: str,
    workspace_root: Path,
    profile_skill_dir: Path | None = None,
    hermes_home: Path | None = None,
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_category: str = DEFAULT_SKILL_CATEGORY,
) -> dict[str, Any]:
    """Check an existing bridge skill install without reinstalling it."""
    workspace_root = Path(workspace_root)
    profile_skill_dir = (
        Path(profile_skill_dir)
        if profile_skill_dir is not None
        else _default_profile_skill_dir(profile_name=profile_name, hermes_home=hermes_home)
    )
    unsafe_reasons = [
        reason
        for reason in (
            _unsafe_name_reason("profile_name", profile_name),
            _unsafe_name_reason("skill_name", skill_name),
            _unsafe_name_reason("skill_category", skill_category),
            _unsafe_workspace_reason(workspace_root),
            _unsafe_skill_dir_reason(profile_skill_dir),
        )
        if reason is not None
    ]

    seed_markdown = ""
    package_artifact: dict[str, Any] | None = None
    if not unsafe_reasons:
        try:
            seed_markdown = build_hermes_reasoning_lease_bridge_skill_markdown(
                workspace_root=workspace_root,
                skill_name=skill_name,
            )
            package_artifact = build_hermes_reasoning_lease_bridge_package_artifact(
                workspace_root=workspace_root,
                skill_markdown=seed_markdown,
                skill_name=skill_name,
                skill_category=skill_category,
            )
        except ValueError as exc:
            unsafe_reasons.append(str(exc))

    if unsafe_reasons:
        return _result_base(
            status=STATUS_REJECT_UNSAFE,
            package_artifact=None,
            binding_artifact=None,
            missing_binding=None,
            reason_codes=["unsafe_warm_start_healthcheck_request"],
            safety_reject_reasons=unsafe_reasons,
        )

    assert profile_skill_dir is not None
    skill_root = _bounded_child(profile_skill_dir, skill_category, skill_name)
    skill_path = _bounded_child(skill_root, "SKILL.md")
    environment_path = _bounded_child(skill_root, ENVIRONMENT_FILENAME)
    binding_path = _bounded_child(skill_root, BINDING_FILENAME)

    missing = []
    if not skill_path.exists():
        missing.append("warm_start_skill_package_absent")
    if not environment_path.exists():
        missing.append("warm_start_environment_contract_absent")
    if not binding_path.exists():
        missing.append("warm_start_binding_artifact_absent")
    if missing:
        result = _result_base(
            status=STATUS_TYPED_UNAVAILABLE,
            package_artifact=package_artifact,
            binding_artifact=None,
            missing_binding=missing[0],
            reason_codes=missing,
        )
        result["warm_start_healthcheck"] = {
            "status": "fail",
            "mode": "check_only",
            "wrote_files": False,
        }
        return result

    try:
        skill_markdown = skill_path.read_text(encoding="utf-8")
        environment_contract = _read_json_mapping(environment_path)
        binding_artifact = _read_json_mapping(binding_path)
    except RECOVERABLE_RUNTIME_ERRORS as exc:  # noqa: BLE001
        result = _result_base(
            status=STATUS_TYPED_UNAVAILABLE,
            package_artifact=package_artifact,
            binding_artifact=None,
            missing_binding="warm_start_artifact_unreadable",
            reason_codes=["warm_start_artifact_unreadable", exc.__class__.__name__],
        )
        result["warm_start_healthcheck"] = {
            "status": "fail",
            "mode": "check_only",
            "wrote_files": False,
        }
        return result

    if environment_contract.get("schema_version") != ENVIRONMENT_SCHEMA_VERSION:
        unsafe_reasons.append("invalid_warm_start_environment_schema_version")
    if binding_artifact.get("schema_version") != BINDING_SCHEMA_VERSION:
        unsafe_reasons.append("invalid_warm_start_binding_schema_version")
    if binding_artifact.get("environment_contract_ref") != environment_contract.get(
        "environment_contract_ref"
    ):
        unsafe_reasons.append("warm_start_environment_binding_ref_mismatch")
    if binding_artifact.get("environment_contract_sha256") != _json_digest(
        environment_contract
    ):
        unsafe_reasons.append("warm_start_environment_contract_digest_mismatch")

    for artifact_name, artifact in (
        ("environment_contract", environment_contract),
        ("binding_artifact", binding_artifact),
    ):
        encoded = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
        if looks_like_local_path(encoded):
            unsafe_reasons.append(f"{artifact_name}_contains_local_path_material")
        if _contains_unsafe_string_value(artifact):
            unsafe_reasons.append(f"{artifact_name}_contains_unsafe_fragment")

    for key in (
        "app_provider_binding_ref",
        "provider_skill_ref",
        "provider_skill_package_ref",
        "provider_subagent_surface_ref",
        "persona_or_prompt_ref",
        "schema_ref",
        "runtime_enforcement_ref",
        "global_hard_nonclaims_ref",
        "environment_contract_ref",
    ):
        value = environment_contract.get(key) or binding_artifact.get(key)
        if value is not None and not _is_safe_ref(str(value)):
            unsafe_reasons.append(f"unsafe_warm_start_{key}")

    if unsafe_reasons:
        return _result_base(
            status=STATUS_REJECT_UNSAFE,
            package_artifact=None,
            binding_artifact=None,
            missing_binding=None,
            reason_codes=["unsafe_warm_start_healthcheck_artifact"],
            safety_reject_reasons=sorted(set(unsafe_reasons)),
        )

    package_artifact = build_hermes_reasoning_lease_bridge_package_artifact(
        workspace_root=workspace_root,
        skill_markdown=skill_markdown,
        skill_name=skill_name,
        skill_category=skill_category,
        provider_skill_ref=str(binding_artifact["provider_skill_ref"]),
        provider_skill_package_ref=str(binding_artifact["provider_skill_package_ref"]),
        provider_subagent_surface_ref=str(binding_artifact["provider_subagent_surface_ref"]),
    )
    result = _result_base(
        status=STATUS_PACKAGE_READY,
        package_artifact=package_artifact,
        binding_artifact=binding_artifact,
        missing_binding=None,
        reason_codes=[
            "warm_start_skill_package_present",
            "warm_start_environment_contract_present",
            "warm_start_binding_artifact_present",
            "warm_start_healthcheck_passed",
        ],
    )
    result["warm_start_healthcheck"] = {
        "status": "pass",
        "mode": "check_only",
        "wrote_files": False,
        "environment_contract_ref": environment_contract["environment_contract_ref"],
    }
    return result


def validate_hermes_reasoning_lease_bridge_deploy_result(result: Mapping[str, Any]) -> None:
    if result.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ValueError("invalid Hermes Reasoning Lease bridge deploy result schema_version")
    if result.get("deploy_status") not in {
        STATUS_PACKAGE_READY,
        STATUS_TYPED_UNAVAILABLE,
        STATUS_REJECT_UNSAFE,
    }:
        raise ValueError("invalid Hermes Reasoning Lease bridge deploy status")
    if result.get("provider_gateway_called") is not False:
        raise ValueError("deployer must not call Hermes")
    if result.get("provider_state_read") is not False:
        raise ValueError("deployer must not read provider state")
    for flag in (
        "raw_skill_markdown_in_result",
        "raw_transcript_included",
        "raw_prompt_included",
        "credential_profile_state_material_included",
        "private_file_material_included",
        "generic_gateway_surface_claimed",
        "mcp_gateway_surface_claimed",
        "agent_adapter_surface_claimed",
        "r9_real_session_pass_claimed",
        "r10_live_pass_claimed",
        "reasoning_lease_solved_claimed",
        "live_readiness_claimed",
        "production_readiness_claimed",
    ):
        if result.get(flag) is not False:
            raise ValueError(f"unsafe deploy result flag: {flag}")
    if not result.get("reason_codes"):
        raise ValueError("deploy result reason_codes are required")

    status = result.get("deploy_status")
    if status == STATUS_PACKAGE_READY:
        if not isinstance(result.get("package_artifact"), Mapping):
            raise ValueError("package ready requires package_artifact")
        if not isinstance(result.get("binding_artifact"), Mapping):
            raise ValueError("package ready requires binding_artifact")
        if result.get("missing_binding") is not None:
            raise ValueError("package ready must not report missing binding")
    elif status == STATUS_TYPED_UNAVAILABLE:
        if not isinstance(result.get("package_artifact"), Mapping):
            raise ValueError("typed unavailable requires package_artifact")
        if result.get("binding_artifact") is not None:
            raise ValueError("typed unavailable must not include binding_artifact")
        if not result.get("missing_binding"):
            raise ValueError("typed unavailable requires missing_binding")
    elif status == STATUS_REJECT_UNSAFE:
        if result.get("package_artifact") is not None:
            raise ValueError("reject must not include package_artifact")
        if not result.get("safety_reject_reasons"):
            raise ValueError("reject requires safety_reject_reasons")

    for artifact_key in ("package_artifact", "binding_artifact"):
        artifact = result.get(artifact_key)
        if isinstance(artifact, Mapping):
            for value in artifact.values():
                if isinstance(value, str) and looks_like_local_path(value):
                    raise ValueError(f"{artifact_key} contains local path material")
            for key in (
                "provider_skill_ref",
                "provider_skill_package_ref",
                "provider_subagent_surface_ref",
                "persona_or_prompt_ref",
                "schema_ref",
                "runtime_enforcement_ref",
                "global_hard_nonclaims_ref",
                "app_provider_binding_ref",
                "sync_artifact_ref",
                "entrypoint_runtime_ref",
                "entrypoint_contract_ref",
            ):
                value = artifact.get(key)
                if value is not None and not _is_safe_ref(str(value)):
                    raise ValueError(f"{artifact_key}.{key} must be a safe ref")
    if result.get("live_invocation_possible_now") is not False:
        raise ValueError("P0-E3 deployer must not claim live invocation possible")
    for key in (
        "cold_start_environment_contract_ref",
        "cold_start_environment_contract_sha256",
    ):
        value = result.get(key)
        if key.endswith("_ref") and value is not None and not _is_safe_ref(str(value)):
            raise ValueError(f"unsafe {key}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or sync the Hermes Reasoning Lease bridge provider skill."
    )
    parser.add_argument("--profile-name", required=True)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--app-provider-binding-ref")
    parser.add_argument("--profile-skill-dir", type=Path)
    parser.add_argument("--hermes-home", type=Path)
    parser.add_argument("--cold-start", action="store_true")
    parser.add_argument("--warm-start-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.warm_start_check:
        result = warm_start_check_hermes_reasoning_lease_bridge_skill(
            profile_name=args.profile_name,
            workspace_root=args.workspace_root,
            profile_skill_dir=args.profile_skill_dir,
            hermes_home=args.hermes_home,
        )
    elif args.cold_start:
        result = cold_start_sync_hermes_reasoning_lease_bridge_skill(
            profile_name=args.profile_name,
            workspace_root=args.workspace_root,
            app_provider_binding_ref=args.app_provider_binding_ref,
            profile_skill_dir=args.profile_skill_dir,
            hermes_home=args.hermes_home,
            dry_run=args.dry_run,
        )
    else:
        result = sync_hermes_reasoning_lease_bridge_skill(
            profile_name=args.profile_name,
            workspace_root=args.workspace_root,
            app_provider_binding_ref=args.app_provider_binding_ref,
            profile_skill_dir=args.profile_skill_dir,
            dry_run=args.dry_run,
        )
    validate_hermes_reasoning_lease_bridge_deploy_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
