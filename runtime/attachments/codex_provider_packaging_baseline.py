from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from attachments.bootstrap_contract import expected_bootstrap_paths
from attachments.deploy_skill import DEPLOY_TARGETS
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
DEFAULT_PROVIDER_PROFILE = "default"
DEFAULT_PROVIDER_SESSION_ID = "thread-codex-packaging-baseline"
P6_P3_ACTION = "P6.P3.claude-code-provider-packaging-baseline"


@lru_cache(maxsize=1)
def load_codex_provider_packaging_baseline_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "codex_provider_packaging_baseline.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_codex_provider_packaging_baseline(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_codex_provider_packaging_baseline_schema(),
    )


def _relative(path: Path, *, workspace_root: Path) -> str:
    return path.resolve().relative_to(workspace_root.resolve()).as_posix()


def codex_provider_native_deploy_target_status() -> str:
    return (
        "provider_native_deploy_target_available"
        if "codex" in DEPLOY_TARGETS
        else "unsupported_provider_for_file_deployment"
    )


def build_codex_provider_packaging_baseline(
    *,
    workspace_root: Path = OPENYGGDRASIL_ROOT,
    provider_profile: str = DEFAULT_PROVIDER_PROFILE,
    provider_session_id: str = DEFAULT_PROVIDER_SESSION_ID,
    local_smoke_status: str = "provider_bootstrap_contract_passed",
    next_action: str = P6_P3_ACTION,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    paths = expected_bootstrap_paths(
        workspace_root=workspace_root,
        provider_id="codex",
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    deploy_status = codex_provider_native_deploy_target_status()
    output = {
        "schema_version": "codex_provider_packaging_baseline.v1",
        "baseline_id": uuid.uuid4().hex,
        "provider_id": "codex",
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_family": "Codex",
        "packaging_status": "degrade_ready_without_provider_native_deploy_target",
        "provider_native_deploy_target_status": deploy_status,
        "deploy_tool_surface": "runtime/attachments/deploy_skill.py",
        "activation_path": (
            "No provider-native Codex deploy target exists in deploy_skill.py; "
            "use the canonical OpenYggdrasil skill instructions in the current Codex workspace "
            "and generate .yggdrasil/providers/codex/... through the shared attachment contracts."
        ),
        "degrade_reason": "Codex is attachable through provider-neutral session contracts but has no provider-native deploy target.",
        "provider_descriptor_contract": "provider_descriptor.v1",
        "session_attachment_contract": "session_attachment.v1",
        "inbox_binding_contract": "inbox_binding.v1",
        "turn_delta_contract": "turn_delta.v1",
        "expected_yggdrasil_tree": {
            "provider_descriptor": _relative(paths["provider_descriptor"], workspace_root=workspace_root),
            "session_attachment": _relative(paths["session_attachment"], workspace_root=workspace_root),
            "inbox_binding": _relative(paths["inbox_binding"], workspace_root=workspace_root),
            "turn_delta": _relative(paths["turn_delta"], workspace_root=workspace_root),
            "session_inbox": _relative(paths["session_inbox"], workspace_root=workspace_root),
        },
        "local_smoke_status": local_smoke_status,
        "known_limitations": [
            "deploy_skill.py has no Codex provider-native file target.",
            "Codex attachment is currently provider-neutral and skill-generated, not an installed provider package.",
            "Raw Codex session transcripts are not copied into OpenYggdrasil.",
        ],
        "safety": {
            "doc_committed": False,
            "raw_transcript_copied": False,
            "raw_session_copied": False,
            "global_inbox_created": False,
            "provider_native_deploy_target_claimed": False,
            "phase5_memory_gates_weakened": False,
        },
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_codex_provider_packaging_baseline(output)
    return output
