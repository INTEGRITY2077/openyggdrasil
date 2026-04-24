from __future__ import annotations

from typing import Any, Dict, Iterable

from harness_common import DEFAULT_VAULT, record_event
from packet_factory import build_graph_hint_packet
from postman_gateway import submit_packet
from subagent_telemetry import record_subagent_event


def emit_graph_hint_poc(
    *,
    profile: str,
    session_id: str,
    mailbox_namespace: str | None = None,
    parent_question_id: str | None = None,
    topic: str,
    source_paths: Iterable[str],
    facts: Iterable[str],
    human_summary: str,
) -> Dict[str, Any]:
    source_paths_list = list(source_paths)
    message = build_graph_hint_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        topic=topic,
        source_paths=source_paths_list,
        facts=facts,
        human_summary=human_summary,
    )
    submit_packet(message, namespace=mailbox_namespace)
    record_event(
        "mailbox_push_packet_emitted",
        {
            "message_id": message["message_id"],
            "profile": profile,
            "session_id": session_id,
            "topic": topic,
        },
    )
    record_subagent_event(
        trace_id=message["message_id"],
        capability="query",
        role="observer",
        actor="observer",
        decider="observer",
        action="packet_emitted",
        status="success",
        producer="observer-daemon",
        parent_question_id=parent_question_id,
        artifacts={
            "message_id": message["message_id"],
            "packet_id": message["message_id"],
        },
        scope={
            "profile": profile,
            "session_id": session_id,
            "vault_path": str(DEFAULT_VAULT.resolve()),
            "source_paths": source_paths_list,
        },
        inference={"mode": "deterministic"},
        details={"topic": topic},
    )
    return message
