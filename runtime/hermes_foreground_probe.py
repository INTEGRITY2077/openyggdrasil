from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from attachments.provider_attachment import (
    runtime_root_for,
    validate_inbox_binding,
    validate_provider_descriptor,
    validate_session_attachment,
    validate_turn_delta,
)
from attachments.deploy_hermes_profile_skill import (
    DEFAULT_SKILL_NAME as DEPLOYED_PROBE_SKILL_NAME,
    build_hermes_profile_skill_markdown,
    sync_hermes_profile_skill,
)
from common.wsl_runner import DEFAULT_WSL_DISTRO, run_wsl_python


WSL_DISTRO = DEFAULT_WSL_DISTRO
DEFAULT_HERMES_BIN = "~/.local/bin/hermes"
DEFAULT_BASE_PROFILE = "wiki"
DEFAULT_PROBE_PROFILE = "yggdrasilfgpoc"
DEFAULT_PROBE_SKILL_NAME = DEPLOYED_PROBE_SKILL_NAME
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROBE_WORKSPACE_ROOT = PROJECT_ROOT / "_tmp" / "hermes-foreground-probe-workspace"


def expected_session_uid(*, probe_profile: str, session_id: str) -> str:
    return f"hermes:{probe_profile}:{session_id}"


def expected_session_component(*, probe_profile: str, session_id: str) -> str:
    return expected_session_uid(probe_profile=probe_profile, session_id=session_id).replace(":", "_")


def windows_to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix()[2:]
    return f"/mnt/{drive}{tail}"


def build_probe_skill_markdown(
    *,
    probe_profile: str,
    workspace_root: Path = DEFAULT_PROBE_WORKSPACE_ROOT,
) -> str:
    return build_hermes_profile_skill_markdown(
        probe_profile=probe_profile,
        workspace_root=workspace_root,
        skill_name=DEFAULT_PROBE_SKILL_NAME,
    )


def build_probe_agents_markdown(*, probe_profile: str) -> str:
    return f"""# AGENTS.md

- Use the `{DEFAULT_PROBE_SKILL_NAME}` skill for OpenYggdrasil-related work in this workspace.
- The current workspace is the only valid attachment root.
- Use `provider_id = hermes`.
- Use `provider_profile = {probe_profile}`.
- The current Hermes session id should be treated as the attachment session id when visible.
- Create or repair canonical `.yggdrasil/providers/hermes/{probe_profile}/<session_component>/...` attachment artifacts.
- Keep the reverse inbox at `.yggdrasil/inbox/hermes/{probe_profile}/<session_component>.jsonl`.
- Never write flat root files like `.yggdrasil/provider_descriptor.v1.json`.
- Do not ask clarifying questions.
"""


