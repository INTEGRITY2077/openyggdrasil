from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from harness_common import record_event, utc_now_iso
from queue_status import QUEUE_STATUS_PATH, write_queue_status


PROJECT_ROOT = Path(__file__).resolve().parent
DISCOVERY_SCRIPT = PROJECT_ROOT / "discover_sessions.py"
WORKER_SCRIPT = PROJECT_ROOT / "run_worker.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one harness service cycle: discovery, queue status, worker, queue status."
    )
    parser.add_argument("--profiles", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chain-graph", action="store_true")
    parser.add_argument("--min-assistant-chars", type=int, default=80)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--skip-worker", action="store_true")
    parser.add_argument("--requested-by", default="service-cycle")
    return parser.parse_args()


def python_command(script: Path, args: List[str]) -> List[str]:
    return [sys.executable, str(script), *args]


def run_subprocess(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def parse_key_value_metrics(text: str) -> Dict[str, str]:
    metrics: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for token in line.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            metrics[key.strip()] = value.strip()
    return metrics


def build_cycle_summary(
    *,
    started_at: str,
    finished_at: str,
    discovery_metrics: Dict[str, str],
    worker_metrics: Dict[str, str],
    status_before: Dict[str, Any],
    status_after: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "discovery": discovery_metrics,
        "worker": worker_metrics,
        "before": status_before["counts"],
        "after": status_after["counts"],
        "locks_after": status_after["active_locks"],
        "status_path": str(QUEUE_STATUS_PATH),
    }


def discovery_args(args: argparse.Namespace) -> List[str]:
    values: List[str] = []
    if args.profiles:
        values.extend(["--profiles", *args.profiles])
    if args.limit:
        values.extend(["--limit", str(args.limit)])
    if args.chain_graph:
        values.append("--chain-graph")
    if args.min_assistant_chars != 80:
        values.extend(["--min-assistant-chars", str(args.min_assistant_chars)])
    if args.requested_by:
        values.extend(["--requested-by", args.requested_by])
    return values


def worker_args(args: argparse.Namespace) -> List[str]:
    values: List[str] = ["--once"]
    if args.max_jobs:
        values.extend(["--max-jobs", str(args.max_jobs)])
    return values


def run_cycle(args: argparse.Namespace) -> Dict[str, Any]:
    started_at = utc_now_iso()
    status_before = write_queue_status()
    discovery_metrics: Dict[str, str] = {}
    worker_metrics: Dict[str, str] = {}

    record_event(
        "service_cycle_started",
        {
            "started_at": started_at,
            "requested_by": args.requested_by,
        },
    )

    if not args.skip_discovery:
        discovery = run_subprocess(python_command(DISCOVERY_SCRIPT, discovery_args(args)))
        if discovery.returncode != 0:
            raise RuntimeError(
                discovery.stderr.strip() or discovery.stdout.strip() or "discovery failed"
            )
        discovery_metrics = parse_key_value_metrics(discovery.stdout)

    if not args.skip_worker:
        worker = run_subprocess(python_command(WORKER_SCRIPT, worker_args(args)))
        if worker.returncode != 0:
            raise RuntimeError(
                worker.stderr.strip() or worker.stdout.strip() or "worker failed"
            )
        worker_metrics = parse_key_value_metrics(worker.stdout)

    status_after = write_queue_status()
    finished_at = utc_now_iso()
    summary = build_cycle_summary(
        started_at=started_at,
        finished_at=finished_at,
        discovery_metrics=discovery_metrics,
        worker_metrics=worker_metrics,
        status_before=status_before,
        status_after=status_after,
    )
    record_event(
        "service_cycle_completed",
        {
            "started_at": started_at,
            "finished_at": finished_at,
            "summary": summary,
        },
    )
    return summary


def main() -> int:
    args = parse_args()
    summary = run_cycle(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
