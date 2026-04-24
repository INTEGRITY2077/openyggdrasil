from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from harness_common import OPS_ROOT, utc_now_iso
from live_monitor import MONITOR_ROOT, MONITOR_SNAPSHOT_PATH, MONITOR_STATUS_PATH
from run_daemon import DAEMON_STATUS_PATH


PROJECT_ROOT = Path(__file__).resolve().parent
DAEMON_SCRIPT = PROJECT_ROOT / "run_daemon.py"
MONITOR_SCRIPT = PROJECT_ROOT / "live_monitor.py"
PREPARED_STATE_PATH = MONITOR_ROOT / "prepared-state.json"
DAEMON_STDOUT_PATH = MONITOR_ROOT / "daemon.stdout.log"
DAEMON_STDERR_PATH = MONITOR_ROOT / "daemon.stderr.log"
MONITOR_STDOUT_PATH = MONITOR_ROOT / "monitor.stdout.log"
MONITOR_STDERR_PATH = MONITOR_ROOT / "monitor.stderr.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start live daemon + monitor processes so Hermes sessions can be observed in real time."
    )
    parser.add_argument("--daemon-interval-seconds", type=float, default=15.0)
    parser.add_argument("--monitor-interval-seconds", type=float, default=5.0)
    parser.add_argument("--tail", type=int, default=200)
    parser.add_argument("--question-limit", type=int, default=10)
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument("--chain-graph", action="store_true")
    parser.add_argument("--requested-by", default="live-monitor-prep")
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def launch_background(command: list[str], *, stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    with stdout_path.open("a", encoding="utf-8") as stdout_handle, stderr_path.open(
        "a",
        encoding="utf-8",
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
            close_fds=True,
        )
    return int(process.pid)


def prepare_live_monitoring(args: argparse.Namespace) -> Dict[str, Any]:
    MONITOR_ROOT.mkdir(parents=True, exist_ok=True)
    daemon_status = read_json(DAEMON_STATUS_PATH) or {}
    monitor_status = read_json(MONITOR_STATUS_PATH) or {}

    daemon_started = False
    monitor_started = False
    daemon_pid = daemon_status.get("pid")
    monitor_pid = monitor_status.get("pid")

    if not daemon_status.get("active"):
        daemon_pid = launch_background(
            [
                sys.executable,
                str(DAEMON_SCRIPT),
                "--interval-seconds",
                str(args.daemon_interval_seconds),
                "--profiles",
                "wiki",
                "--max-jobs",
                str(args.max_jobs),
                "--requested-by",
                args.requested_by,
                "--status-path",
                str(DAEMON_STATUS_PATH),
                *(["--chain-graph"] if args.chain_graph else []),
            ],
            stdout_path=DAEMON_STDOUT_PATH,
            stderr_path=DAEMON_STDERR_PATH,
        )
        daemon_started = True

    if not monitor_status.get("active"):
        monitor_pid = launch_background(
            [
                sys.executable,
                str(MONITOR_SCRIPT),
                "--watch",
                "--interval-seconds",
                str(args.monitor_interval_seconds),
                "--tail",
                str(args.tail),
                "--question-limit",
                str(args.question_limit),
                "--output",
                str(MONITOR_SNAPSHOT_PATH),
                "--status-path",
                str(MONITOR_STATUS_PATH),
            ],
            stdout_path=MONITOR_STDOUT_PATH,
            stderr_path=MONITOR_STDERR_PATH,
        )
        monitor_started = True

    payload = {
        "prepared_at": utc_now_iso(),
        "daemon_started": daemon_started,
        "monitor_started": monitor_started,
        "daemon_pid": daemon_pid,
        "monitor_pid": monitor_pid,
        "daemon_status_path": str(DAEMON_STATUS_PATH),
        "monitor_status_path": str(MONITOR_STATUS_PATH),
        "monitor_snapshot_path": str(MONITOR_SNAPSHOT_PATH),
        "daemon_stdout_path": str(DAEMON_STDOUT_PATH),
        "daemon_stderr_path": str(DAEMON_STDERR_PATH),
        "monitor_stdout_path": str(MONITOR_STDOUT_PATH),
        "monitor_stderr_path": str(MONITOR_STDERR_PATH),
    }
    PREPARED_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    args = parse_args()
    payload = prepare_live_monitoring(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
