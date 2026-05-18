from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "hermes_state_db_source.v1"


def _home_hermes_state_db() -> Path:
    return Path.home() / ".hermes" / "state.db"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_hermes_state_db_session(
    *,
    session_id: str,
    state_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read one Hermes state.db session as a bounded Provider source surface.

    The returned shape intentionally mirrors the session JSON adapter used by
    the OpenYggdrasil source_ref resolver. Raw text is kept inside the local
    source cache only; Provider mail still carries pointer fields.
    """

    session_id = str(session_id or "").strip()
    if not session_id:
        return {"status": "typed_unavailable", "reason_code": "session_id_missing"}

    state_db = Path(state_db_path) if state_db_path else _home_hermes_state_db()
    if not state_db.exists():
        return {
            "status": "typed_unavailable",
            "reason_code": "state_db_not_found",
            "state_db_path": str(state_db),
        }

    try:
        con = _connect_readonly(state_db)
    except sqlite3.Error as exc:
        return {
            "status": "typed_unavailable",
            "reason_code": f"state_db_open_failed:{exc.__class__.__name__}",
            "state_db_path": str(state_db),
        }

    try:
        session_row = con.execute(
            "select id, source, model, title, started_at, ended_at, message_count from sessions where id=?",
            (session_id,),
        ).fetchone()
        rows = con.execute(
            """
            select id, role, content, timestamp, token_count, finish_reason
            from messages
            where session_id=?
            order by id asc
            """,
            (session_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        return {
            "status": "typed_unavailable",
            "reason_code": f"state_db_query_failed:{exc.__class__.__name__}",
            "state_db_path": str(state_db),
        }
    finally:
        con.close()

    if not rows:
        return {
            "status": "typed_unavailable",
            "reason_code": "session_messages_missing",
            "provider_session_id": session_id,
        }

    messages: list[dict[str, Any]] = []
    for row_id, role, content, timestamp, token_count, finish_reason in rows:
        if role not in {"user", "assistant", "tool", "system"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        message: dict[str, Any] = {
            "role": role,
            "content": content,
            "created_at": timestamp,
            "source_surface": "hermes_state_db",
            "state_db_message_id": row_id,
        }
        if isinstance(token_count, int):
            message["token_count"] = token_count
        if isinstance(finish_reason, str) and finish_reason:
            message["finish_reason"] = finish_reason
        messages.append(message)

    if not messages:
        return {
            "status": "typed_unavailable",
            "reason_code": "session_text_messages_missing",
            "provider_session_id": session_id,
        }

    return {
        "status": "ready",
        "schema_version": SCHEMA_VERSION,
        "provider_id": "hermes",
        "provider_profile": "openyggdrasil-provider",
        "provider_session_id": session_id,
        "session_row": {
            "id": session_row[0] if session_row else session_id,
            "source": session_row[1] if session_row else None,
            "model": session_row[2] if session_row else None,
            "title": session_row[3] if session_row else None,
            "started_at": session_row[4] if session_row else None,
            "ended_at": session_row[5] if session_row else None,
            "message_count": session_row[6] if session_row else None,
        },
        "messages": messages,
        "message_count": len(messages),
        "state_db_path": str(state_db),
        "hard_nonclaims": [
            "state_db_materialization_is_a_local_source_cache_not_provider_answer",
            "postman_does_not_judge_materialized_messages",
            "source_ref_still_requires_anchor_hash_verification",
        ],
    }


def materialize_hermes_state_db_session_json(
    *,
    session_id: str,
    output_dir: str | Path,
    state_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Write a local session_<id>.json cache from Hermes state.db if available."""

    loaded = load_hermes_state_db_session(session_id=session_id, state_db_path=state_db_path)
    if loaded.get("status") != "ready":
        return loaded

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    session_path = output / f"session_{session_id}.json"
    payload = {
        "schema_version": "hermes_session_json.v1",
        "provider_id": loaded["provider_id"],
        "provider_profile": loaded["provider_profile"],
        "provider_session_id": loaded["provider_session_id"],
        "messages": loaded["messages"],
        "source_materialization": {
            "schema_version": SCHEMA_VERSION,
            "source_surface": "hermes_state_db",
            "state_db_path": loaded["state_db_path"],
            "message_count": loaded["message_count"],
            "hard_nonclaims": loaded["hard_nonclaims"],
        },
    }

    existing = _read_json(session_path)
    if existing.get("messages") == payload["messages"]:
        action = "unchanged"
    else:
        session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        action = "written"

    return {
        "status": "ready",
        "schema_version": SCHEMA_VERSION,
        "action": action,
        "provider_session_id": session_id,
        "session_path": str(session_path),
        "message_count": loaded["message_count"],
        "source_surface": "hermes_state_db",
        "hard_nonclaims": loaded["hard_nonclaims"],
    }


def materialize_latest_hermes_state_db_session_json(
    *,
    output_dir: str | Path,
    state_db_path: str | Path | None = None,
) -> dict[str, Any]:
    state_db = Path(state_db_path) if state_db_path else _home_hermes_state_db()
    if not state_db.exists():
        return {"status": "typed_unavailable", "reason_code": "state_db_not_found", "state_db_path": str(state_db)}
    try:
        con = _connect_readonly(state_db)
        row = con.execute(
            """
            select session_id, max(timestamp) as latest_timestamp
            from messages
            where role in ('user', 'assistant')
            group by session_id
            order by latest_timestamp desc
            limit 1
            """
        ).fetchone()
    except sqlite3.Error as exc:
        return {
            "status": "typed_unavailable",
            "reason_code": f"state_db_latest_session_failed:{exc.__class__.__name__}",
            "state_db_path": str(state_db),
        }
    finally:
        try:
            con.close()
        except UnboundLocalError:
            pass
    if not row or not row[0]:
        return {"status": "typed_unavailable", "reason_code": "state_db_latest_session_missing"}
    return materialize_hermes_state_db_session_json(
        session_id=str(row[0]),
        output_dir=output_dir,
        state_db_path=state_db,
    )


__all__ = [
    "SCHEMA_VERSION",
    "load_hermes_state_db_session",
    "materialize_hermes_state_db_session_json",
    "materialize_latest_hermes_state_db_session_json",
]