def build_probe_contract_markdown(*, probe_profile: str) -> str:
    return f"""# OpenYggdrasil Probe Contract

Use this file as the canonical attachment reference for the current workspace.

## Identity Rules

- `provider_id = hermes`
- `provider_profile = {probe_profile}`
- `provider_session_id = <current Hermes session id>`
- `session_uid = hermes:{probe_profile}:<current Hermes session id>`
- `session_component = hermes_{probe_profile}_<current Hermes session id>`

## Required Paths

- `.yggdrasil/providers/hermes/{probe_profile}/<session_component>/provider_descriptor.v1.json`
- `.yggdrasil/providers/hermes/{probe_profile}/<session_component>/session_attachment.v1.json`
- `.yggdrasil/providers/hermes/{probe_profile}/<session_component>/inbox_binding.v1.json`
- `.yggdrasil/providers/hermes/{probe_profile}/<session_component>/turn_delta.v1.jsonl`
- `.yggdrasil/inbox/hermes/{probe_profile}/<session_component>.jsonl`

## Required Schema Fields

### provider_descriptor.v1.json

- `schema_version = provider_descriptor.v1`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`
- `adapter_mode = skill_generated`
- `generated_at`
- `generated_by = yggdrasil-skill-bootstrap`
- `workspace_root`
- `capabilities.attachment = true`
- `capabilities.turn_delta = true`
- `capabilities.reverse_inbox = true`

### session_attachment.v1.json

- `schema_version = session_attachment.v1`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`
- `origin_kind = workspace-session`
- `origin_locator`
- `update_mode = push-delta`
- `created_at`
- `attachment_root`
- `workspace_root`
- `capabilities.turn_delta = true`
- `capabilities.reverse_inbox = true`

### inbox_binding.v1.json

- `schema_version = inbox_binding.v1`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`
- `inbox_mode = jsonl_file`
- `target_kind = session_bound`
- `inbox_path`
- `workspace_root`
- `created_at`

### turn_delta.v1.jsonl

Each row must include:

- `schema_version = turn_delta.v1`
- `provider_id`
- `provider_profile`
- `provider_session_id`
- `session_uid`
- `delta_id`
- `sequence`
- `created_at`
- `role`
- `content`
- optional `summary`

## Copyable JSON Templates

Replace every angle-bracket placeholder with the current real value.

### provider_descriptor.v1.json

```json
{{
  "schema_version": "provider_descriptor.v1",
  "provider_id": "hermes",
  "provider_profile": "{probe_profile}",
  "provider_session_id": "<current_session_id>",
  "session_uid": "hermes:{probe_profile}:<current_session_id>",
  "adapter_mode": "skill_generated",
  "generated_at": "<iso_timestamp>",
  "generated_by": "yggdrasil-skill-bootstrap",
  "workspace_root": "<workspace_root>",
  "capabilities": {{
    "attachment": true,
    "turn_delta": true,
    "reverse_inbox": true,
    "heartbeat": false
  }},
  "provider_extras": {{}}
}}
```

### session_attachment.v1.json

```json
{{
  "schema_version": "session_attachment.v1",
  "provider_id": "hermes",
  "provider_profile": "{probe_profile}",
  "provider_session_id": "<current_session_id>",
  "session_uid": "hermes:{probe_profile}:<current_session_id>",
  "origin_kind": "workspace-session",
  "origin_locator": {{
    "workspace_root": "<workspace_root>",
    "session_id": "<current_session_id>"
  }},
  "update_mode": "push-delta",
  "created_at": "<iso_timestamp>",
  "attachment_root": "<workspace_root>/.yggdrasil/providers/hermes/{probe_profile}/<session_component>",
  "workspace_root": "<workspace_root>",
  "capabilities": {{
    "turn_delta": true,
    "reverse_inbox": true,
    "heartbeat": false
  }},
  "expires_at": null
}}
```

### inbox_binding.v1.json

```json
{{
  "schema_version": "inbox_binding.v1",
  "provider_id": "hermes",
  "provider_profile": "{probe_profile}",
  "provider_session_id": "<current_session_id>",
  "session_uid": "hermes:{probe_profile}:<current_session_id>",
  "inbox_mode": "jsonl_file",
  "target_kind": "session_bound",
  "inbox_path": "<workspace_root>/.yggdrasil/inbox/hermes/{probe_profile}/<session_component>.jsonl",
  "workspace_root": "<workspace_root>",
  "created_at": "<iso_timestamp>"
}}
```

### first turn_delta.v1 row

```json
{{
  "schema_version": "turn_delta.v1",
  "provider_id": "hermes",
  "provider_profile": "{probe_profile}",
  "provider_session_id": "<current_session_id>",
  "session_uid": "hermes:{probe_profile}:<current_session_id>",
  "delta_id": "<uuid>",
  "sequence": 1,
  "created_at": "<iso_timestamp>",
  "role": "assistant",
  "content": "Foreground Hermes session attached to OpenYggdrasil.",
  "summary": "workspace attachment bootstrap"
}}
```

## Forbidden Shapes

- `.yggdrasil/provider_descriptor.v1.json`
- `.yggdrasil/session_attachment.v1.json`
- `.yggdrasil/inbox_binding.v1.json`
- `.yggdrasil/inbox/hermes/{probe_profile}/<session_id>/turn_delta.v1.jsonl`
- any text prefix like `File unchanged since last read...` inside JSON or JSONL files
"""


