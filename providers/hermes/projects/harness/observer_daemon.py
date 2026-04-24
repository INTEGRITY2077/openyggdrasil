from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict

from harness_common import record_event, utc_now_iso
from observer_emit import emit_observer_commands
from observer_judgment import planned_observer_commands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the observer daemon.")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--profiles", nargs="*", default=["wiki"])
    parser.add_argument("--schedule-lint", action="store_true")
    parser.add_argument("--requested-by", default="observer-daemon")
    parser.add_argument("--mailbox-namespace", default=None)
    return parser.parse_args()


def observe_once(args: argparse.Namespace) -> Dict[str, Any]:
    plans = planned_observer_commands(
        profiles=args.profiles or ["wiki"],
        schedule_lint=args.schedule_lint,
    )
    mailbox_namespace = getattr(args, "mailbox_namespace", None)
    if mailbox_namespace is None:
        emitted = emit_observer_commands(plans)
    else:
        emitted = emit_observer_commands(plans, namespace=mailbox_namespace)
    return {
        "planned": len(plans),
        "emitted": len(emitted),
        "message_ids": [message["message_id"] for message in emitted],
        "message_types": [message["message_type"] for message in emitted],
    }


def main() -> int:
    args = parse_args()
    started_at = utc_now_iso()
    cycles = 0
    last_summary: Dict[str, Any] | None = None
    record_event("observer_daemon_started", {"started_at": started_at, "requested_by": args.requested_by})
    try:
        while True:
            last_summary = observe_once(args)
            cycles += 1
            if args.iterations and cycles >= args.iterations:
                break
            time.sleep(args.interval_seconds)
    finally:
        summary = {
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "cycles": cycles,
            "last_summary": last_summary,
        }
        record_event("observer_daemon_stopped", summary)
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
