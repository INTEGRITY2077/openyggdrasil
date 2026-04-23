from __future__ import annotations

import json
import tempfile
from pathlib import Path

from antigravity_router_bootstrap import (
    DEFAULT_ANTIGRAVITY_CMD,
    DEFAULT_ANTIGRAVITY_LOG_ROOT,
    run_antigravity_live_chat_probe,
    scaffold_antigravity_workspace,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openyggdrasil-antigravity-live-") as temp_dir:
        temp_root = Path(temp_dir)
        workspace_root = temp_root / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        scaffold = scaffold_antigravity_workspace(workspace_root)
        (workspace_root / "README.md").write_text(
            "# Antigravity Live Attach Probe\n\nThis workspace is used to verify live OpenYggdrasil skill attachment behavior.\n",
            encoding="utf-8",
        )

        prompt = (
            "Use the openyggdrasil-provider-bootstrap skill. "
            "Attach this Antigravity workspace to OpenYggdrasil by creating "
            ".yggdrasil provider attachment artifacts for the current session, "
            "including provider_descriptor.v1.json, session_attachment.v1.json, "
            "inbox_binding.v1.json, and one turn_delta.v1.jsonl entry. "
            "Do not ask for clarification. Work only inside this workspace."
        )

        probe = run_antigravity_live_chat_probe(
            workspace_root=workspace_root,
            prompt=prompt,
            profile="openyggdrasil-live-probe",
            antigravity_cmd=DEFAULT_ANTIGRAVITY_CMD,
            log_root=DEFAULT_ANTIGRAVITY_LOG_ROOT,
            settle_seconds=25,
        )

        status = "ok" if probe["yggdrasil_exists"] else "blocked"
        proof = {
            "status": status,
            "workspace_root": str(workspace_root),
            "bootstrap_skill_files": {key: str(path) for key, path in scaffold.items()},
            "live_probe": probe,
            "mode": "antigravity-live-chat-skill-attach-probe",
        }
        proof_path = Path(__file__).resolve().parents[1] / "_tmp" / "antigravity-live-skill-attach-proof.json"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
        print(proof_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
