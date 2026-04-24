from __future__ import annotations

from pathlib import Path
from typing import Any

from attachments.provider_attachment import (
    append_turn_delta,
    bootstrap_skill_provider_session,
    build_session_uid,
    discover_generated_provider_sessions,
    provider_attachment_root,
    provider_inbox_path,
    session_uid_path_component,
)
from attachments.provider_inbox import inject_session_packet, read_session_inbox


def expected_bootstrap_paths(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> dict[str, Path]:
    workspace_root = workspace_root.resolve()
    attachment_root = provider_attachment_root(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "runtime_root": workspace_root / ".yggdrasil",
        "attachment_root": attachment_root,
        "provider_descriptor": attachment_root / "provider_descriptor.v1.json",
        "session_attachment": attachment_root / "session_attachment.v1.json",
        "inbox_binding": attachment_root / "inbox_binding.v1.json",
        "turn_delta": attachment_root / "turn_delta.v1.jsonl",
        "session_inbox": provider_inbox_path(
            workspace_root=workspace_root,
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        ),
    }


def prove_provider_bootstrap_contract(
    *,
    workspace_root: Path,
    provider_id: str = "hermes",
    provider_profile: str = "default",
    provider_session_id: str = "session-bootstrap-smoke",
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    bootstrap = bootstrap_skill_provider_session(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        origin_kind="provider-thread",
        origin_locator={
            "provider_id": provider_id,
            "provider_profile": provider_profile,
            "provider_session_id": provider_session_id,
        },
    )
    turn_delta = append_turn_delta(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        sequence=1,
        role="user",
        content="bootstrap contract smoke turn",
        summary="bootstrap contract smoke",
    )
    inbox_packet = inject_session_packet(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        packet_type="attention_flag",
        payload={
            "schema_version": "bootstrap_contract_smoke.v1",
            "status": "session_bound_inbox_writable",
        },
    )
    discovered = discover_generated_provider_sessions(workspace_root)
    inbox_rows = read_session_inbox(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    paths = expected_bootstrap_paths(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    expected_attachment_suffix = Path(
        ".yggdrasil",
        "providers",
        provider_id,
        provider_profile,
        session_uid_path_component(session_uid),
    )
    expected_inbox_suffix = Path(
        ".yggdrasil",
        "inbox",
        provider_id,
        provider_profile,
        f"{session_uid_path_component(session_uid)}.jsonl",
    )
    checks = {
        "provider_descriptor_exists": paths["provider_descriptor"].exists(),
        "session_attachment_exists": paths["session_attachment"].exists(),
        "inbox_binding_exists": paths["inbox_binding"].exists(),
        "turn_delta_appendable": paths["turn_delta"].exists() and turn_delta["sequence"] == 1,
        "session_inbox_writable": paths["session_inbox"].exists() and len(inbox_rows) == 1,
        "attachment_path_shape": paths["attachment_root"].relative_to(workspace_root) == expected_attachment_suffix,
        "inbox_path_shape": paths["session_inbox"].relative_to(workspace_root) == expected_inbox_suffix,
        "session_discoverable": any(
            row["provider_descriptor"]["session_uid"] == session_uid
            and row["turn_delta_count"] == 1
            and row["latest_turn_sequence"] == 1
            for row in discovered
        ),
    }
    return {
        "schema_version": "provider_bootstrap_contract_smoke.v1",
        "ok": all(checks.values()),
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "paths": {key: str(value) for key, value in paths.items()},
        "checks": checks,
        "bootstrap": bootstrap,
        "turn_delta": turn_delta,
        "inbox_packet": inbox_packet,
    }
