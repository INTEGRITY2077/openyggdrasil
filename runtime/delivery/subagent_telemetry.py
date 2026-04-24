from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema

from harness_common import OPS_ROOT, append_jsonl, json_ready, utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_ROOT = OPS_ROOT / "telemetry"
TELEMETRY_EVENTS_PATH = TELEMETRY_ROOT / "subagent-events.jsonl"
TELEMETRY_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT
    / "providers"
    / "hermes"
    / "projects"
    / "harness"
    / "subagent_telemetry.v1.schema.json"
)


def ensure_telemetry_dirs() -> None:
    TELEMETRY_ROOT.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    return json.loads(TELEMETRY_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_event(event: Dict[str, Any]) -> None:
    jsonschema.validate(instance=event, schema=load_schema())


def build_event(
    *,
    trace_id: str,
    capability: str,
    role: str,
    actor: str,
    decider: str,
    action: str,
    status: str,
    producer: str,
    parent_question_id: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    scope: Optional[Dict[str, Any]] = None,
    inference: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event = {
        "schema_version": "subagent-telemetry.v1",
        "event_id": uuid.uuid4().hex,
        "timestamp": utc_now_iso(),
        "trace_id": trace_id,
        "parent_question_id": parent_question_id,
        "capability": capability,
        "role": role,
        "actor": actor,
        "decider": decider,
        "action": action,
        "status": status,
        "producer": producer,
        "artifacts": json_ready(artifacts or {}),
        "scope": json_ready(scope or {}),
        "inference": json_ready(inference or {"mode": "deterministic"}),
    }
    if details:
        event["details"] = json_ready(details)
    validate_event(event)
    return event


def record_subagent_event(
    *,
    trace_id: str,
    capability: str,
    role: str,
    actor: str,
    decider: str,
    action: str,
    status: str,
    producer: str,
    parent_question_id: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    scope: Optional[Dict[str, Any]] = None,
    inference: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
    path: Path = TELEMETRY_EVENTS_PATH,
) -> Dict[str, Any]:
    ensure_telemetry_dirs()
    event = build_event(
        trace_id=trace_id,
        capability=capability,
        role=role,
        actor=actor,
        decider=decider,
        action=action,
        status=status,
        producer=producer,
        parent_question_id=parent_question_id,
        artifacts=artifacts,
        scope=scope,
        inference=inference,
        details=details,
    )
    append_jsonl(path, event)
    return event