def newest_session_id(before: Sequence[str], after: Sequence[str]) -> str | None:
    new_names = sorted(set(after) - set(before))
    if new_names:
        latest = new_names[-1]
    elif after:
        latest = sorted(after)[-1]
    else:
        return None
    if latest.startswith("session_") and latest.endswith(".json"):
        return latest[len("session_") : -len(".json")]
    return latest


def _run_wsl_bash(script: str, *, timeout_seconds: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-lc", script],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def _hermes_shell_expr() -> str:
    return '"$HOME/.local/bin/hermes"'


def ensure_probe_profile(
    *,
    probe_profile: str = DEFAULT_PROBE_PROFILE,
    clone_from: str = DEFAULT_BASE_PROFILE,
) -> Dict[str, Any]:
    python_code = f"""
import json
import pathlib
import shutil
import subprocess

probe_profile = {json.dumps(probe_profile)}
clone_from = {json.dumps(clone_from)}
hermes = str(pathlib.Path.home() / ".local" / "bin" / "hermes")
profile_root = pathlib.Path.home() / ".hermes" / "profiles" / probe_profile
created = False
stdout = ""
stderr = ""
if not profile_root.exists():
    cp = subprocess.run(
        [hermes, "profile", "create", probe_profile, "--clone", "--clone-from", clone_from, "--no-alias"],
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = cp.stdout
    stderr = cp.stderr
    if cp.returncode != 0:
        raise SystemExit(cp.returncode)
    created = True
print(json.dumps({{"created": created, "profile_root": str(profile_root), "stdout": stdout, "stderr": stderr}}))
""".strip()
    completed = run_wsl_python(python_code, timeout_seconds=120, mode="heredoc")
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to ensure Hermes probe profile\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return json.loads(completed.stdout.strip())


def sync_probe_auth(
    *,
    probe_profile: str = DEFAULT_PROBE_PROFILE,
    clone_from: str = DEFAULT_BASE_PROFILE,
) -> Dict[str, Any]:
    python_code = f"""
import json
import pathlib
import shutil

probe_profile = {json.dumps(probe_profile)}
clone_from = {json.dumps(clone_from)}
profiles_root = pathlib.Path.home() / ".hermes" / "profiles"
source_auth = profiles_root / clone_from / "auth.json"
probe_auth = profiles_root / probe_profile / "auth.json"
copied = False
source_exists = source_auth.exists()
if source_exists:
    probe_auth.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source_auth.read_bytes()
    target_bytes = probe_auth.read_bytes() if probe_auth.exists() else None
    if target_bytes != source_bytes:
        shutil.copy2(source_auth, probe_auth)
        probe_auth.chmod(0o600)
        copied = True
print(json.dumps({{
    "source_auth": str(source_auth),
    "probe_auth": str(probe_auth),
    "source_exists": source_exists,
    "probe_exists": probe_auth.exists(),
    "copied": copied,
}}))
""".strip()
    completed = run_wsl_python(python_code, timeout_seconds=120, mode="heredoc")
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to sync Hermes probe auth\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return json.loads(completed.stdout.strip())


def sync_probe_skill(
    *,
    probe_profile: str = DEFAULT_PROBE_PROFILE,
    skill_name: str = DEFAULT_PROBE_SKILL_NAME,
    workspace_root: Path = DEFAULT_PROBE_WORKSPACE_ROOT,
) -> Dict[str, Any]:
    return sync_hermes_profile_skill(
        probe_profile=probe_profile,
        workspace_root=workspace_root,
        skill_name=skill_name,
    )


def list_profile_skills(*, probe_profile: str = DEFAULT_PROBE_PROFILE) -> str:
    hermes = _hermes_shell_expr()
    command = f"{hermes} -p {shlex.quote(probe_profile)} skills list"
    completed = _run_wsl_bash(command, timeout_seconds=120)
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to list Hermes skills\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return completed.stdout


def list_session_files(*, probe_profile: str = DEFAULT_PROBE_PROFILE) -> List[str]:
    python_code = f"""
import json
import pathlib

probe_profile = {json.dumps(probe_profile)}
base = pathlib.Path.home() / ".hermes"
if probe_profile != "default":
    base = base / "profiles" / probe_profile
sessions_dir = base / "sessions"
paths = sorted(path.name for path in sessions_dir.glob("session_*.json"))
print(json.dumps(paths))
""".strip()
    completed = run_wsl_python(python_code, timeout_seconds=120, mode="heredoc")
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to list Hermes session files\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return json.loads(completed.stdout.strip())


def read_session_summary(*, probe_profile: str, session_id: str) -> Dict[str, Any]:
    python_code = f"""
import json
import pathlib

probe_profile = {json.dumps(probe_profile)}
session_id = {json.dumps(session_id)}
base = pathlib.Path.home() / ".hermes"
if probe_profile != "default":
    base = base / "profiles" / probe_profile
session_path = base / "sessions" / f"session_{{session_id}}.json"
data = json.loads(session_path.read_text(encoding="utf-8"))
messages = data.get("messages") or []
assistant_messages = [row.get("content", "") for row in messages if row.get("role") == "assistant"]
user_messages = [row.get("content", "") for row in messages if row.get("role") == "user"]
summary = {{
    "session_path": str(session_path),
    "session_id": data.get("session_id"),
    "message_count": data.get("message_count"),
    "platform": data.get("platform"),
    "last_updated": data.get("last_updated"),
    "user_message_count": len(user_messages),
    "assistant_message_count": len(assistant_messages),
    "last_user": user_messages[-1] if user_messages else None,
    "last_assistant": assistant_messages[-1] if assistant_messages else None,
}}
print(json.dumps(summary, ensure_ascii=False))
""".strip()
    completed = run_wsl_python(python_code, timeout_seconds=120, mode="heredoc")
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to read Hermes session summary\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return json.loads(completed.stdout.strip())


def write_probe_workspace_files(*, workspace_root: Path, probe_profile: str) -> Dict[str, str]:
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    readme_path = workspace_root / "README.md"
    agents_path = workspace_root / "AGENTS.md"
    contract_path = workspace_root / "OPENYGGDRASIL_PROBE_CONTRACT.md"
    readme_path.write_text(
        "# Hermes Foreground Probe Workspace\n\n"
        "This workspace exists to verify whether a foreground-equivalent Hermes CLI session can attach itself to OpenYggdrasil.\n",
        encoding="utf-8",
    )
    agents_path.write_text(build_probe_agents_markdown(probe_profile=probe_profile), encoding="utf-8")
    contract_path.write_text(build_probe_contract_markdown(probe_profile=probe_profile), encoding="utf-8")
    return {
        "workspace_root": str(workspace_root),
        "readme_path": str(readme_path),
        "agents_path": str(agents_path),
        "contract_path": str(contract_path),
    }


def prepare_probe_workspace(*, workspace_root: Path = DEFAULT_PROBE_WORKSPACE_ROOT) -> Path:
    workspace_root = workspace_root.resolve()
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return workspace_root


def run_foreground_turn(
    *,
    probe_profile: str,
    workspace_root: Path,
    query: str,
    resume_session_id: str | None = None,
    source_tag: str = "tool",
    skill_name: str = DEFAULT_PROBE_SKILL_NAME,
    max_turns: int = 18,
) -> Dict[str, Any]:
    before = list_session_files(probe_profile=probe_profile)
    hermes = _hermes_shell_expr()
    workspace_wsl = shlex.quote(windows_to_wsl_path(workspace_root))
    parts = [
        f"cd {workspace_wsl} &&",
        f"{hermes} -p {shlex.quote(probe_profile)} chat",
        "-Q",
        "--yolo",
        "--pass-session-id",
        f"--source {shlex.quote(source_tag)}",
        f"-s {shlex.quote(skill_name)}",
        f"--max-turns {int(max_turns)}",
    ]
    if resume_session_id:
        parts.append(f"--resume {shlex.quote(resume_session_id)}")
    parts.append(f"-q {shlex.quote(query)}")
    command = " ".join(parts)
    completed = _run_wsl_bash(command, timeout_seconds=600)
    after = list_session_files(probe_profile=probe_profile)
    session_id = resume_session_id or newest_session_id(before, after)
    session_summary = read_session_summary(probe_profile=probe_profile, session_id=session_id) if session_id else None
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "session_id": session_id,
        "session_summary": session_summary,
    }


