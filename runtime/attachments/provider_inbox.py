from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping

import jsonschema

from common.jsonl_io import append_jsonl
from harness_common import utc_now_iso
from attachments.provider_attachment import (
    _read_jsonl,
    build_session_uid,
    provider_attachment_root,
    provider_inbox_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"


@lru_cache(maxsize=1)
def load_inbox_packet_schema() -> Dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / "inbox_packet.v1.schema.json").read_text(encoding="utf-8"))


def validate_inbox_packet(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_inbox_packet_schema())


def inject_session_packet(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
    packet_type: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    workspace_root = workspace_root.resolve()
    inbox_path = provider_inbox_path(
        workspace_root=workspace_root,
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
    if not (attachment_root / "session_attachment.v1.json").exists():
        raise FileNotFoundError(f"Missing generated session attachment: {attachment_root}")

    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    packet = {
        "schema_version": "inbox_packet.v1",
        "message_id": uuid.uuid4().hex,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "session_uid": session_uid,
        "packet_type": packet_type,
        "created_at": utc_now_iso(),
        "payload": dict(payload),
    }
    validate_inbox_packet(packet)
    append_jsonl(inbox_path, packet)
    return packet


def read_session_inbox(
    *,
    workspace_root: Path,
    provider_id: str,
    provider_profile: str,
    provider_session_id: str,
) -> List[Dict[str, Any]]:
    inbox_path = provider_inbox_path(
        workspace_root=workspace_root.resolve(),
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    rows = _read_jsonl(inbox_path)
    for row in rows:
        validate_inbox_packet(row)
    return rows
