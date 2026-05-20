from __future__ import annotations

import json

from runtime.capture.context_guard import build_context_guard_mementos, write_context_guard_result


def _episode() -> dict:
    return {
        "episode_id": "episode-dog-walk-stress",
        "source_ref": "hermes-session-json://20260520-dog-walk-stress",
        "topic_key": "biology/animal-ecology/domestic-dogs",
        "message_index_range": {"start": 10, "end": 18},
        "anchor_hash": "abc123",
        "signals": {
            "connected_turns": 5,
            "reusable_distinctions": 3,
            "durable_decisions": 1,
            "still_evolving": False,
            "losing_this_hurts_later": True,
        },
    }


def test_context_guard_records_actual_preflight_event_without_false_nonclaim() -> None:
    result = build_context_guard_mementos(
        run_id="test-actual-preflight",
        episodes=[_episode()],
        context_pressure={
            "threshold_reached": True,
            "threshold": 136000,
            "compaction_event": {
                "observed": True,
                "lane": "MF1",
                "marker": "Preflight compression: ~138,358 tokens >= 136,000 threshold.",
                "token_estimate": 138358,
                "threshold": 136000,
            },
        },
    )

    assert result["status"] == "pass"
    assert result["actual_compaction_event"]["proven"] is True
    assert "context_guard_slice_is_not_actual_compaction_event" not in result["hard_nonclaims"]
    assert result["precompact_memento_or_source_ref"] is True
    assert result["no_provider_long_summary"] is True


def test_context_guard_keeps_nonclaim_when_preflight_event_missing() -> None:
    result = build_context_guard_mementos(
        run_id="test-pointer-only",
        episodes=[_episode()],
        context_pressure={"threshold_reached": True, "threshold": 136000},
    )

    assert result["status"] == "pass"
    assert result["actual_compaction_event"]["proven"] is False
    assert "context_guard_slice_is_not_actual_compaction_event" in result["hard_nonclaims"]


def test_context_guard_receipt_carries_actual_event(tmp_path) -> None:
    result = build_context_guard_mementos(
        run_id="test-write-actual-preflight",
        episodes=[_episode()],
        context_pressure={
            "threshold_reached": True,
            "threshold": 136000,
            "compaction_event": {
                "observed": True,
                "lane": "MF1",
                "marker": "Preflight compression: ~138,358 tokens >= 136,000 threshold.",
                "token_estimate": 138358,
                "threshold": 136000,
            },
        },
    )

    written = write_context_guard_result(vault_root=tmp_path, result=result)
    receipt = written["receipt"]
    assert receipt["actual_compaction_event_proven"] is True
    assert receipt["actual_compaction_event"]["lane"] == "MF1"

    receipt_rows = (tmp_path / "_meta" / "context_guard_receipts.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(receipt_rows[-1])["actual_compaction_event_proven"] is True