def attachment_probe_summary(*, workspace_root: Path, probe_profile: str) -> Dict[str, Any]:
    workspace_root = workspace_root.resolve()
    attachments_root = runtime_root_for(workspace_root) / "providers"
    hermes_rows: List[Dict[str, Any]] = []
    invalid_rows: List[Dict[str, Any]] = []
    discovered_count = 0
    if not attachments_root.exists():
        return {
            "discovered_count": 0,
            "hermes_profile_rows": [],
            "invalid_rows": [],
        }

    for attachment_path in sorted(attachments_root.rglob("session_attachment.v1.json")):
        attachment_root = attachment_path.parent
        descriptor_path = attachment_root / "provider_descriptor.v1.json"
        inbox_binding_path = attachment_root / "inbox_binding.v1.json"
        turn_delta_path = attachment_root / "turn_delta.v1.jsonl"
        discovered_count += 1
        try:
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            attachment = json.loads(attachment_path.read_text(encoding="utf-8"))
            inbox_binding = json.loads(inbox_binding_path.read_text(encoding="utf-8"))
            turn_deltas = []
            if turn_delta_path.exists():
                for raw_line in turn_delta_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    turn_deltas.append(json.loads(line))

            validate_provider_descriptor(descriptor)
            validate_session_attachment(attachment)
            validate_inbox_binding(inbox_binding)
            for row in turn_deltas:
                validate_turn_delta(row)

            if descriptor["provider_id"] == "hermes" and descriptor["provider_profile"] == probe_profile:
                hermes_rows.append(
                    {
                        "session_uid": descriptor["session_uid"],
                        "provider_session_id": descriptor["provider_session_id"],
                        "attachment_root": attachment["attachment_root"],
                        "inbox_path": inbox_binding["inbox_path"],
                        "turn_delta_count": len(turn_deltas),
                        "latest_turn_sequence": turn_deltas[-1]["sequence"] if turn_deltas else None,
                    }
                )
        except Exception as exc:
            invalid_rows.append(
                {
                    "attachment_root": str(attachment_root),
                    "error": str(exc),
                    "provider_descriptor_path": str(descriptor_path),
                    "session_attachment_path": str(attachment_path),
                    "inbox_binding_path": str(inbox_binding_path),
                    "turn_delta_path": str(turn_delta_path),
                }
            )

    return {
        "discovered_count": discovered_count,
        "hermes_profile_rows": hermes_rows,
        "invalid_rows": invalid_rows,
    }


