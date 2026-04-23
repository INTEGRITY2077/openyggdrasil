from __future__ import annotations

import json
import tempfile
from pathlib import Path

from antigravity_router_bootstrap import (
    bootstrap_antigravity_workspace_session,
    monitor_antigravity_skill_attach,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openyggdrasil-antigravity-monitor-") as temp_dir:
        temp_root = Path(temp_dir)
        workspace_root = temp_root / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)

        bootstrap = bootstrap_antigravity_workspace_session(
            workspace_root=workspace_root,
            provider_session_id="session-monitor-proof-001",
        )
        monitor = monitor_antigravity_skill_attach(
            workspace_root=workspace_root,
            timeout_seconds=5,
            poll_seconds=0.25,
            log_root=temp_root / "logs",
        )

        proof = {
            "status": monitor["status"],
            "workspace_root": str(workspace_root),
            "bootstrap_session_uid": bootstrap["bootstrap"]["provider_descriptor"]["session_uid"],
            "monitor": monitor,
            "mode": "antigravity-skill-attach-monitor-proof",
        }
        proof_path = Path(__file__).resolve().parents[1] / "_tmp" / "antigravity-skill-monitor-proof.json"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
        print(proof_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
