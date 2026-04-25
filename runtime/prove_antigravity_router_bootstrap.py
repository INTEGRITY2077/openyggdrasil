from __future__ import annotations

import json
import tempfile
from pathlib import Path

from antigravity_router_bootstrap import (
    DEFAULT_PROFILE,
    DEFAULT_SESSION_ID,
    bootstrap_antigravity_workspace_session,
    default_antigravity_cmd,
    discover_antigravity_sessions,
    read_antigravity_session_inbox,
    register_antigravity_mcp_server,
)


ANTIGRAVITY_CMD = default_antigravity_cmd()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROOF_ROOT = PROJECT_ROOT / "_tmp"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openyggdrasil-antigravity-poc-") as temp_dir:
        temp_root = Path(temp_dir)
        workspace_root = temp_root / "workspace"
        user_data_dir = temp_root / "ag-user-data"
        workspace_root.mkdir(parents=True, exist_ok=True)

        bootstrap = bootstrap_antigravity_workspace_session(
            workspace_root=workspace_root,
            provider_profile=DEFAULT_PROFILE,
            provider_session_id=DEFAULT_SESSION_ID,
        )
        discovered = discover_antigravity_sessions(workspace_root)
        inbox_rows = read_antigravity_session_inbox(
            workspace_root=workspace_root,
            provider_profile=DEFAULT_PROFILE,
            provider_session_id=DEFAULT_SESSION_ID,
        )

        mcp_registration = register_antigravity_mcp_server(
            antigravity_cmd=ANTIGRAVITY_CMD,
            user_data_dir=user_data_dir,
            server_name="openyggdrasil-test",
            command="cmd",
            args=["/c", "echo", "ok"],
        )

        proof = {
            "status": "ok",
            "workspace_root": str(workspace_root),
            "user_data_dir": str(user_data_dir),
            "bootstrap_skill_files": {key: str(path) for key, path in bootstrap["paths"].items()},
            "attachment_session_uid": bootstrap["bootstrap"]["provider_descriptor"]["session_uid"],
            "discovered_count": len(discovered),
            "inbox_count": len(inbox_rows),
            "mcp_registration": {
                "returncode": mcp_registration["returncode"],
                "mcp_exists": mcp_registration["mcp_exists"],
                "servers": list(mcp_registration["mcp_config"].get("servers", {}).keys()),
            },
            "mode": "antigravity-bootstrap-skill-plus-generated-attachment-plus-mcp-registration",
        }

        PROOF_ROOT.mkdir(parents=True, exist_ok=True)
        proof_path = PROOF_ROOT / "antigravity-router-bootstrap-proof.json"
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
        print(proof_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
