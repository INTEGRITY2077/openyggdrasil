from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Any, Dict, List, Mapping

from provider_attachment import (
    append_turn_delta,
    bootstrap_skill_provider_session,
    discover_generated_provider_sessions,
)
from provider_inbox import inject_session_packet, read_session_inbox


ANTIGRAVITY_PROVIDER_ID = "antigravity"
DEFAULT_PROFILE = "default"
DEFAULT_SESSION_ID = "session-antigravity-bootstrap-001"
DEFAULT_SKILL_NAME = "openyggdrasil-provider-bootstrap"
DEFAULT_ANTIGRAVITY_CMD = Path(r"<local-user>\AppData\Local\Programs\Antigravity\bin\antigravity.cmd")
DEFAULT_ANTIGRAVITY_LOG_ROOT = Path.home() / "AppData" / "Roaming" / "Antigravity" / "logs"


def scaffold_antigravity_workspace(workspace_root: Path) -> Dict[str, Path]:
    workspace_root = workspace_root.resolve()
    skill_root = workspace_root / ".agents" / "skills" / DEFAULT_SKILL_NAME
    rules_dir = workspace_root / ".agents" / "rules"
    workflows_dir = workspace_root / ".agents" / "workflows"

    skill_root.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)
    workflows_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skill_root / "SKILL.md"
    rule_path = rules_dir / "openyggdrasil-attachment-discipline.md"
    workflow_path = workflows_dir / "emit-openyggdrasil-bootstrap.md"

    skill_path.write_text(
        """---
name: openyggdrasil-provider-bootstrap
description: Use when a provider session needs to attach to OpenYggdrasil through generated artifacts in the current workspace.
---

# OpenYggdrasil Provider Bootstrap

## Goal
- Attach the current Antigravity session to OpenYggdrasil without assuming a static provider adapter.

## Required Behavior
1. Treat the current workspace as the attachment root.
2. Generate provider/session attachment artifacts under `.yggdrasil/`.
3. Keep the attachment session-bound and provider-bound.
4. Do not invent provider metadata that is not visible from the current session.

## Required Artifact Families
- `provider_descriptor.v1.json`
- `session_attachment.v1.json`
- `inbox_binding.v1.json`
- `turn_delta.v1.jsonl`

## Reverse Injection Discipline
- Read only the session-bound inbox for the current provider session.
- Never consume a global inbox.
""",
        encoding="utf-8",
    )
    rule_path.write_text(
        """# OpenYggdrasil Attachment Discipline

- Prefer Planning mode for OpenYggdrasil-related work.
- Keep terminal execution in Request Review unless the operator has explicitly narrowed the task.
- Treat `.yggdrasil/` as an attachment protocol surface, not as disposable scratch state.
- Keep provider/session identity namespaced.
""",
        encoding="utf-8",
    )
    workflow_path.write_text(
        """# emit-openyggdrasil-bootstrap

- Inspect the current provider session context.
- Emit or update OpenYggdrasil provider attachment artifacts for the current workspace.
- Confirm the attachment root and session-bound inbox path.
""",
        encoding="utf-8",
    )

    return {
        "skill_path": skill_path,
        "rule_path": rule_path,
        "workflow_path": workflow_path,
    }


