"""
Structured Logging — 14차 Axis 5: print(json.dumps) → 구조화 로깅.

Usage:
    from runtime.logging import info, warn, error, log_event
    info("producer_start", pid=os.getpid())
    error("json_parse_failed", path=str(file), exc=str(e))
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _emit(level: str, event: str, **kwargs: Any) -> None:
    """JSON 라인을 stderr로 출력."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **kwargs,
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)


def info(event: str, **kwargs: Any) -> None:
    _emit("INFO", event, **kwargs)


def warn(event: str, **kwargs: Any) -> None:
    _emit("WARN", event, **kwargs)


def error(event: str, **kwargs: Any) -> None:
    _emit("ERROR", event, **kwargs)


def log_event(event: str, **kwargs: Any) -> None:
    """stdout JSON 로그 (기존 print(json.dumps) 대체)."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    print(json.dumps(record, ensure_ascii=False))
