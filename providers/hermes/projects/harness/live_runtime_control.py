from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict

import prepare_live_monitoring
from harness_common import utc_now_iso
from live_monitor import MONITOR_SNAPSHOT_PATH, MONITOR_STATUS_PATH, write_snapshot
from prepare_live_monitoring import PREPARED_STATE_PATH
from run_daemon import DAEMON_STATUS_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Explicit operator control surface for Hermes live monitoring runtime."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start daemon + live monitor in background.")
    start_parser.add_argument("--daemon-interval-seconds", type=float, default=15.0)
    start_parser.add_argument("--monitor-interval-seconds", type=float, default=5.0)
    start_parser.add_argument("--tail", type=int, default=200)
    start_parser.add_argument("--question-limit", type=int, default=10)
    start_parser.add_argument("--max-jobs", type=int, default=4)
    start_parser.add_argument("--chain-graph", action="store_true")
    start_parser.add_argument("--requested-by", default="live-runtime-control")

    subparsers.add_parser("stop", help="Stop background daemon + live monitor.")
    subparsers.add_parser("status", help="Show current runtime status.")

    snapshot_parser = subparsers.add_parser("snapshot", help="Write a one-shot live monitor snapshot.")
    snapshot_parser.add_argument("--tail", type=int, default=200)
    snapshot_parser.add_argument("--question-limit", type=int, default=10)
    snapshot_parser.add_argument("--output", default=str(MONITOR_SNAPSHOT_PATH))

    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = completed.stdout.strip()
        if not output or "No tasks are running" in output:
            return False
        return output.startswith('"')
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def stop_process_tree(pid: int) -> bool:
    if not process_alive(pid):
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return completed.returncode == 0
    os.kill(int(pid), signal.SIGTERM)
    return True


def write_status_override(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def stopped_daemon_payload(status: Dict[str, Any] | None, *, stop_reason: str) -> Dict[str, Any]:
    existing = status or {}
    return {
        "active": False,
        "started_at": existing.get("started_at"),
        "updated_at": utc_now_iso(),
        "pid": existing.get("pid"),
        "host": existing.get("host"),
        "cycles": existing.get("cycles", 0),
        "consecutive_failures": existing.get("consecutive_failures", 0),
        "requested_by": existing.get("requested_by"),
        "last_summary": existing.get("last_summary"),
        "last_error": existing.get("last_error"),
        "stop_reason": stop_reason,
        "stale_lock_recoveries": existing.get("stale_lock_recoveries", 0),
    }


def stopped_monitor_payload(status: Dict[str, Any] | None, *, stop_reason: str) -> Dict[str, Any]:
    existing = status or {}
    return {
        "active": False,
        "updated_at": utc_now_iso(),
        "pid": existing.get("pid"),
        "host": existing.get("host"),
        "output_path": existing.get("output_path", str(MONITOR_SNAPSHOT_PATH)),
        "last_snapshot_at": existing.get("last_snapshot_at"),
        "interval_seconds": existing.get("interval_seconds"),
        "tail": existing.get("tail"),
        "question_limit": existing.get("question_limit"),
        "stop_reason": stop_reason,
        "last_error": existing.get("last_error"),
    }


def runtime_status() -> Dict[str, Any]:
    daemon_status = read_json(DAEMON_STATUS_PATH) or {}
    monitor_status = read_json(MONITOR_STATUS_PATH) or {}
    prepared_state = read_json(PREPARED_STATE_PATH)
    daemon_pid = daemon_status.get("pid")
    monitor_pid = monitor_status.get("pid")
    return {
        "generated_at": utc_now_iso(),
        "daemon": {
            "status_path": str(DAEMON_STATUS_PATH),
            "active_flag": bool(daemon_status.get("active")),
            "pid": daemon_pid,
            "process_alive": process_alive(daemon_pid),
            "requested_by": daemon_status.get("requested_by"),
            "updated_at": daemon_status.get("updated_at"),
            "stop_reason": daemon_status.get("stop_reason"),
            "cycles": daemon_status.get("cycles"),
        },
        "monitor": {
            "status_path": str(MONITOR_STATUS_PATH),
            "active_flag": bool(monitor_status.get("active")),
            "pid": monitor_pid,
            "process_alive": process_alive(monitor_pid),
            "updated_at": monitor_status.get("updated_at"),
            "stop_reason": monitor_status.get("stop_reason"),
            "snapshot_path": (monitor_status or {}).get("output_path", str(MONITOR_SNAPSHOT_PATH)),
        },
        "prepared_state_path": str(PREPARED_STATE_PATH),
        "prepared_state": prepared_state,
    }


def start_runtime(args: argparse.Namespace) -> Dict[str, Any]:
    start_args = argparse.Namespace(
        daemon_interval_seconds=args.daemon_interval_seconds,
        monitor_interval_seconds=args.monitor_interval_seconds,
        tail=args.tail,
        question_limit=args.question_limit,
        max_jobs=args.max_jobs,
        chain_graph=args.chain_graph,
        requested_by=args.requested_by,
    )
    payload = prepare_live_monitoring.prepare_live_monitoring(start_args)
    return {
        "command": "start",
        "started_at": utc_now_iso(),
        "result": payload,
        "status": runtime_status(),
    }


def stop_runtime() -> Dict[str, Any]:
    daemon_status = read_json(DAEMON_STATUS_PATH) or {}
    monitor_status = read_json(MONITOR_STATUS_PATH) or {}

    daemon_pid = daemon_status.get("pid")
    monitor_pid = monitor_status.get("pid")

    daemon_stopped = stop_process_tree(int(daemon_pid)) if daemon_pid else False
    monitor_stopped = stop_process_tree(int(monitor_pid)) if monitor_pid else False

    daemon_stop_reason = "manual_stop" if daemon_pid else "not_running"
    monitor_stop_reason = "manual_stop" if monitor_pid else "not_running"

    daemon_payload = write_status_override(
        DAEMON_STATUS_PATH,
        stopped_daemon_payload(daemon_status, stop_reason=daemon_stop_reason),
    )
    monitor_payload = write_status_override(
        MONITOR_STATUS_PATH,
        stopped_monitor_payload(monitor_status, stop_reason=monitor_stop_reason),
    )

    return {
        "command": "stop",
        "stopped_at": utc_now_iso(),
        "daemon": {
            "pid": daemon_pid,
            "stop_attempted": bool(daemon_pid),
            "stop_succeeded": daemon_stopped or not daemon_pid,
            "status": daemon_payload,
        },
        "monitor": {
            "pid": monitor_pid,
            "stop_attempted": bool(monitor_pid),
            "stop_succeeded": monitor_stopped or not monitor_pid,
            "status": monitor_payload,
        },
    }


def snapshot_runtime(args: argparse.Namespace) -> Dict[str, Any]:
    output_path = Path(args.output)
    payload = write_snapshot(output_path, tail=args.tail, question_limit=args.question_limit)
    return {
        "command": "snapshot",
        "snapshot_path": str(output_path),
        "result": payload,
    }


def main() -> int:
    args = parse_args()
    if args.command == "start":
        payload = start_runtime(args)
    elif args.command == "stop":
        payload = stop_runtime()
    elif args.command == "status":
        payload = {
            "command": "status",
            "result": runtime_status(),
        }
    elif args.command == "snapshot":
        payload = snapshot_runtime(args)
    else:
        raise ValueError(f"unsupported command: {args.command}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
