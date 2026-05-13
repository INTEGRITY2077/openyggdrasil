from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from source_ref.hermes_session_json import _canonical_anchor_hash

from runtime.capture.provider_current_source_bridge import (
    build_memory_ticket_payload_from_existing_provider_exchange,
)


SCHEMA_VERSION = "provider_admission_sidecar.v1"
STATE_SCHEMA_VERSION = "provider_admission_sidecar_state.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return seen
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, Mapping) and row.get("dedupe_key"):
            seen.add(str(row["dedupe_key"]))
    return seen


def _append_state(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _message_text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _session_id_from_path(path: Path) -> str:
    name = path.name
    if name.startswith("session_") and name.endswith(".json"):
        return name[len("session_") : -len(".json")]
    return path.stem


def _session_messages(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return [dict(message) for message in messages if isinstance(message, Mapping)]


def _iter_user_assistant_ranges(messages: list[dict[str, Any]]) -> Iterable[tuple[int, int, str, str, list[dict[str, Any]]]]:
    for index in range(max(0, len(messages) - 1)):
        first = messages[index]
        second = messages[index + 1]
        if first.get("role") != "user" or second.get("role") != "assistant":
            continue
        user_text = _message_text(first)
        assistant_text = _message_text(second)
        if not user_text or not assistant_text:
            continue
        selected = [first, second]
        yield index, index + 1, user_text, assistant_text, selected


def _dedupe_key(*, source_ref: str, start: int, end: int, anchor_hash: str) -> str:
    return f"{source_ref}:{start}:{end}:{anchor_hash}"


def _state_row(
    *,
    dedupe_key: str,
    source_ref: str,
    start: int,
    end: int,
    anchor_hash: str,
    status: str,
    reason_code: str | None = None,
    delivery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "schema_version": STATE_SCHEMA_VERSION,
        "created_at": _now(),
        "dedupe_key": dedupe_key,
        "source_ref": source_ref,
        "message_index_range": {"start": start, "end": end},
        "anchor_hash": anchor_hash,
        "status": status,
    }
    if reason_code:
        row["reason_code"] = reason_code
    if delivery:
        for key in ("delivery_id", "mail_id", "work_order_id", "recipient", "message_type", "status"):
            if key in delivery:
                row[f"delivery_{key}" if key == "status" else key] = delivery[key]
    return row


def process_provider_session_file(
    *,
    session_path: str | Path,
    sessions_dir: str | Path,
    state_path: str | Path,
    submit: bool = False,
    recipient: str = "OP1",
    provider_id: str | None = None,
    provider_profile: str | None = None,
) -> dict[str, Any]:
    """Scan one Provider session JSON and admit each salient user/assistant pair once."""

    session_path = Path(session_path)
    sessions_dir = Path(sessions_dir)
    state_path = Path(state_path)
    payload = _read_json(session_path)
    messages = _session_messages(payload)
    session_id = str(payload.get("provider_session_id") or _session_id_from_path(session_path)).strip()
    active_provider_id = str(provider_id or payload.get("provider_id") or "hermes").strip()
    active_provider_profile = str(provider_profile or payload.get("provider_profile") or "openyggdrasil-provider").strip()
    source_ref = f"hermes-session-json://{session_id}"
    seen = _load_state(state_path)
    prepared: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []

    for start, end, user_text, assistant_text, selected in _iter_user_assistant_ranges(messages):
        anchor_hash = _canonical_anchor_hash(selected)
        dedupe = _dedupe_key(source_ref=source_ref, start=start, end=end, anchor_hash=anchor_hash)
        if dedupe in seen:
            skipped.append({"source_ref": source_ref, "message_index_range": {"start": start, "end": end}, "reason_code": "already_processed"})
            continue
        ticket = build_memory_ticket_payload_from_existing_provider_exchange(
            provider_id=active_provider_id,
            provider_profile=active_provider_profile,
            provider_session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
            message_index_range={"start": start, "end": end},
            anchor_hash=anchor_hash,
            sessions_dir=sessions_dir,
        )
        if ticket.get("schema_version") != "memory_ticket.v1" or ticket.get("status") == "typed_unavailable":
            reason = str(ticket.get("reason_code") or "typed_unavailable")
            _append_state(
                state_path,
                _state_row(
                    dedupe_key=dedupe,
                    source_ref=source_ref,
                    start=start,
                    end=end,
                    anchor_hash=anchor_hash,
                    status="skipped",
                    reason_code=reason,
                ),
            )
            skipped.append({"source_ref": source_ref, "message_index_range": {"start": start, "end": end}, "reason_code": reason})
            seen.add(dedupe)
            continue
        delivery: dict[str, Any] | None = None
        if submit:
            from runtime.delivery.postman_live_delivery import submit_live_delivery

            delivery = submit_live_delivery(
                recipient=recipient,
                message_type="memory_ticket",
                payload=ticket,
                provider_id=active_provider_id,
                mail_id=f"memticket-{uuid.uuid4().hex[:6]}",
            )
            deliveries.append(delivery)
        _append_state(
            state_path,
            _state_row(
                dedupe_key=dedupe,
                source_ref=source_ref,
                start=start,
                end=end,
                anchor_hash=anchor_hash,
                status="delivered" if delivery else "prepared",
                delivery=delivery,
            ),
        )
        prepared.append(
            {
                "source_ref": source_ref,
                "message_index_range": {"start": start, "end": end},
                "anchor_hash": anchor_hash,
                "canonical_topic_key": ticket.get("canonical_topic_key"),
                "canonical_topic_title": ticket.get("canonical_topic_title"),
                "submitted": bool(delivery),
                "delivery_id": (delivery or {}).get("delivery_id"),
                "mail_id": (delivery or {}).get("mail_id"),
                "work_order_id": (delivery or {}).get("work_order_id"),
            }
        )
        seen.add(dedupe)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "done",
        "session_path_name": session_path.name,
        "provider_id": active_provider_id,
        "provider_profile": active_provider_profile,
        "provider_session_id": session_id,
        "prepared_count": len(prepared),
        "skipped_count": len(skipped),
        "delivery_count": len(deliveries),
        "prepared": prepared,
        "skipped": skipped,
        "hard_nonclaims": {
            "raw_provider_material_included": False,
            "postman_semantic_quality_owner": False,
            "worker_judgment_claimed": False,
            "production_ready": False,
        },
    }


def process_provider_session_dir(
    *,
    sessions_dir: str | Path,
    state_path: str | Path,
    submit: bool = False,
    recipient: str = "OP1",
) -> dict[str, Any]:
    sessions_dir = Path(sessions_dir)
    results = [
        process_provider_session_file(
            session_path=path,
            sessions_dir=sessions_dir,
            state_path=state_path,
            submit=submit,
            recipient=recipient,
        )
        for path in sorted(sessions_dir.glob("session_*.json"))
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "done",
        "session_count": len(results),
        "prepared_count": sum(int(result.get("prepared_count") or 0) for result in results),
        "skipped_count": sum(int(result.get("skipped_count") or 0) for result in results),
        "delivery_count": sum(int(result.get("delivery_count") or 0) for result in results),
        "results": results,
    }


__all__ = [
    "SCHEMA_VERSION",
    "process_provider_session_dir",
    "process_provider_session_file",
]
