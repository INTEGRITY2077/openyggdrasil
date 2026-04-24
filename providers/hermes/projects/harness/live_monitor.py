from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from graph_freshness import current_graph_freshness
from harness_common import EVENTS_PATH, OPS_ROOT, read_jsonl, utc_now_iso
from plugin_logger import PLUGIN_LOG_EVENTS_PATH, read_plugin_events
from queue_status import QUEUE_STATUS_PATH, write_queue_status
from run_daemon import DAEMON_STATUS_PATH
from subagent_telemetry import TELEMETRY_EVENTS_PATH


MONITOR_ROOT = OPS_ROOT / "monitoring"
MONITOR_SNAPSHOT_PATH = MONITOR_ROOT / "live-monitor.json"
MONITOR_STATUS_PATH = MONITOR_ROOT / "monitor-status.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate live plugin-plane monitoring data for Hermes runtime observation."
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--tail", type=int, default=200)
    parser.add_argument("--question-limit", type=int, default=10)
    parser.add_argument("--output", default=str(MONITOR_SNAPSHOT_PATH))
    parser.add_argument("--status-path", default=str(MONITOR_STATUS_PATH))
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def tail_rows(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return rows
    return rows[-limit:]


def _normalize_timestamp(value: str | None) -> str:
    return value or ""


def _add_lineage_event(
    bucket: Dict[str, Dict[str, Any]],
    *,
    parent_question_id: str | None,
    source: str,
    event_type: str | None,
    timestamp: str | None,
    session_id: str | None = None,
    profile: str | None = None,
) -> None:
    if not parent_question_id:
        return
    item = bucket.setdefault(
        parent_question_id,
        {
            "parent_question_id": parent_question_id,
            "latest_timestamp": "",
            "session_id": session_id,
            "profile": profile,
            "sources": {},
        },
    )
    if session_id and not item.get("session_id"):
        item["session_id"] = session_id
    if profile and not item.get("profile"):
        item["profile"] = profile
    if _normalize_timestamp(timestamp) >= _normalize_timestamp(item.get("latest_timestamp")):
        item["latest_timestamp"] = timestamp or ""
    source_bucket = item["sources"].setdefault(
        source,
        {
            "count": 0,
            "latest_event_type": None,
            "latest_timestamp": "",
        },
    )
    source_bucket["count"] += 1
    if _normalize_timestamp(timestamp) >= _normalize_timestamp(source_bucket.get("latest_timestamp")):
        source_bucket["latest_timestamp"] = timestamp or ""
        source_bucket["latest_event_type"] = event_type


def summarize_recent_questions(
    *,
    plugin_events: List[Dict[str, Any]],
    telemetry_events: List[Dict[str, Any]],
    queue_events: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for row in plugin_events:
        _add_lineage_event(
            bucket,
            parent_question_id=row.get("parent_question_id"),
            source="plugin",
            event_type=row.get("event_type"),
            timestamp=row.get("timestamp"),
            session_id=row.get("session_id"),
            profile=row.get("profile"),
        )
    for row in telemetry_events:
        scope = row.get("scope") or {}
        _add_lineage_event(
            bucket,
            parent_question_id=row.get("parent_question_id"),
            source="telemetry",
            event_type=row.get("action"),
            timestamp=row.get("timestamp"),
            session_id=scope.get("session_id"),
            profile=scope.get("profile"),
        )
    for row in queue_events:
        _add_lineage_event(
            bucket,
            parent_question_id=row.get("parent_question_id"),
            source="queue",
            event_type=row.get("event_type"),
            timestamp=row.get("timestamp") or row.get("created_at"),
        )
    recent = sorted(
        bucket.values(),
        key=lambda item: item.get("latest_timestamp") or "",
        reverse=True,
    )
    return recent[:limit]


def summarize_recent_events(
    *,
    plugin_events: List[Dict[str, Any]],
    telemetry_events: List[Dict[str, Any]],
    queue_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "plugin": {
            "count": len(plugin_events),
            "latest_event_type": plugin_events[-1].get("event_type") if plugin_events else None,
            "latest_timestamp": plugin_events[-1].get("timestamp") if plugin_events else None,
        },
        "telemetry": {
            "count": len(telemetry_events),
            "latest_event_type": telemetry_events[-1].get("action") if telemetry_events else None,
            "latest_timestamp": telemetry_events[-1].get("timestamp") if telemetry_events else None,
        },
        "queue": {
            "count": len(queue_events),
            "latest_event_type": queue_events[-1].get("event_type") if queue_events else None,
            "latest_timestamp": (
                queue_events[-1].get("timestamp") or queue_events[-1].get("created_at")
                if queue_events
                else None
            ),
        },
    }


def build_live_monitor_snapshot(*, tail: int = 200, question_limit: int = 10) -> Dict[str, Any]:
    queue_status = write_queue_status()
    daemon_status = read_json(DAEMON_STATUS_PATH)
    plugin_events = tail_rows(read_plugin_events(path=PLUGIN_LOG_EVENTS_PATH), tail)
    telemetry_events = tail_rows(read_jsonl(TELEMETRY_EVENTS_PATH), tail)
    queue_events = tail_rows(read_jsonl(EVENTS_PATH), tail)
    recent_questions = summarize_recent_questions(
        plugin_events=plugin_events,
        telemetry_events=telemetry_events,
        queue_events=queue_events,
        limit=question_limit,
    )
    return {
        "generated_at": utc_now_iso(),
        "daemon_status": daemon_status,
        "queue_status": queue_status,
        "graph_freshness": current_graph_freshness(),
        "event_summary": summarize_recent_events(
            plugin_events=plugin_events,
            telemetry_events=telemetry_events,
            queue_events=queue_events,
        ),
        "recent_questions": recent_questions,
        "paths": {
            "daemon_status": str(DAEMON_STATUS_PATH),
            "queue_status": str(QUEUE_STATUS_PATH),
            "plugin_events": str(PLUGIN_LOG_EVENTS_PATH),
            "telemetry_events": str(TELEMETRY_EVENTS_PATH),
            "queue_events": str(EVENTS_PATH),
        },
    }


def write_monitor_status(
    status_path: Path,
    *,
    active: bool,
    output_path: Path,
    last_snapshot_at: str | None,
    interval_seconds: float,
    tail: int,
    question_limit: int,
    stop_reason: str | None = None,
    last_error: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "active": active,
        "updated_at": utc_now_iso(),
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "output_path": str(output_path),
        "last_snapshot_at": last_snapshot_at,
        "interval_seconds": interval_seconds,
        "tail": tail,
        "question_limit": question_limit,
        "stop_reason": stop_reason,
        "last_error": last_error,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def write_snapshot(output_path: Path, *, tail: int, question_limit: int) -> Dict[str, Any]:
    payload = build_live_monitor_snapshot(tail=tail, question_limit=question_limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def run_watch_loop(args: argparse.Namespace, *, sleep_fn=time.sleep) -> Dict[str, Any]:
    output_path = Path(args.output)
    status_path = Path(args.status_path)
    last_snapshot_at: str | None = None
    last_error: str | None = None
    stop_reason = "completed"
    write_monitor_status(
        status_path,
        active=True,
        output_path=output_path,
        last_snapshot_at=last_snapshot_at,
        interval_seconds=args.interval_seconds,
        tail=args.tail,
        question_limit=args.question_limit,
    )
    try:
        while True:
            payload = write_snapshot(output_path, tail=args.tail, question_limit=args.question_limit)
            last_snapshot_at = payload["generated_at"]
            last_error = None
            write_monitor_status(
                status_path,
                active=True,
                output_path=output_path,
                last_snapshot_at=last_snapshot_at,
                interval_seconds=args.interval_seconds,
                tail=args.tail,
                question_limit=args.question_limit,
            )
            sleep_fn(args.interval_seconds)
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
    except Exception as exc:
        stop_reason = "monitor_exception"
        last_error = str(exc)
        raise
    finally:
        write_monitor_status(
            status_path,
            active=False,
            output_path=output_path,
            last_snapshot_at=last_snapshot_at,
            interval_seconds=args.interval_seconds,
            tail=args.tail,
            question_limit=args.question_limit,
            stop_reason=stop_reason,
            last_error=last_error,
        )
    return read_json(status_path) or {}


def main() -> int:
    args = parse_args()
    if args.watch:
        run_watch_loop(args)
        return 0
    payload = write_snapshot(Path(args.output), tail=args.tail, question_limit=args.question_limit)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
