from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from attachments.bootstrap_contract import expected_bootstrap_paths
from attachments.deploy_hermes_profile_skill import DEFAULT_SKILL_CATEGORY, DEFAULT_SKILL_NAME
from attachments.hermes_foreground_unavailable_contract import (
    MISSING_PROVIDER_HARNESS_PROBE_REF,
)
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
DEFAULT_PROVIDER_PROFILE = "yggdrasilfgpoc"
DEFAULT_PROVIDER_SESSION_ID = "session-packaging-baseline-smoke"
P6_P2_ACTION = "P6.P2.codex-provider-packaging-baseline"


@lru_cache(maxsize=1)
def load_hermes_provider_packaging_baseline_schema() -> dict[str, Any]:
    return json.loads(
        (CONTRACTS_ROOT / "hermes_provider_packaging_baseline.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_hermes_provider_packaging_baseline(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_provider_packaging_baseline_schema(),
    )


def _relative(path: Path, *, workspace_root: Path) -> str:
    return path.resolve().relative_to(workspace_root.resolve()).as_posix()


def _install_path(*, provider_profile: str) -> str:
    return (
        f"~/.hermes/profiles/{provider_profile}/skills/"
        f"{DEFAULT_SKILL_CATEGORY}/{DEFAULT_SKILL_NAME}/SKILL.md"
    )


def build_hermes_provider_packaging_baseline(
    *,
    workspace_root: Path = OPENYGGDRASIL_ROOT,
    provider_profile: str = DEFAULT_PROVIDER_PROFILE,
    provider_session_id: str = DEFAULT_PROVIDER_SESSION_ID,
    local_smoke_status: str = "provider_bootstrap_contract_passed",
    next_action: str = P6_P2_ACTION,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    paths = expected_bootstrap_paths(
        workspace_root=workspace_root,
        provider_id="hermes",
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    output = {
        "schema_version": "hermes_provider_packaging_baseline.v1",
        "baseline_id": uuid.uuid4().hex,
        "provider_id": "hermes",
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "provider_family": "Hermes",
        "packaging_status": "baseline_ready_with_typed_live_foreground_unavailable",
        "install_path": _install_path(provider_profile=provider_profile),
        "activation_path": f"Hermes profile skill `{DEFAULT_SKILL_NAME}`",
        "bootstrap_command": (
            "py -3 -c \"from pathlib import Path; "
            "from runtime.attachments.deploy_hermes_profile_skill import sync_hermes_profile_skill; "
            f"sync_hermes_profile_skill(probe_profile='{provider_profile}', workspace_root=Path.cwd())\""
        ),
        "skill_name": DEFAULT_SKILL_NAME,
        "skill_category": DEFAULT_SKILL_CATEGORY,
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
        "live_foreground_status": "typed_unavailable",
        "typed_unavailable_contract": "hermes_foreground_unavailable_contract.v1",
        "known_limitations": [
            f"Live foreground provider harness dependency is missing: {MISSING_PROVIDER_HARNESS_PROBE_REF}",
            "Foreground-equivalent bootstrap and memory roundtrip proofs must not be relabeled as live foreground proof.",
            "Hermes profile skill sync depends on the local WSL Hermes profile layout.",
        ],
        "safety": {
            "doc_committed": False,
            "raw_transcript_copied": False,
            "raw_session_copied": False,
            "global_inbox_created": False,
            "live_foreground_claimed": False,
            "foreground_equivalent_relabel": False,
            "phase5_memory_gates_weakened": False,
        },
        "next_action": next_action,
        "checked_at": utc_now_iso(),
    }
    validate_hermes_provider_packaging_baseline(output)
    return output
