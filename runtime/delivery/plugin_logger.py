from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema

from harness_common import OPS_ROOT, append_jsonl, json_ready, utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_LOG_ROOT = OPS_ROOT / "plugin-logger"
PLUGIN_LOG_EVENTS_PATH = PLUGIN_LOG_ROOT / "plugin-events.jsonl"
PLUGIN_LOG_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT
    / "providers"
    / "hermes"
    / "projects"
    / "harness"
    / "plugin_logger.v1.schema.json"
)


def ensure_plugin_log_dirs() -> None:
    PLUGIN_LOG_ROOT.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    return json.loads(PLUGIN_LOG_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_event(event: Dict[str, Any]) -> None:
    jsonschema.validate(instance=event, schema=load_schema())


def build_plugin_event(
    *,
    event_type: str,
    actor: str,
    parent_question_id: Optional[str] = None,
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    query_text: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event = {
        "schema_version": "plugin-logger.v1",
        "event_id": uuid.uuid4().hex,
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "actor": actor,
        "parent_question_id": parent_question_id,
        "profile": profile,
        "session_id": session_id,
        "query_text": query_text,
        "artifacts": json_ready(artifacts or {}),
        "state": json_ready(state or {}),
    }
    validate_event(event)
    return event


def record_plugin_event(
    *,
    event_type: str,
    actor: str,
    parent_question_id: Optional[str] = None,
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    query_text: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    path: Path | None = None,
) -> Dict[str, Any]:
    ensure_plugin_log_dirs()
    event = build_plugin_event(
        event_type=event_type,
        actor=actor,
        parent_question_id=parent_question_id,
        profile=profile,
        session_id=session_id,
        query_text=query_text,
        artifacts=artifacts,
        state=state,
    )
    append_jsonl(path or PLUGIN_LOG_EVENTS_PATH, event)
    return event


def read_plugin_events(*, path: Path | None = None) -> list[Dict[str, Any]]:
    target = path or PLUGIN_LOG_EVENTS_PATH
    if not target.exists():
        return []
    rows: list[Dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows
