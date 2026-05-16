from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from runtime.capture.hermes_state_db_source import materialize_hermes_state_db_session_json
from runtime.source_ref.hermes_session_json import _canonical_anchor_hash, resolve_hermes_session_json_source_ref


def _make_state_db(path: Path, *, session_id: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            create table sessions (
                id text, source text, user_id text, model text, model_config text,
                system_prompt text, parent_session_id text, started_at real, ended_at real,
                end_reason text, message_count integer, tool_call_count integer,
                input_tokens integer, output_tokens integer, cache_read_tokens integer,
                cache_write_tokens integer, reasoning_tokens integer, billing_provider text,
                billing_base_url text, billing_mode text, estimated_cost_usd real,
                actual_cost_usd real, cost_status text, cost_source text,
                pricing_version text, title text, api_call_count integer,
                handoff_state text, handoff_platform text, handoff_error text
            )
            """
        )
        con.execute(
            """
            create table messages (
                id integer primary key autoincrement, session_id text, role text,
                content text, tool_call_id text, tool_calls text, tool_name text,
                timestamp real, token_count integer, finish_reason text,
                reasoning text, reasoning_details text, codex_reasoning_items text,
                reasoning_content text, codex_message_items text
            )
            """
        )
        con.execute(
            "insert into sessions (id, source, model, started_at, message_count, title) values (?, ?, ?, ?, ?, ?)",
            (session_id, "cli", "gpt-test", 1.0, 2, "smoke"),
        )
        con.execute(
            """
            insert into messages (session_id, role, content, timestamp, token_count)
            values (?, ?, ?, ?, ?)
            """,
            (session_id, "user", "agents 기준이 헷갈린다.", 2.0, 7),
        )
        con.execute(
            """
            insert into messages (session_id, role, content, timestamp, token_count)
            values (?, ?, ?, ?, ?)
            """,
            (session_id, "assistant", "실행 모델과 정의 위치를 분리해서 보세요.", 3.0, 9),
        )
        con.commit()
    finally:
        con.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ygg-state-db-source-smoke-") as raw:
        root = Path(raw)
        state_db = root / "state.db"
        output_dir = root / "source-cache"
        session_id = "state-db-smoke"
        _make_state_db(state_db, session_id=session_id)

        materialized = materialize_hermes_state_db_session_json(
            session_id=session_id,
            output_dir=output_dir,
            state_db_path=state_db,
        )
        if materialized.get("status") != "ready":
            raise AssertionError(materialized)
        session_path = Path(str(materialized["session_path"]))
        if not session_path.exists():
            raise AssertionError("session cache was not written")

        messages = [
            {
                "role": "user",
                "content": "agents 기준이 헷갈린다.",
                "created_at": 2.0,
                "source_surface": "hermes_state_db",
                "state_db_message_id": 1,
                "token_count": 7,
            },
            {
                "role": "assistant",
                "content": "실행 모델과 정의 위치를 분리해서 보세요.",
                "created_at": 3.0,
                "source_surface": "hermes_state_db",
                "state_db_message_id": 2,
                "token_count": 9,
            },
        ]
        anchor_hash = _canonical_anchor_hash(messages)
        resolved = resolve_hermes_session_json_source_ref(
            source_ref=f"hermes-session-json://{session_id}",
            message_index_range={"start": 0, "end": 1},
            sessions_dir=output_dir,
            anchor_hash=anchor_hash,
        )
        if resolved.get("status") != "resolved":
            raise AssertionError(resolved)
        if resolved.get("redaction_status") != "pointer_only":
            raise AssertionError("resolver did not preserve pointer-only status")
        print("hermes_state_db_source_smoke=pass")


if __name__ == "__main__":
    main()
