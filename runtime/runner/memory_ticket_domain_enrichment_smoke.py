from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from runtime.capture.provider_current_source_bridge import (
    build_memory_ticket_payload_from_existing_provider_exchange,
)
from runtime.operator.producer import _handle_memory_ticket
from runtime.source_ref.hermes_session_json import _canonical_anchor_hash


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _fixture_docs(root: Path) -> None:
    _write(
        root / "Build with Claude Code" / "sub-agents.md",
        """
# Subagents

Custom subagents are specialized agents that Claude Code can delegate to for
specific tasks. They are separate context windows with their own prompts and
tool permissions.

# Agent teams

Agent teams describe coordinated multi-agent workflows where a primary task can
be split across multiple specialist agents.
""",
    )
    _write(
        root / "Reference" / "plugins.md",
        """
# Plugins

Plugins package and distribute Claude Code extensions such as slash commands,
agents, hooks, skills, and MCP servers.

# Plugin agents

Plugin agents are agent definitions shipped by a plugin. They are not the same
axis as the runtime execution model; they describe where the agent definition
comes from.
""",
    )
    _write(
        root / "Build with Claude Code" / "hooks.md",
        """
# Hooks

Hooks run automatically at configured lifecycle events.

# Skills

Skills are instructions and workflows that the model reads and applies when a
task calls for that capability.

# MCP

MCP servers connect Claude Code to external tools, APIs, and data sources.
""",
    )


def _fixture_payload(sessions_dir: Path) -> dict:
    messages = [
        {
            "role": "user",
            "content": "Claude Code 문서 보다가 agent 쪽이 헷갈려. subagent, agent team, plugin agents 기준을 나중에도 다시 쓸 수 있게 잡고 싶어.",
        },
        {
            "role": "assistant",
            "content": "실행 모델은 subagent나 agent team 쪽으로 보고, plugin agents는 agent 정의가 plugin에서 공급되는 위치로 분리해서 보는 것이 안전합니다.",
        },
    ]
    session_id = "domain-enrichment-smoke"
    _write(
        sessions_dir / f"session_{session_id}.json",
        json.dumps(
            {
                "schema_version": "hermes_session_json.v1",
                "provider_id": "hermes",
                "provider_profile": "openyggdrasil-provider",
                "provider_session_id": session_id,
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    payload = build_memory_ticket_payload_from_existing_provider_exchange(
        provider_id="hermes",
        provider_profile="openyggdrasil-provider",
        provider_session_id=session_id,
        user_text=messages[0]["content"],
        assistant_text=messages[1]["content"],
        message_index_range={"start": 0, "end": 1},
        anchor_hash=_canonical_anchor_hash(messages),
        sessions_dir=sessions_dir,
        source_ref_scheme="hermes-session-json",
    )
    if payload.get("schema_version") != "memory_ticket.v1":
        raise AssertionError(f"payload not emitted: {payload}")
    if not isinstance(payload.get("domain_evidence_request"), dict):
        raise AssertionError("domain evidence request missing")
    return payload


def main() -> None:
    original_env = os.environ.get("OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON")
    original_workspace = os.environ.get("OPENYGGDRASIL_WORKSPACE_ROOT")
    try:
        with tempfile.TemporaryDirectory(prefix="ygg-domain-enrich-smoke-") as raw:
            root = Path(raw)
            docs_root = root / "docs"
            sessions_dir = root / "sessions"
            mailbox = root / "mailbox"
            vault = root / "vault"
            _fixture_docs(docs_root)
            payload = _fixture_payload(sessions_dir)

            os.environ.pop("OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON", None)
            blocked = _handle_memory_ticket(mailbox, vault, {"mail_id": "weak", "payload": payload})
            if blocked.get("status") != "typed_unavailable":
                raise AssertionError(f"weak payload should stay blocked: {blocked}")
            if blocked.get("nodes"):
                raise AssertionError("weak payload produced nodes without configured source roots")

            workspace_root = root / "workspace"
            _write(
                workspace_root / "config" / "domain_source_roots.json",
                json.dumps({"docs_roots": {"fixture-docs": str(docs_root)}}, ensure_ascii=False, indent=2),
            )
            os.environ["OPENYGGDRASIL_WORKSPACE_ROOT"] = str(workspace_root)
            os.environ.pop("OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON", None)
            admitted = _handle_memory_ticket(mailbox, vault, {"mail_id": "strong", "payload": payload})
            if admitted.get("status") != "acknowledged":
                raise AssertionError(f"workspace-config enriched payload should be acknowledged: {admitted}")

            os.environ["OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON"] = json.dumps(
                {"fixture-docs-env": str(docs_root)},
                ensure_ascii=False,
            )
            admitted = _handle_memory_ticket(mailbox, vault, {"mail_id": "strong-env", "payload": payload})
            if admitted.get("status") != "acknowledged":
                raise AssertionError(f"env enriched payload should be acknowledged: {admitted}")
            if len(admitted.get("nodes") or []) != 1:
                raise AssertionError("enriched payload did not produce one canonical node")
            node_id = admitted["nodes"][0]
            node_path = vault / "concepts" / f"{node_id}.md"
            if not node_path.exists():
                raise AssertionError("canonical N node was not written")
            if list((vault / "concepts").glob("PRN-*.md")):
                raise AssertionError("legacy PRN mirror should not be written")
            text = node_path.read_text(encoding="utf-8")
            required = [
                "## What This Page Is",
                "## Source Synthesis",
                "local-docs://fixture-docs/",
                "## Related Pages",
                "## Maintenance Notes",
            ]
            missing = [item for item in required if item not in text]
            if missing:
                raise AssertionError(f"node missing prose/wiki sections: {missing}")
            forbidden = ["추출된 주장:", "이 소스가 노드에 충분한 이유:", "이것이 증명하지 못하는 것:"]
            leaked = [item for item in forbidden if item in text]
            if leaked:
                raise AssertionError(f"report scaffold leaked into wiki node: {leaked}")
            quality = admitted.get("quality_assessment") or {}
            if quality.get("verdict") != "pass":
                raise AssertionError(f"quality did not pass: {quality}")
            if "human_evaluator_not_executed" not in (quality.get("confidence_deductions") or []):
                raise AssertionError("missing explicit confidence deduction for absent human evaluator")
            print("memory_ticket_domain_enrichment_smoke=pass")
            print(json.dumps({"node_id": node_id, "quality": quality}, ensure_ascii=False, sort_keys=True))
    finally:
        if original_env is None:
            os.environ.pop("OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON", None)
        else:
            os.environ["OPENYGGDRASIL_DOMAIN_SOURCE_ROOTS_JSON"] = original_env
        if original_workspace is None:
            os.environ.pop("OPENYGGDRASIL_WORKSPACE_ROOT", None)
        else:
            os.environ["OPENYGGDRASIL_WORKSPACE_ROOT"] = original_workspace


if __name__ == "__main__":
    main()
