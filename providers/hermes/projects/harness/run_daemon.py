from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict

from harness_common import QUEUE_ROOT, record_event, utc_now_iso
from lock_policy import recover_stale_locks
from run_cycle import run_cycle


DAEMON_STATUS_PATH = QUEUE_ROOT / "daemon-status.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Hermes external harness as a simple polling daemon."
    )
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of cycles to run. 0 means forever.",
    )
    parser.add_argument("--profiles", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chain-graph", action="store_true")
    parser.add_argument("--min-assistant-chars", type=int, default=80)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--skip-worker", action="store_true")
    parser.add_argument("--requested-by", default="daemon")
    parser.add_argument("--stale-lock-age-seconds", type=float, default=900.0)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--status-path", default=str(DAEMON_STATUS_PATH))
    return parser.parse_args()


def cycle_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        profiles=args.profiles,
        limit=args.limit,
        chain_graph=args.chain_graph,
        min_assistant_chars=args.min_assistant_chars,
        max_jobs=args.max_jobs,
        skip_discovery=args.skip_discovery,
        skip_worker=args.skip_worker,
        requested_by=args.requested_by,
    )


def daemon_summary(
    *,
    started_at: str,
    cycles: int,
    last_summary: Dict[str, Any] | None,
    stop_reason: str,
    consecutive_failures: int,
    last_error: str | None,
    stale_lock_recoveries: int,
) -> Dict[str, Any]:
    return {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "cycles": cycles,
        "last_summary": last_summary,
        "stop_reason": stop_reason,
        "consecutive_failures": consecutive_failures,
        "last_error": last_error,
        "stale_lock_recoveries": stale_lock_recoveries,
    }


def write_daemon_status(
    status_path: Path,
    *,
    active: bool,
    started_at: str,
    cycles: int,
    consecutive_failures: int,
    requested_by: str,
    last_summary: Dict[str, Any] | None,
    last_error: str | None,
    stop_reason: str | None = None,
    stale_lock_recoveries: int = 0,
) -> Dict[str, Any]:
    payload = {
        "active": active,
        "started_at": started_at,
        "updated_at": utc_now_iso(),
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "cycles": cycles,
        "consecutive_failures": consecutive_failures,
        "requested_by": requested_by,
        "last_summary": last_summary,
        "last_error": last_error,
        "stop_reason": stop_reason,
        "stale_lock_recoveries": stale_lock_recoveries,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def run_daemon_loop(
    args: argparse.Namespace,
    *,
    cycle_runner=run_cycle,
    stale_lock_recoverer=recover_stale_locks,
    sleep_fn=time.sleep,
) -> Dict[str, Any]:
    started_at = utc_now_iso()
    cycles = 0
    last_summary: Dict[str, Any] | None = None
    consecutive_failures = 0
    last_error: str | None = None
    stale_lock_recoveries = 0
    stop_reason = "completed"
    status_path = Path(args.status_path)

    record_event(
        "daemon_started",
        {
            "started_at": started_at,
            "interval_seconds": args.interval_seconds,
            "iterations": args.iterations,
            "requested_by": args.requested_by,
            "stale_lock_age_seconds": args.stale_lock_age_seconds,
            "max_consecutive_failures": args.max_consecutive_failures,
            "retry_backoff_seconds": args.retry_backoff_seconds,
        },
    )
    write_daemon_status(
        status_path,
        active=True,
        started_at=started_at,
        cycles=cycles,
        consecutive_failures=consecutive_failures,
        requested_by=args.requested_by,
        last_summary=last_summary,
        last_error=last_error,
        stale_lock_recoveries=stale_lock_recoveries,
    )

    try:
        while True:
            recovery = stale_lock_recoverer(stale_after_seconds=args.stale_lock_age_seconds)
            recovered_count = int(recovery.get("recovered_count") or 0)
            if recovered_count:
                stale_lock_recoveries += recovered_count
                record_event("daemon_stale_locks_recovered", recovery)

            try:
                last_summary = cycle_runner(cycle_namespace(args))
                cycles += 1
                consecutive_failures = 0
                last_error = None
                record_event(
                    "daemon_heartbeat",
                    {
                        "cycles": cycles,
                        "requested_by": args.requested_by,
                        "stale_lock_recoveries": stale_lock_recoveries,
                    },
                )
            except Exception as exc:
                consecutive_failures += 1
                last_error = str(exc)
                record_event(
                    "daemon_cycle_failed",
                    {
                        "cycles": cycles,
                        "consecutive_failures": consecutive_failures,
                        "error": last_error,
                    },
                )
                write_daemon_status(
                    status_path,
                    active=True,
                    started_at=started_at,
                    cycles=cycles,
                    consecutive_failures=consecutive_failures,
                    requested_by=args.requested_by,
                    last_summary=last_summary,
                    last_error=last_error,
                    stale_lock_recoveries=stale_lock_recoveries,
                )
                if consecutive_failures >= args.max_consecutive_failures:
                    stop_reason = "max_consecutive_failures"
                    record_event(
                        "daemon_max_failures_reached",
                        {
                            "cycles": cycles,
                            "consecutive_failures": consecutive_failures,
                            "error": last_error,
                        },
                    )
                    break
                sleep_fn(args.retry_backoff_seconds)
                continue

            write_daemon_status(
                status_path,
                active=True,
                started_at=started_at,
                cycles=cycles,
                consecutive_failures=consecutive_failures,
                requested_by=args.requested_by,
                last_summary=last_summary,
                last_error=last_error,
                stale_lock_recoveries=stale_lock_recoveries,
            )
            if args.iterations and cycles >= args.iterations:
                stop_reason = "iterations_complete"
                break
            sleep_fn(args.interval_seconds)
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        record_event(
            "daemon_interrupted",
            {
                "cycles": cycles,
            },
        )
    except Exception as exc:
        stop_reason = "daemon_exception"
        record_event(
            "daemon_failed",
            {
                "cycles": cycles,
                "error": str(exc),
            },
        )
        raise
    finally:
        summary = daemon_summary(
            started_at=started_at,
            cycles=cycles,
            last_summary=last_summary,
            stop_reason=stop_reason,
            consecutive_failures=consecutive_failures,
            last_error=last_error,
            stale_lock_recoveries=stale_lock_recoveries,
        )
        write_daemon_status(
            status_path,
            active=False,
            started_at=started_at,
            cycles=cycles,
            consecutive_failures=consecutive_failures,
            requested_by=args.requested_by,
            last_summary=last_summary,
            last_error=last_error,
            stop_reason=stop_reason,
            stale_lock_recoveries=stale_lock_recoveries,
        )
        record_event("daemon_stopped", summary)
        print(json.dumps(summary, ensure_ascii=False))

    return summary


def main() -> int:
    args = parse_args()
    run_daemon_loop(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
