from __future__ import annotations

import json
import subprocess
from pathlib import Path


WSL_DISTRO = "ubuntu-agent"
DEFAULT_SKILL_NAME = "openyggdrasil-foreground-probe"
DEFAULT_SKILL_CATEGORY = "autonomous-ai-agents"


def build_hermes_profile_skill_markdown(
    *,
    probe_profile: str,
    workspace_root: Path,
    skill_name: str = DEFAULT_SKILL_NAME,
    contract_filename: str = "OPENYGGDRASIL_PROBE_CONTRACT.md",
) -> str:
    workspace_root = workspace_root.resolve()
    return f"""---
name: {skill_name}
description: Attaches the current Hermes foreground session to the shared OpenYggdrasil memory forest when the current workspace needs canonical attachment bootstrap, repair, or session-bound inbox access.
---

# OpenYggdrasil Foreground Probe

Use this skill when the current Hermes foreground session must:

- attach itself to OpenYggdrasil inside the current workspace
- create canonical `.yggdrasil/providers/...` artifacts
- keep the inbox session-bound
- append valid `turn_delta.v1` rows across resumed turns

Profile binding:

- `provider_id = hermes`
- `provider_profile = {probe_profile}`

Workspace contract:

- open and follow `{contract_filename}` in the current workspace
- treat `{workspace_root}` as the canonical workspace root for this probe

Core rules:

- stay in the current workspace
- do not ask clarifying questions
- never use a global inbox
- never create flat `.yggdrasil` root files
- validate JSON and JSONL with a real parser before finishing

Support consumption rule:

- when a delivered session-bound `support_bundle` exists for the current unresolved question,
  inspect that delivered packet first
- prefer `payload.canonical_note` and `payload.provenance_note` from the latest delivered
  `support_bundle` over older workspace notes when the task explicitly asks for delivered
  OpenYggdrasil support
- do not substitute an older topic page if the delivered `support_bundle` already names a
  canonical note for the current question

Use repo-owned validation/repair tooling when needed:

- `runtime/attachments/validate_attachment.py`
- `runtime/attachments/repair_attachment.py`

This file is the Hermes provider-native deployed view for the foreground probe.
Do not edit it by hand.
"""


def _run_wsl_python(python_code: str, *, timeout_seconds: int = 120) -> subprocess.CompletedProcess[str]:
    script = "python3 - <<'PY'\n" + python_code + "\nPY"
    return subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--", "bash", "-lc", script],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def sync_hermes_profile_skill(
    *,
    probe_profile: str,
    workspace_root: Path,
    skill_name: str = DEFAULT_SKILL_NAME,
    category: str = DEFAULT_SKILL_CATEGORY,
    contract_filename: str = "OPENYGGDRASIL_PROBE_CONTRACT.md",
) -> dict[str, str]:
    skill_markdown = build_hermes_profile_skill_markdown(
        probe_profile=probe_profile,
        workspace_root=workspace_root,
        skill_name=skill_name,
        contract_filename=contract_filename,
    )
    python_code = f"""
import json
import pathlib

probe_profile = {json.dumps(probe_profile)}
category = {json.dumps(category)}
skill_name = {json.dumps(skill_name)}
skill_markdown = {json.dumps(skill_markdown)}
skill_root = pathlib.Path.home() / ".hermes" / "profiles" / probe_profile / "skills" / category / skill_name
skill_root.mkdir(parents=True, exist_ok=True)
skill_path = skill_root / "SKILL.md"
skill_path.write_text(skill_markdown, encoding="utf-8")
print(json.dumps({{"skill_root": str(skill_root), "skill_path": str(skill_path)}}))
""".strip()
    completed = _run_wsl_python(python_code, timeout_seconds=120)
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to sync Hermes profile skill\n"
            f"stdout={completed.stdout!r}\n"
            f"stderr={completed.stderr!r}"
        )
    return json.loads(completed.stdout.strip())
