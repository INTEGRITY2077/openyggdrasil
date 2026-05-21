from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ledger_row() -> dict:
    return {
        "schema_version": "boundary_ledger_entry.v1",
        "run_id": "unit-worker-loop-ledger",
        "episode_id": "episode-agent-placement-boundary",
        "topic_key": "software-development/claude-code/extension-placement/agents",
        "source_ref": "hermes-session-json://20260521-agent-placement-boundary",
        "message_index_range": {"start": 69, "end": 71},
        "anchor_hash": "f6dbe0a386dc12797a4636152c34f172c65769b6a523cd3a0b41b605000909b2",
        "state": "closed",
        "reason_code": "mature_episode",
        "signals": {
            "connected_turns": 5,
            "reusable_distinctions": 3,
            "durable_decisions": 1,
            "still_evolving": False,
            "losing_this_hurts_later": True,
            "weak_or_chitchat": False,
        },
    }


def test_worker_owned_loop_preflight_marker_writes_pointer_memento(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mailbox = tmp_path / "mailbox"
    vault = tmp_path / "vault"
    mailbox.mkdir()
    vault.mkdir()
    _append_jsonl(vault / "_meta" / "pending_episode_ledger.jsonl", _ledger_row())

    monkeypatch.setattr(
        sys,
        "argv",
        ["ygg_poll.py", "produce", str(mailbox), str(vault)],
    )
    monkeypatch.setenv("OY_ALLOW_PUBLIC_RUNTIME_VAULT", "1")
    import runtime.polling.worker_owned_loop as worker_owned_loop

    worker_owned_loop = importlib.reload(worker_owned_loop)
    monkeypatch.setattr(worker_owned_loop, "resolve_vault_root", lambda: vault)

    worker_owned_loop._maybe_record_preflight_compaction(
        "Preflight compression: ~142,570 tokens >= 136,000 threshold."
    )

    memento_path = vault / "_meta" / "precompact_memento.jsonl"
    receipt_path = vault / "_meta" / "context_guard_receipts.jsonl"
    loop_log_path = mailbox / "live_worker_owned_loop_log.jsonl"

    assert memento_path.exists()
    memento = json.loads(memento_path.read_text(encoding="utf-8").splitlines()[-1])
    assert memento["source_ref"] == "hermes-session-json://20260521-agent-placement-boundary"
    assert memento["summary_policy"] == "pointer_only_no_raw_transcript"
    assert memento["raw_transcript_included"] is False

    receipt = json.loads(receipt_path.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["actual_compaction_event_proven"] is True

    loop_log = json.loads(loop_log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert loop_log["phase"] == "precompact_memento_observer"
    assert loop_log["actual_compaction_event_proven"] is True
    assert loop_log["raw_pane_text_included"] is False
