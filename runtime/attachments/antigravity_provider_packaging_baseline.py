from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from antigravity_router_bootstrap import (
    ANTIGRAVITY_PROVIDER_ID,
    DEFAULT_PROFILE,
    DEFAULT_SESSION_ID,
    DEFAULT_SKILL_NAME,
)
from attachments.bootstrap_contract import expected_bootstrap_paths
from attachments.deploy_skill import DEPLOY_TARGETS
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
GEMINI_PROVIDER_ID = "gemini"
GEMINI_DEPLOY_TARGET = "GEMINI.md"
P6_S1_ACTION = "P6.S1.provider-effort-vocabulary-normalization"


@lru_cache(maxsize=1)
def load_antigravity_provider_packaging_baseline_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "antigravity_provider_packaging_baseline.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_antigravity_provider_packaging_baseline(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_antigravity_provider_packaging_baseline_schema(),
    )


def _relative(path: Path, *, workspace_root: Path) -> str:
    return path.resolve().relative_to(workspace_root.resolve()).as_posix()


def gemini_deploy_target_status() -> str:
    target = DEPLOY_TARGETS.get(GEMINI_PROVIDER_ID)
    return (
        "provider_native_deploy_target_available"
        if target is not None and target.as_posix() == GEMINI_DEPLOY_TARGET
        else "unsupported_provider_for_file_deployment"
    )


def build_antigravity_provider_packaging_baseline(
    *,
    workspace_root: Path = OPENYGGDRASIL_ROOT,
    provider_profile: str = DEFAULT_PROFILE,
    provider_session_id: str = DEFAULT_SESSION_ID,
    local_smoke_status: str = "antigravity_workspace_bootstrap_passed",
    gemini_deploy_smoke_status: str = "gemini_file_deploy_write_passed",
    antigravity_scaffold_smoke_status: str = "workspace_scaffold_write_passed",
    next_action: str = P6_S1_ACTION,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    paths = expected_bootstrap_paths(
        workspace_root=workspace_root,
        provider_id=ANTIGRAVITY_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    output = {
        "schema_version": "antigravity_provider_packaging_baseline.v1",
        "baseline_id": uuid.uuid4().hex,
        "provider_id": ANTIGRAVITY_PROVIDER_ID,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_family": "Gemini / Antigravity",
        "packaging_status": "baseline_ready_with_workspace_router_and_gemini_file_target",
        "gemini_deploy_target_status": gemini_deploy_target_status(),
        "gemini_deploy_tool_surface": "runtime/attachments/deploy_skill.py",
        "gemini_deploy_target": GEMINI_DEPLOY_TARGET,
        "antigravity_scaffold_surface": "runtime/antigravity_router_bootstrap.py",
        "antigravity_skill_path": f".agents/skills/{DEFAULT_SKILL_NAME}/SKILL.md",
        "antigravity_rule_path": ".agents/rules/openyggdrasil-attachment-discipline.md",
        "antigravity_workflow_path": ".agents/workflows/emit-openyggdrasil-bootstrap.md",
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
        "gemini_deploy_smoke_status": gemini_deploy_smoke_status,
        "antigravity_scaffold_smoke_status": antigravity_scaffold_smoke_status,
        "known_limitations": [
            "This baseline proves repo-owned Gemini file deployment and Antigravity workspace scaffold behavior, not current product behavior.",
            "The Antigravity provider id remains distinct from the Gemini file target to preserve provider/session provenance.",
            "Raw Gemini or Antigravity sessions and transcripts are not copied into OpenYggdrasil.",
        ],
        "safety": {
            "doc_committed": False,
            "raw_transcript_copied": False,
            "raw_session_copied": False,
            "global_inbox_created": False,
            "product_behavior_claimed": False,
            "provider_specific_contract_bypass": False,
            "phase5_memory_gates_weakened": False,
        },
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_antigravity_provider_packaging_baseline(output)
    return output
