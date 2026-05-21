from __future__ import annotations

import subprocess

from runtime.cli import ygg_memory_lanes


def test_provider_tmux_lane_downgrades_sync_wait(monkeypatch) -> None:
    monkeypatch.delenv("YGG_PROVIDER_SESSION_ID", raising=False)
    monkeypatch.delenv("OY_PROVIDER_SESSION_ID", raising=False)
    monkeypatch.delenv("YGG_ALLOW_PROVIDER_SYNC_RECALL", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-test/default,1,0")
    monkeypatch.setenv("YGG_TMUX_SESSION_NAME", "ygg-pro1")

    assert ygg_memory_lanes._provider_recall_wait_should_downgrade() is True


def test_memory_lane_tmux_does_not_downgrade_sync_wait(monkeypatch) -> None:
    monkeypatch.delenv("YGG_PROVIDER_SESSION_ID", raising=False)
    monkeypatch.delenv("OY_PROVIDER_SESSION_ID", raising=False)
    monkeypatch.delenv("YGG_ALLOW_PROVIDER_SYNC_RECALL", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-test/default,1,0")
    monkeypatch.setenv("YGG_TMUX_SESSION_NAME", "ygg-mf1")

    assert ygg_memory_lanes._provider_recall_wait_should_downgrade() is False


def test_explicit_provider_sync_recall_override(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-test/default,1,0")
    monkeypatch.setenv("YGG_TMUX_SESSION_NAME", "ygg-pro1")
    monkeypatch.setenv("YGG_ALLOW_PROVIDER_SYNC_RECALL", "1")

    assert ygg_memory_lanes._provider_recall_wait_should_downgrade() is False


def test_tmux_session_name_probe_uses_tmux_when_no_override(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-test/default,1,0")
    monkeypatch.delenv("YGG_TMUX_SESSION_NAME", raising=False)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ygg-pro1\n", stderr="")

    monkeypatch.setattr(ygg_memory_lanes.subprocess, "run", fake_run)

    assert ygg_memory_lanes._current_tmux_session_name() == "ygg-pro1"
    assert ygg_memory_lanes._provider_recall_wait_should_downgrade() is True
