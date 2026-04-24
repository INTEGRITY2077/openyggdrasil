from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from harness_common import record_event
from mailbox_status import pushable_packets, write_mailbox_status
from mailbox_store import deliver_push_packet, delivery_target_for
from plugin_logger import record_plugin_event
from support_bundle import deliver_session_support_packet
from subagent_telemetry import record_subagent_event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deliver push-ready mailbox packets into the Hermes-consumable inbox once."
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mailbox-namespace", default=None)
    return parser.parse_args()


def deliver_once(args: argparse.Namespace) -> Dict[str, Any]:
    packets = pushable_packets(
        profile=args.profile,
        session_id=args.session_id,
        namespace=args.mailbox_namespace,
    )
    if args.limit:
        packets = packets[: args.limit]
    destinations: List[str] = []
    delivered_ids: List[str] = []
    session_support_destinations: List[str] = []
    session_support_packet_ids: List[str] = []
    for packet in packets:
        lane, destination = delivery_target_for(packet, namespace=args.mailbox_namespace)
        destination = deliver_push_packet(packet, namespace=args.mailbox_namespace)
        session_support = None
        if lane == "hermes_inbox":
            session_support = deliver_session_support_packet(packet)
            if session_support is not None:
                session_support_destinations.append(str(session_support["inbox_path"]))
                session_support_packet_ids.append(str(session_support["message_id"]))
        destinations.append(str(destination))
        delivered_ids.append(packet["message_id"])
        event_type = "mailbox_push_delivered" if lane == "hermes_inbox" else "mailbox_operator_delivered"
        record_event(
            event_type,
            {
                "message_id": packet["message_id"],
                "profile": packet.get("scope", {}).get("profile"),
                "session_id": packet.get("scope", {}).get("session_id"),
                "destination": str(destination),
                "delivery_lane": lane,
            },
        )
        record_subagent_event(
            trace_id=packet["message_id"],
            capability="query",
            role="postman",
            actor="postman",
            decider="postman",
            action="push_delivered" if lane == "hermes_inbox" else "operator_lane_delivered",
            status="success",
            producer="postman",
            parent_question_id=packet.get("parent_question_id"),
            artifacts={
                "message_id": packet["message_id"],
                "packet_id": packet["message_id"],
            },
            scope={
                "profile": packet.get("scope", {}).get("profile"),
                "session_id": packet.get("scope", {}).get("session_id"),
                "vault_path": packet.get("scope", {}).get("vault_path"),
                "target_paths": [str(destination)],
            },
            inference={"mode": "deterministic"},
            details={"delivery_lane": lane},
        )
        record_plugin_event(
            event_type="packet_delivered",
            actor="postman",
            parent_question_id=packet.get("parent_question_id"),
            profile=packet.get("scope", {}).get("profile"),
            session_id=packet.get("scope", {}).get("session_id"),
            query_text=packet.get("scope", {}).get("topic"),
            artifacts={
                "packet_id": packet["message_id"],
                "packet_type": packet.get("message_type"),
                "destination": str(destination),
                "session_support_destination": (
                    str(session_support["inbox_path"]) if session_support is not None else None
                ),
                "session_support_packet_id": (
                    str(session_support["message_id"]) if session_support is not None else None
                ),
                "mailbox_namespace": args.mailbox_namespace,
            },
            state={
                "delivery_lane": lane,
            },
        )
    status = write_mailbox_status(namespace=args.mailbox_namespace)
    return {
        "delivered": len(delivered_ids),
        "message_ids": delivered_ids,
        "destinations": destinations,
        "session_support_delivered": len(session_support_packet_ids),
        "session_support_packet_ids": session_support_packet_ids,
        "session_support_destinations": session_support_destinations,
        "status": status["counts"],
    }


def main() -> int:
    args = parse_args()
    summary = deliver_once(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
