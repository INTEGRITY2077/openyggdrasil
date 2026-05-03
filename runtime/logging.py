"""
Structured Logging — 14차 Axis 5: print(json.dumps) → 구조화 로깅.

Log Level Filtering: 환경변수 LOG_LEVEL 또는 --log-level로 제어.
  LOG_LEVEL=ERROR → WARN/INFO 이하 출력하지 않음.

Usage:
    from runtime.logging import info, warn, error, log_event
    info("producer_start", pid=os.getpid())
    error("json_parse_failed", path=str(file), exc=str(e))
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# 로그 레벨 (낮을수록 많이 출력)
LEVELS = {"ERROR": 40, "WARN": 30, "INFO": 20, "DEBUG": 10}

_current_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
_current_level = LEVELS.get(_current_level_name, 20)


def set_level(level: str) -> None:
    """로그 레벨 설정. ERROR|WARN|INFO|DEBUG"""
    global _current_level, _current_level_name
    _current_level_name = level.upper()
    _current_level = LEVELS.get(_current_level_name, 20)


def get_level() -> str:
    return _current_level_name


def _should_emit(level: str) -> bool:
    return LEVELS.get(level, 0) >= _current_level


def _emit(level: str, event: str, **kwargs: Any) -> None:
    """JSON 라인을 stderr로 출력."""
    if not _should_emit(level):
        return
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
    """stdout JSON 로그 (기존 print(json.dumps) 대체). LOG_LEVEL 적용."""
    if not _should_emit("INFO"):
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    print(json.dumps(record, ensure_ascii=False))
