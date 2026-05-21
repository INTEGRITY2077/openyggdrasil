from __future__ import annotations

import subprocess
from pathlib import Path

from runtime.capture.live_compaction_observer import (
    _default_runner,
    observe_compaction_text,
    observe_tmux_targets,
    parse_token_meter,
    run_live_compaction_observer,
)
import runtime.capture.live_compaction_observer as live_compaction_observer


def _episode() -> dict:
    return {
        "episode_id": "episode-claude-code-extension-placement",
        "source_ref": "hermes-session-json://20260521_100525_3dd9d9",
        "topic_key": "software-development/claude-code/extension-placement/agents",
        "message_index_range": {"start": 69, "end": 71},
        "anchor_hash": "f6dbe0a386dc12797a4636152c34f172c65769b6a523cd3a0b41b605000909b2",
        "signals": {
            "connected_turns": 5,
            "reusable_distinctions": 3,
            "durable_decisions": 1,
            "still_evolving": False,
            "losing_this_hurts_later": True,
            "weak_or_chitchat": False,
        },
    }


def _append_ledger(vault: Path) -> None:
    row = {**_episode(), "schema_version": "boundary_ledger_entry.v1", "state": "closed"}
    path = vault / "_meta" / "pending_episode_ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def test_parse_token_meter_is_not_compaction_proof() -> None:
    row = observe_compaction_text("⚕ gpt-5.5 │ 72.7K/272K │", lane="provider")

    assert row["token_meter"]["used_tokens"] == 72700
    assert row["token_meter"]["source_label"] == "72.7K/272K"
    assert row["threshold_reached"] is False
    assert row["preflight_marker_found"] is False
    assert row["raw_pane_text_included"] is False


def test_preflight_marker_runs_pointer_memento(tmp_path: Path) -> None:
    _append_ledger(tmp_path)
    result = run_live_compaction_observer(
        vault_root=tmp_path,
        run_id="unit-live-observer",
        targets={"mf1": "ygg-mf1:1"},
        episodes=[_episode()],
        runner=lambda command: subprocess.CompletedProcess(
            command,
            0,
            stdout="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
            stderr="",
        ),
    )

    assert result["production_ready_axis_pass"] is True
    assert result["compaction_continuity_conditions"]["pane_memento_marker_found"] is False
    assert result["compaction_continuity_conditions"]["context_guard_memento_write_proven"] is True
    assert result["compaction_continuity_conditions"]["memento_sot"] == "vault_context_guard_receipt"
    assert "live_panes_no_memento_marker" not in result["compact_memento_blockers"]
    assert result["context_guard_result"]["receipt"]["actual_compaction_event_proven"] is True
    assert result["context_guard_result"]["written_memento_ids"]


def test_preflight_marker_is_idempotent_by_native_event(tmp_path: Path) -> None:
    _append_ledger(tmp_path)

    def runner(command):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
            stderr="",
        )

    first = run_live_compaction_observer(
        vault_root=tmp_path,
        run_id="unit-live-observer-first",
        targets={"mf1": "ygg-mf1:1"},
        episodes=[_episode()],
        runner=runner,
    )
    second = run_live_compaction_observer(
        vault_root=tmp_path,
        run_id="unit-live-observer-second",
        targets={"mf1": "ygg-mf1:1"},
        episodes=[_episode()],
        runner=runner,
    )

    assert first["production_ready_axis_pass"] is True
    assert second["production_ready_axis_pass"] is True
    assert second["context_guard_result"]["status"] == "already_recorded_event"
    assert second["compaction_continuity_conditions"]["already_recorded_event"] is True
    assert len((tmp_path / "_meta" / "precompact_memento.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_tmux_observer_keeps_missing_marker_blocked() -> None:
    result = observe_tmux_targets(
        {"provider": "ygg-pro1:1"},
        runner=lambda command: subprocess.CompletedProcess(
            command,
            0,
            stdout="⚕ gpt-5.5 │ 72.7K/272K │ no compaction marker here",
            stderr="",
        ),
    )

    assert result["status"] == "blocked"
    assert "live_panes_below_preflight_threshold" in result["blockers"]
    assert "live_panes_no_preflight_marker" in result["blockers"]


def test_parse_token_meter_supports_integer_shape() -> None:
    row = parse_token_meter("tokens 142570/272000")

    assert row["found"] is True
    assert row["used_tokens"] == 142570
    assert row["source_label"] == "142570/272000"
    assert row["raw_text_included"] is False


def test_default_runner_uses_wsl_tmux_fallback_on_windows(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(live_compaction_observer.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        live_compaction_observer.shutil,
        "which",
        lambda name: "C:\\Windows\\System32\\wsl.exe" if name == "wsl" else None,
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        if command and command[0] == "tmux":
            raise FileNotFoundError("tmux")
        assert command[:3] == ["wsl", "bash", "-lc"]
        assert "tmux capture-pane" in command[3]
        return subprocess.CompletedProcess(command, 0, stdout=b"gpt-5.5 | 72.7K/272K", stderr=b"")

    monkeypatch.setattr(live_compaction_observer.subprocess, "run", fake_run)

    result = _default_runner(["tmux", "capture-pane", "-p", "-t", "ygg-pro1:1"])

    assert result.returncode == 0
    assert result.stdout == "gpt-5.5 | 72.7K/272K"
    assert calls[0][0] == "tmux"
    assert calls[1][:3] == ["wsl", "bash", "-lc"]
