from __future__ import annotations

import subprocess
from pathlib import Path

from runtime.cli.ygg_compaction import run_compaction_check, run_compaction_watch


def _append_ledger(vault: Path) -> None:
    row = (
        '{"schema_version":"boundary_ledger_entry.v1",'
        '"episode_id":"episode-compact-cli",'
        '"topic_key":"software-development/claude-code/extension-placement",'
        '"source_ref":"hermes-session-json://compact-cli",'
        '"message_index_range":{"start":1,"end":4},'
        '"anchor_hash":"abc123",'
        '"state":"closed",'
        '"signals":{"connected_turns":4,"reusable_distinctions":2,'
        '"durable_decisions":1,"still_evolving":false,'
        '"losing_this_hurts_later":true,"weak_or_chitchat":false}}'
    )
    path = vault / "_meta" / "pending_episode_ledger.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(row + "\n", encoding="utf-8")


def test_compact_check_stays_blocked_without_preflight_marker(tmp_path: Path) -> None:
    _append_ledger(tmp_path)
    result = run_compaction_check(
        vault_root=tmp_path,
        run_id="unit-no-preflight",
        targets={"provider": "ygg-pro1:1"},
        runner=lambda command: subprocess.CompletedProcess(
            command,
            0,
            stdout="gpt-5.5 | 72.7K/272K | no compaction marker",
            stderr="",
        ),
    )

    assert result["production_ready_axis_pass"] is False
    assert "live_panes_no_preflight_marker" in result["compact_memento_blockers"]
    assert not (tmp_path / "_meta" / "precompact_memento.jsonl").exists()
    assert result["cli"]["raw_pane_text_included"] is False


def test_compact_check_writes_pointer_memento_after_real_preflight_marker(tmp_path: Path) -> None:
    _append_ledger(tmp_path)
    result = run_compaction_check(
        vault_root=tmp_path,
        run_id="unit-with-preflight",
        targets={"provider": "ygg-pro1:1"},
        runner=lambda command: subprocess.CompletedProcess(
            command,
            0,
            stdout="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
            stderr="",
        ),
    )

    assert result["production_ready_axis_pass"] is True
    assert result["compaction_continuity_conditions"]["context_guard_memento_write_proven"] is True
    assert result["cli"]["candidate_episode_count"] == 1
    memento_path = tmp_path / "_meta" / "precompact_memento.jsonl"
    assert memento_path.exists()
    text = memento_path.read_text(encoding="utf-8")
    assert "hermes-session-json://compact-cli" in text
    assert "raw_transcript" in text


def test_compact_watch_waits_until_real_marker_then_writes_memento(tmp_path: Path) -> None:
    _append_ledger(tmp_path)
    calls = {"count": 0}

    def runner(command):
        calls["count"] += 1
        if calls["count"] < 3:
            stdout = "gpt-5.5 | 80K/272K | no compaction marker"
        else:
            stdout = "Preflight compression: ~142,570 tokens >= 136,000 threshold."
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    result = run_compaction_watch(
        vault_root=tmp_path,
        run_id="unit-watch-preflight",
        targets={"provider": "ygg-pro1:1"},
        interval_seconds=0,
        max_attempts=5,
        runner=runner,
    )

    assert result["production_ready_axis_pass"] is True
    assert result["watch"]["attempts"] == 3
    assert result["watch"]["completed_reason"] == "pass"
    assert (tmp_path / "_meta" / "precompact_memento.jsonl").exists()


def test_compact_watch_keeps_blocked_when_marker_never_appears(tmp_path: Path) -> None:
    _append_ledger(tmp_path)
    result = run_compaction_watch(
        vault_root=tmp_path,
        run_id="unit-watch-no-marker",
        targets={"provider": "ygg-pro1:1"},
        interval_seconds=0,
        max_attempts=2,
        runner=lambda command: subprocess.CompletedProcess(
            command,
            0,
            stdout="gpt-5.5 | 90K/272K | no compaction marker",
            stderr="",
        ),
    )

    assert result["production_ready_axis_pass"] is False
    assert result["watch"]["attempts"] == 2
    assert result["watch"]["completed_reason"] == "max_attempts_reached"
    assert not (tmp_path / "_meta" / "precompact_memento.jsonl").exists()