def bootstrap_antigravity_workspace_session(
    *,
    workspace_root: Path,
    provider_profile: str = DEFAULT_PROFILE,
    provider_session_id: str = DEFAULT_SESSION_ID,
    origin_locator: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    workspace_root = workspace_root.resolve()
    paths = scaffold_antigravity_workspace(workspace_root)
    bootstrap_result = bootstrap_skill_provider_session(
        workspace_root=workspace_root,
        provider_id=ANTIGRAVITY_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        origin_kind="workspace-session",
        origin_locator=dict(
            origin_locator
            or {
                "provider": ANTIGRAVITY_PROVIDER_ID,
                "workspace_root": str(workspace_root),
                "profile": provider_profile,
                "session_id": provider_session_id,
            }
        ),
        provider_extras={
            "workspace_skill_root": str(workspace_root / ".agents" / "skills"),
            "workspace_rule_root": str(workspace_root / ".agents" / "rules"),
            "workspace_workflow_root": str(workspace_root / ".agents" / "workflows"),
        },
    )
    first_delta = append_turn_delta(
        workspace_root=workspace_root,
        provider_id=ANTIGRAVITY_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        sequence=1,
        role="user",
        content="bootstrap antigravity provider attachment for this workspace",
        summary="antigravity bootstrap",
    )
    first_packet = inject_session_packet(
        workspace_root=workspace_root,
        provider_id=ANTIGRAVITY_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        packet_type="support_bundle",
        payload={
            "summary": "antigravity session attached",
            "provider": ANTIGRAVITY_PROVIDER_ID,
        },
    )
    return {
        "paths": paths,
        "bootstrap": bootstrap_result,
        "turn_delta": first_delta,
        "inbox_packet": first_packet,
    }


def discover_antigravity_sessions(workspace_root: Path) -> List[Dict[str, Any]]:
    discovered = discover_generated_provider_sessions(workspace_root.resolve())
    return [
        row
        for row in discovered
        if row["provider_descriptor"]["provider_id"] == ANTIGRAVITY_PROVIDER_ID
    ]


def read_antigravity_session_inbox(
    *,
    workspace_root: Path,
    provider_profile: str = DEFAULT_PROFILE,
    provider_session_id: str = DEFAULT_SESSION_ID,
) -> List[Dict[str, Any]]:
    return read_session_inbox(
        workspace_root=workspace_root.resolve(),
        provider_id=ANTIGRAVITY_PROVIDER_ID,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )


def register_antigravity_mcp_server(
    *,
    antigravity_cmd: Path,
    user_data_dir: Path,
    server_name: str,
    command: str,
    args: List[str],
) -> Dict[str, Any]:
    user_data_dir = user_data_dir.resolve()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"name": server_name, "command": command, "args": args}, ensure_ascii=False)
    result = subprocess.run(
        [
            str(antigravity_cmd),
            "--user-data-dir",
            str(user_data_dir),
            "--add-mcp",
            payload,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    mcp_path = user_data_dir / "User" / "mcp.json"
    mcp_config: Dict[str, Any] = {}
    if mcp_path.exists():
        mcp_config = json.loads(mcp_path.read_text(encoding="utf-8"))
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "mcp_path": str(mcp_path),
        "mcp_exists": mcp_path.exists(),
        "mcp_config": mcp_config,
    }


def detect_antigravity_chat_command_failure(log_dir: Path) -> Dict[str, Any]:
    patterns = [
        "workbench.action.chat.newChat",
        "command 'workbench.action.chat.newChat' not found",
    ]
    matches: List[Dict[str, str]] = []
    if not log_dir.exists():
        return {"detected": False, "matches": matches}

    for path in log_dir.rglob("*.log"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in patterns:
            if pattern in text:
                matches.append({"path": str(path), "pattern": pattern})
    return {"detected": bool(matches), "matches": matches}


def collect_antigravity_attach_observations(
    *,
    workspace_root: Path,
    log_root: Path = DEFAULT_ANTIGRAVITY_LOG_ROOT,
    baseline: float | None = None,
) -> Dict[str, Any]:
    workspace_root = workspace_root.resolve()
    yggdrasil_root = workspace_root / ".yggdrasil"
    skill_root = workspace_root / ".agents" / "skills" / DEFAULT_SKILL_NAME
    rule_path = workspace_root / ".agents" / "rules" / "openyggdrasil-attachment-discipline.md"
    workflow_path = workspace_root / ".agents" / "workflows" / "emit-openyggdrasil-bootstrap.md"

    sessions = discover_antigravity_sessions(workspace_root)
    inbox_counts: Dict[str, int] = {}
    for row in sessions:
        descriptor = row["provider_descriptor"]
        inbox_rows = read_antigravity_session_inbox(
            workspace_root=workspace_root,
            provider_profile=descriptor["provider_profile"],
            provider_session_id=descriptor["provider_session_id"],
        )
        inbox_counts[descriptor["session_uid"]] = len(inbox_rows)

    latest_dir = None
    if log_root.exists():
        candidates = [path for path in log_root.iterdir() if path.is_dir()]
        if baseline is not None:
            candidates = [path for path in candidates if path.stat().st_mtime >= baseline]
        if candidates:
            latest_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    failure = detect_antigravity_chat_command_failure(latest_dir) if latest_dir else {"detected": False, "matches": []}

    status = "pending"
    if sessions:
        status = "attached"
    elif failure["detected"]:
        status = "blocked"

    return {
        "status": status,
        "workspace_root": str(workspace_root),
        "yggdrasil_exists": yggdrasil_root.exists(),
        "skill_exists": (skill_root / "SKILL.md").exists(),
        "rule_exists": rule_path.exists(),
        "workflow_exists": workflow_path.exists(),
        "session_count": len(sessions),
        "sessions": sessions,
        "inbox_counts": inbox_counts,
        "latest_log_dir": str(latest_dir) if latest_dir else None,
        "chat_command_failure": failure,
    }


def monitor_antigravity_skill_attach(
    *,
    workspace_root: Path,
    timeout_seconds: int = 60,
    poll_seconds: float = 2.0,
    log_root: Path = DEFAULT_ANTIGRAVITY_LOG_ROOT,
    stop_event: Event | None = None,
) -> Dict[str, Any]:
    deadline = time.time() + max(timeout_seconds, 1)
    baseline = time.time()
    snapshots: List[Dict[str, Any]] = []

    while time.time() <= deadline:
        if stop_event and stop_event.is_set():
            break

        snapshot = collect_antigravity_attach_observations(
            workspace_root=workspace_root,
            log_root=log_root,
            baseline=baseline,
        )
        snapshots.append(snapshot)
        if snapshot["status"] in {"attached", "blocked"}:
            return {
                "status": snapshot["status"],
                "final_snapshot": snapshot,
                "snapshot_count": len(snapshots),
                "snapshots": snapshots,
                "mode": "antigravity-skill-attach-monitor",
            }
        time.sleep(max(poll_seconds, 0.1))

    final_snapshot = snapshots[-1] if snapshots else collect_antigravity_attach_observations(
        workspace_root=workspace_root,
        log_root=log_root,
        baseline=baseline,
    )
    return {
        "status": "timeout",
        "final_snapshot": final_snapshot,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "mode": "antigravity-skill-attach-monitor",
    }


def run_antigravity_live_chat_probe(
    *,
    workspace_root: Path,
    prompt: str,
    profile: str,
    antigravity_cmd: Path = DEFAULT_ANTIGRAVITY_CMD,
    log_root: Path = DEFAULT_ANTIGRAVITY_LOG_ROOT,
    settle_seconds: int = 25,
) -> Dict[str, Any]:
    workspace_root = workspace_root.resolve()
    baseline = time.time()
    result = subprocess.run(
        [
            str(antigravity_cmd),
            "chat",
            "--new-window",
            "--profile",
            profile,
            prompt,
        ],
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    time.sleep(settle_seconds)

    latest_dir = None
    if log_root.exists():
        candidates = [
            path
            for path in log_root.iterdir()
            if path.is_dir() and path.stat().st_mtime >= baseline
        ]
        if candidates:
            latest_dir = max(candidates, key=lambda path: path.stat().st_mtime)
    failure = detect_antigravity_chat_command_failure(latest_dir) if latest_dir else {"detected": False, "matches": []}
    yggdrasil_root = workspace_root / ".yggdrasil"

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "latest_log_dir": str(latest_dir) if latest_dir else None,
        "chat_command_failure": failure,
        "yggdrasil_exists": yggdrasil_root.exists(),
        "workspace_root": str(workspace_root),
    }
