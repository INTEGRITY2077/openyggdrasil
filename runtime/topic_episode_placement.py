from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "topic_episode_placement.v1.schema.json"


def load_placement_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_placement_verdict(verdict: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(verdict), schema=load_placement_schema())


def ensure_promotion_job_has_placement(job: Mapping[str, Any]) -> dict[str, Any]:
    payload = job.get("payload", {})
    verdict = payload.get("placement_verdict")
    if not isinstance(verdict, Mapping):
        raise RuntimeError("promotion job is missing placement_verdict")
    verdict_dict = dict(verdict)
    validate_placement_verdict(verdict_dict)
    if not verdict_dict.get("place"):
        raise RuntimeError("promotion job placement_verdict does not allow placement")
    payload_session = payload.get("session_id")
    verdict_session = verdict_dict.get("session_id")
    if payload_session and verdict_session and str(payload_session) != str(verdict_session):
        raise RuntimeError("promotion job placement_verdict session_id does not match payload.session_id")
    payload_profile = payload.get("profile") or "default"
    verdict_profile = verdict_dict.get("profile") or "default"
    if str(payload_profile) != str(verdict_profile):
        raise RuntimeError("promotion job placement_verdict profile does not match payload.profile")
    return verdict_dict
