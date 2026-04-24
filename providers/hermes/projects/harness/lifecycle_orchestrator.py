from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from harness_common import record_event, utc_now_iso
from observer_daemon import observe_once
from postman_push_once import deliver_once
from postman_route_commands_once import command_messages, route_command
from run_cycle import run_cycle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one external lifecycle orchestration pass.")
    parser.add_argument("--profiles", nargs="*", default=["wiki"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chain-graph", action="store_true")
    parser.add_argument("--min-assistant-chars", type=int, default=80)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--skip-worker", action="store_true")
    parser.add_argument("--schedule-lint", action="store_true")
    parser.add_argument("--route-commands", action="store_true")
    parser.add_argument("--deliver-packets", action="store_true")
    parser.add_argument("--requested-by", default="lifecycle-orchestrator")
    parser.add_argument("--mailbox-namespace", default=None)
    return parser.parse_args()


def route_pending_commands(*, mailbox_namespace: str | None = None) -> Dict[str, Any]:
    messages = command_messages(profile=None, session_id=None, mailbox_namespace=mailbox_namespace)
    results = [route_command(message, mailbox_namespace=mailbox_namespace) for message in messages]
    return {"routed": len(results), "results": results}


def orchestrate_once(args: argparse.Namespace) -> Dict[str, Any]:
    started_at = utc_now_iso()
    record_event(
        "lifecycle_orchestrator_started",
        {"started_at": started_at, "requested_by": args.requested_by},
    )
    observed = observe_once(args)
    cycle = run_cycle(args)
    routed = route_pending_commands(mailbox_namespace=args.mailbox_namespace) if args.route_commands else None
    delivered = (
        deliver_once(
            argparse.Namespace(
                profile=None,
                session_id=None,
                limit=0,
                mailbox_namespace=args.mailbox_namespace,
            )
        )
        if args.deliver_packets
        else None
    )
    summary = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "observed": observed,
        "cycle": cycle,
        "routed": routed,
        "delivered": delivered,
    }
    record_event("lifecycle_orchestrator_completed", {"summary": summary})
    return summary


def main() -> int:
    args = parse_args()
    summary = orchestrate_once(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
