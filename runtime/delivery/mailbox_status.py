from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from delivery.mailbox_store import (
    claimed_message_ids,
    delivery_target_for,
    legacy_global_inbox_paths,
    mailbox_paths,
    read_claims,
    read_messages,
)
from delivery.packet_factory import is_push_ready_packet
from harness_common import utc_now_iso


MAILBOX_STATUS_PATH = mailbox_paths()["status_path"]


def pushable_packets(
    *,
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    messages_path: Path | None = None,
    claims_path: Path | None = None,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    already_delivered = claimed_message_ids(
        consumer="postman",
        claim_type="push_delivered",
        path=claims_path,
        namespace=namespace,
    )
    packets: List[Dict[str, Any]] = []
    for message in read_messages(messages_path, namespace=namespace):
        if not is_push_ready_packet(message):
            continue
        if message.get("message_id") in already_delivered:
            continue
        scope = message.get("scope", {})
        if profile and scope.get("profile") != profile:
            continue
        if session_id and scope.get("session_id") != session_id:
            continue
        packets.append(message)
    return packets


def sessionless_pushable_packets(
    *,
    profile: Optional[str] = None,
    messages_path: Path | None = None,
    claims_path: Path | None = None,
    namespace: str | None = None,
) -> List[Dict[str, Any]]:
    packets = pushable_packets(
        profile=profile,
        session_id=None,
        messages_path=messages_path,
        claims_path=claims_path,
        namespace=namespace,
    )
    return [
        message
        for message in packets
        if delivery_target_for(message, namespace=namespace)[0] == "operator_lane"
    ]


def write_mailbox_status(
    *,
    messages_path: Path | None = None,
    claims_path: Path | None = None,
    status_path: Path | None = None,
    namespace: str | None = None,
) -> Dict[str, Any]:
    paths = mailbox_paths(namespace=namespace)
    effective_status_path = status_path or paths["status_path"]
    messages = read_messages(messages_path, namespace=namespace)
    claims = read_claims(claims_path, namespace=namespace)
    legacy_global_paths = legacy_global_inbox_paths(namespace=namespace)
    legacy_global_rows = sum(len(read_messages(path=path)) for path in legacy_global_paths)
    push_ready = [message for message in messages if is_push_ready_packet(message)]
    delivered = claimed_message_ids(
        consumer="postman",
        claim_type="push_delivered",
        path=claims_path,
        namespace=namespace,
    )
    status = {
        "generated_at": utc_now_iso(),
        "namespace": namespace or "active",
        "root": str(paths["root"]),
        "counts": {
            "messages": len(messages),
            "claims": len(claims),
            "push_ready": len(push_ready),
            "undelivered_push_ready": sum(
                1 for message in push_ready if message.get("message_id") not in delivered
            ),
            "delivered_push_ready": sum(
                1 for message in push_ready if message.get("message_id") in delivered
            ),
            "operator_lane_push_ready": sum(
                1
                for message in push_ready
                if delivery_target_for(message, namespace=namespace)[0] == "operator_lane"
            ),
            "hermes_lane_push_ready": sum(
                1
                for message in push_ready
                if delivery_target_for(message, namespace=namespace)[0] == "hermes_inbox"
            ),
            "legacy_global_inbox_files": len(legacy_global_paths),
            "legacy_global_inbox_rows": legacy_global_rows,
        },
        "legacy_global_inbox": {
            "deprecated": True,
            "paths": [str(path) for path in legacy_global_paths],
        },
    }
    effective_status_path.parent.mkdir(parents=True, exist_ok=True)
    effective_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
