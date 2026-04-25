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
DEFAULT_PROVIDER_SESSION_ID = "thread-claude-code-packaging-baseline"
P6_P4_ACTION = "P6.P4.antigravity-provider-packaging-baseline"
CLAUDE_CODE_PROVIDER_ID = "claude-code"
CLAUDE_CODE_DEPLOY_TARGET = ".claude/skills/openyggdrasil/SKILL.md"
CLAUDE_CODE_CLEAN_ROOM_POLICY = (
    "reference behavior and repo-owned packaging patterns only; do not copy, vendor, "
    "translate, or mechanically port local Claude Code implementation source"
)


@lru_cache(maxsize=1)
def load_claude_code_provider_packaging_baseline_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "claude_code_provider_packaging_baseline.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_claude_code_provider_packaging_baseline(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_claude_code_provider_packaging_baseline_schema(),
    )


def _relative(path: Path, *, workspace_root: Path) -> str:
    return path.resolve().relative_to(workspace_root.resolve()).as_posix()


def claude_code_provider_native_deploy_target_status() -> str:
    target = DEPLOY_TARGETS.get(CLAUDE_CODE_PROVIDER_ID)
    return (
        "provider_native_deploy_target_available"
        if target is not None and target.as_posix() == CLAUDE_CODE_DEPLOY_TARGET
        else "unsupported_provider_for_file_deployment"
    )


def build_claude_code_provider_packaging_baseline(
    *,
    workspace_root: Path = OPENYGGDRASIL_ROOT,
    provider_profile: str = DEFAULT_PROVIDER_PROFILE,
    provider_session_id: str = DEFAULT_PROVIDER_SESSION_ID,
    local_smoke_status: str = "provider_bootstrap_contract_passed",
    deploy_smoke_status: str = "provider_native_file_deploy_write_passed",
    next_action: str = P6_P4_ACTION,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    paths = expected_bootstrap_paths(
        workspace_root=workspace_root,
        provider_id=CLAUDE_CODE_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    output = {
        "schema_version": "claude_code_provider_packaging_baseline.v1",
        "baseline_id": uuid.uuid4().hex,
        "provider_id": CLAUDE_CODE_PROVIDER_ID,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_family": "Claude Code / Claude-compatible",
        "packaging_status": "baseline_ready_with_clean_room_provider_native_deploy_target",
        "provider_native_deploy_target_status": claude_code_provider_native_deploy_target_status(),
        "deploy_tool_surface": "runtime/attachments/deploy_skill.py",
        "deploy_target": CLAUDE_CODE_DEPLOY_TARGET,
        "activation_path": CLAUDE_CODE_DEPLOY_TARGET,
        "skill_name": "openyggdrasil",
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
        "deploy_smoke_status": deploy_smoke_status,
        "clean_room_policy": CLAUDE_CODE_CLEAN_ROOM_POLICY,
        "known_limitations": [
            "This baseline proves repo-owned provider-native file deployment, not current Claude Code product behavior.",
            "No local Claude Code implementation source is copied, vendored, translated, or mechanically ported.",
            "Raw Claude Code sessions and transcripts are not copied into OpenYggdrasil.",
        ],
        "safety": {
            "doc_committed": False,
            "raw_transcript_copied": False,
            "raw_session_copied": False,
            "global_inbox_created": False,
            "unlicensed_source_copied": False,
            "unlicensed_source_vendored": False,
            "mechanical_port_performed": False,
            "phase5_memory_gates_weakened": False,
        },
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_claude_code_provider_packaging_baseline(output)
    return output
