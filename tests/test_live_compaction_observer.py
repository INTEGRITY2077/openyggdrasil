from __future__ import annotations

import subprocess
from pathlib import Path

from runtime.capture.live_compaction_observer import (
    observe_compaction_text,
    observe_tmux_targets,
    parse_token_meter,
    run_live_compaction_observer,
)


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


def test_parse_token_meter_is_not_compaction_proof() -> None:
    row = observe_compaction_text("⚕ gpt-5.5 │ 72.7K/272K │", lane="provider")

    assert row["token_meter"]["used_tokens"] == 72700
    assert row["token_meter"]["source_label"] == "72.7K/272K"
    assert row["threshold_reached"] is False
    assert row["preflight_marker_found"] is False
    assert row["raw_pane_text_included"] is False


def test_preflight_marker_runs_pointer_memento(tmp_path: Path) -> None:
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
