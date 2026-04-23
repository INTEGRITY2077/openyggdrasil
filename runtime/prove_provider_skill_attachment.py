from __future__ import annotations

import json
import tempfile
from pathlib import Path

from provider_attachment import (
    append_turn_delta,
    bootstrap_skill_provider_session,
    discover_generated_provider_sessions,
)
from provider_inbox import inject_session_packet, read_session_inbox


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openyggdrasil-provider-poc-") as temp_dir:
        workspace_root = Path(temp_dir)
        providers = [
            ("claude-code", "default", "thread-claude-001"),
            ("antigravity", "default", "thread-antigravity-001"),
            ("codex", "default", "thread-codex-001"),
        ]
        for provider_id, provider_profile, provider_session_id in providers:
            bootstrap_skill_provider_session(
                workspace_root=workspace_root,
                provider_id=provider_id,
                provider_profile=provider_profile,
                provider_session_id=provider_session_id,
                origin_kind="provider-thread",
                origin_locator={
                    "thread_id": provider_session_id,
                    "workspace_root": str(workspace_root),
                },
            )
            append_turn_delta(
                workspace_root=workspace_root,
                provider_id=provider_id,
                provider_profile=provider_profile,
                provider_session_id=provider_session_id,
                sequence=1,
                role="user",
                content=f"{provider_id} bootstrap request",
                summary="bootstrap",
            )
            inject_session_packet(
                workspace_root=workspace_root,
                provider_id=provider_id,
                provider_profile=provider_profile,
                provider_session_id=provider_session_id,
                packet_type="support_bundle",
                payload={"summary": f"{provider_id} attached"},
            )

        discovered = discover_generated_provider_sessions(workspace_root)
        inbox_counts = {
            provider_id: len(
                read_session_inbox(
                    workspace_root=workspace_root,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    provider_session_id=provider_session_id,
                )
            )
            for provider_id, provider_profile, provider_session_id in providers
        }

        proof = {
            "status": "ok",
            "workspace_root": str(workspace_root),
            "provider_count": len(providers),
            "discovered_count": len(discovered),
            "providers": [
                {
                    "provider_id": row["provider_descriptor"]["provider_id"],
                    "session_uid": row["provider_descriptor"]["session_uid"],
                    "turn_delta_count": row["turn_delta_count"],
                    "latest_turn_sequence": row["latest_turn_sequence"],
                }
                for row in discovered
            ],
            "inbox_counts": inbox_counts,
            "mode": "skill-generated-provider-attachments-with-session-bound-inbox",
        }

        proof_path = workspace_root / "provider-skill-attachment-proof.json"
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
        print(proof_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
