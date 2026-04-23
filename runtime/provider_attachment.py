from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping

import jsonschema

from harness_common import utc_now_iso


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
ATTACHMENT_RUNTIME_DIRNAME = ".yggdrasil"
SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_component(value: str) -> str:
    cleaned = SAFE_COMPONENT_RE.sub("_", value.strip())
    return cleaned or "unknown"


def build_session_uid(*, provider_id: str, provider_profile: str, provider_session_id: str) -> str:
    return ":".join(
        [
            _safe_component(provider_id),
            _safe_component(provider_profile),
            _safe_component(provider_session_id),
        ]
    )


def session_uid_path_component(session_uid: str) -> str:
    # Keep the logical session UID stable in contract payloads, but use a
    # filesystem-safe component for Windows paths and filenames.
    return _safe_component(session_uid)


def runtime_root_for(workspace_root: Path) -> Path:
    return workspace_root / ATTACHMENT_RUNTIME_DIRNAME


def provider_attachment_root(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> Path:
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return (
        runtime_root_for(workspace_root)
        / "providers"
        / _safe_component(provider_id)
        / _safe_component(provider_profile)
        / session_uid_path_component(session_uid)
    )


def provider_inbox_path(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> Path:
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return (
        runtime_root_for(workspace_root)
        / "inbox"
        / _safe_component(provider_id)
        / _safe_component(provider_profile)
        / f"{session_uid_path_component(session_uid)}.jsonl"
    )


def _load_schema(filename: str) -> Dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_provider_descriptor_schema() -> Dict[str, Any]:
    return _load_schema("provider_descriptor.v1.schema.json")


@lru_cache(maxsize=None)
def load_session_attachment_schema() -> Dict[str, Any]:
    return _load_schema("session_attachment.v1.schema.json")


@lru_cache(maxsize=None)
def load_inbox_binding_schema() -> Dict[str, Any]:
    return _load_schema("inbox_binding.v1.schema.json")


@lru_cache(maxsize=None)
def load_turn_delta_schema() -> Dict[str, Any]:
    return _load_schema("turn_delta.v1.schema.json")


def validate_provider_descriptor(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_provider_descriptor_schema())


def validate_session_attachment(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_session_attachment_schema())


def validate_inbox_binding(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_inbox_binding_schema())


def validate_turn_delta(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_turn_delta_schema())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False) + "\n")


def bootstrap_skill_provider_session(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    origin_kind: str,
    origin_locator: Mapping[str, Any],
    provider_extras: Mapping[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    workspace_root = workspace_root.resolve()
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    attachment_root = provider_attachment_root(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    inbox_path = provider_inbox_path(
        workspace_root=workspace_root,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )

    descriptor = {
        "schema_version": "provider_descriptor.v1",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "adapter_mode": "skill_generated",
        "generated_at": utc_now_iso(),
        "generated_by": "yggdrasil-skill-bootstrap",
        "workspace_root": str(workspace_root),
        "capabilities": {
            "attachment": True,
            "turn_delta": True,
            "reverse_inbox": True,
            "heartbeat": False
        },
        "provider_extras": dict(provider_extras or {})
    }
    validate_provider_descriptor(descriptor)

    attachment = {
        "schema_version": "session_attachment.v1",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "origin_kind": origin_kind,
        "origin_locator": dict(origin_locator),
        "update_mode": "push-delta",
        "created_at": utc_now_iso(),
        "attachment_root": str(attachment_root),
        "workspace_root": str(workspace_root),
        "capabilities": {
            "turn_delta": True,
            "reverse_inbox": True,
            "heartbeat": False
        },
        "expires_at": None
    }
    validate_session_attachment(attachment)

    inbox_binding = {
        "schema_version": "inbox_binding.v1",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "inbox_mode": "jsonl_file",
        "target_kind": "session_bound",
        "inbox_path": str(inbox_path),
        "workspace_root": str(workspace_root),
        "created_at": utc_now_iso()
    }
    validate_inbox_binding(inbox_binding)

    _write_json(attachment_root / "provider_descriptor.v1.json", descriptor)
    _write_json(attachment_root / "session_attachment.v1.json", attachment)
    _write_json(attachment_root / "inbox_binding.v1.json", inbox_binding)

    return {
        "provider_descriptor": descriptor,
        "session_attachment": attachment,
        "inbox_binding": inbox_binding
    }


def append_turn_delta(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    sequence: int,
    role: str,
    content: str,
    summary: str | None = None,
) -> Dict[str, Any]:
    attachment_root = provider_attachment_root(
        workspace_root=workspace_root.resolve(),
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    payload = {
        "schema_version": "turn_delta.v1",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "delta_id": uuid.uuid4().hex,
        "sequence": sequence,
        "created_at": utc_now_iso(),
        "role": role,
        "content": content,
        "summary": summary
    }
    validate_turn_delta(payload)
    _append_jsonl(attachment_root / "turn_delta.v1.jsonl", payload)
    return payload


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def discover_generated_provider_sessions(workspace_root: Path) -> List[Dict[str, Any]]:
    runtime_root = runtime_root_for(workspace_root.resolve())
    attachments_root = runtime_root / "providers"
    rows: List[Dict[str, Any]] = []
    if not attachments_root.exists():
        return rows

    for attachment_path in sorted(attachments_root.rglob("session_attachment.v1.json")):
        attachment_root = attachment_path.parent
        descriptor_path = attachment_root / "provider_descriptor.v1.json"
        inbox_binding_path = attachment_root / "inbox_binding.v1.json"
        turn_delta_path = attachment_root / "turn_delta.v1.jsonl"
        if not descriptor_path.exists() or not inbox_binding_path.exists():
            continue

        descriptor = _read_json(descriptor_path)
        attachment = _read_json(attachment_path)
        inbox_binding = _read_json(inbox_binding_path)
        turn_deltas = _read_jsonl(turn_delta_path)

        validate_provider_descriptor(descriptor)
        validate_session_attachment(attachment)
        validate_inbox_binding(inbox_binding)
        for row in turn_deltas:
            validate_turn_delta(row)

        rows.append(
            {
                "provider_descriptor": descriptor,
                "session_attachment": attachment,
                "inbox_binding": inbox_binding,
                "turn_delta_count": len(turn_deltas),
                "latest_turn_sequence": max((int(row["sequence"]) for row in turn_deltas), default=0),
            }
        )

    return rows