def run_hermes_foreground_probe(
    *,
    probe_profile: str = DEFAULT_PROBE_PROFILE,
    clone_from: str = DEFAULT_BASE_PROFILE,
) -> Dict[str, Any]:
    ensure_result = ensure_probe_profile(probe_profile=probe_profile, clone_from=clone_from)
    auth_result = sync_probe_auth(probe_profile=probe_profile, clone_from=clone_from)
    skill_result = sync_probe_skill(
        probe_profile=probe_profile,
        workspace_root=DEFAULT_PROBE_WORKSPACE_ROOT,
    )
    skill_list = list_profile_skills(probe_profile=probe_profile)

    workspace_root = prepare_probe_workspace()
    workspace_files = write_probe_workspace_files(
        workspace_root=workspace_root,
        probe_profile=probe_profile,
    )

    bootstrap_query = (
        f"Use the {DEFAULT_PROBE_SKILL_NAME} skill. "
        f"The current Hermes profile is {probe_profile}. "
        "Open and follow OPENYGGDRASIL_PROBE_CONTRACT.md exactly. "
        "Copy the JSON templates and replace the placeholders with real values from the current session. "
        "Attach this foreground Hermes session to OpenYggdrasil using the canonical providers tree, not a flat .yggdrasil root. "
        "Use provider_id hermes, use the current session id from the system prompt, "
        "derive session_uid as hermes:yggdrasilfgpoc:<current_session_id>, derive the session_component by replacing colons with underscores, "
        "write the three JSON contract files under .yggdrasil/providers/hermes/yggdrasilfgpoc/<session_component>/, "
        "write exactly one turn_delta.v1.jsonl row in that same directory, and create the session inbox file at "
        ".yggdrasil/inbox/hermes/yggdrasilfgpoc/<session_component>.jsonl. "
        "Do not ask clarifying questions. Work only inside this workspace."
    )
    turn1 = run_foreground_turn(
        probe_profile=probe_profile,
        workspace_root=workspace_root,
        query=bootstrap_query,
    )

    if turn1["returncode"] == 0 and turn1["session_id"]:
        resume_query = (
            f"Continue using the {DEFAULT_PROBE_SKILL_NAME} skill in the same session. "
            "Open and follow OPENYGGDRASIL_PROBE_CONTRACT.md exactly. "
            "Repair the existing attachment into the canonical providers tree if it is flattened or misplaced, then append exactly one new turn_delta.v1 row "
            "inside .yggdrasil/providers/hermes/yggdrasilfgpoc/<session_component>/turn_delta.v1.jsonl. "
            "Record the durable decision that mailbox remains outside the vault using valid turn_delta.v1 fields only. "
            "After writing the files, answer with the current session_uid, the session_component path, and whether the canonical session-bound inbox file exists."
        )
        turn2 = run_foreground_turn(
            probe_profile=probe_profile,
            workspace_root=workspace_root,
            query=resume_query,
            resume_session_id=turn1["session_id"],
        )
        validate_query = (
            f"Continue using the {DEFAULT_PROBE_SKILL_NAME} skill in the same session. "
            "Open and follow OPENYGGDRASIL_PROBE_CONTRACT.md exactly. "
            "Validate provider_descriptor.v1.json, session_attachment.v1.json, inbox_binding.v1.json, and every row of turn_delta.v1.jsonl with a real JSON parser. "
            "If turn_delta.v1.jsonl contains any tool-cache prefix, diff header, commentary, or non-JSON text, repair it so the file contains exactly two pure JSON rows with sequence 1 and sequence 2 only. "
            "Preserve the same provider_session_id, session_uid, session_component path, and canonical inbox path. "
            "After validation, answer with validated yes or no, the final turn_delta row count, and whether all contract files are pure parseable JSON."
        )
        turn3 = run_foreground_turn(
            probe_profile=probe_profile,
            workspace_root=workspace_root,
            query=validate_query,
            resume_session_id=turn1["session_id"],
        )
    else:
        turn2 = {
            "command": None,
            "returncode": None,
            "stdout": "",
            "stderr": "skipped because bootstrap turn did not produce a resumable session",
            "session_id": None,
            "session_summary": None,
        }
        turn3 = {
            "command": None,
            "returncode": None,
            "stdout": "",
            "stderr": "skipped because bootstrap turn did not produce a resumable session",
            "session_id": None,
            "session_summary": None,
        }

    attachment_summary = attachment_probe_summary(
        workspace_root=workspace_root,
        probe_profile=probe_profile,
    )
    if attachment_summary["hermes_profile_rows"]:
        status = "attached"
    elif attachment_summary["invalid_rows"]:
        status = "invalid-contract"
    else:
        status = "blocked"

    return {
        "status": status,
        "probe_profile": probe_profile,
        "clone_from": clone_from,
        "profile": ensure_result,
        "auth_sync": auth_result,
        "skill_sync": skill_result,
        "skills_list_preview": skill_list.splitlines()[:40],
        "workspace": workspace_files,
        "turns": [
            {
                "name": "bootstrap",
                **turn1,
            },
            {
                "name": "resume_and_append_turn_delta",
                **turn2,
            },
            {
                "name": "validate_and_repair_contracts",
                **turn3,
            },
        ],
        "attachment_summary": attachment_summary,
        "mode": "hermes-foreground-equivalent-profile-skill-resume-probe",
    }
