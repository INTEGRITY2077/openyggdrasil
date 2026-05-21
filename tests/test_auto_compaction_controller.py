from __future__ import annotations

import json
from pathlib import Path

from runtime.capture.auto_compaction_controller import (
    load_compaction_candidate_episodes,
    parse_preflight_compression,
    run_auto_compaction_controller_from_vault,
)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ledger_row() -> dict:
    return {
        "schema_version": "boundary_ledger_entry.v1",
        "run_id": "unit-ledger",
        "episode_id": "episode-dog-walk-stress",
        "topic_key": "biology/animal-ecology/domestic-dogs",
        "source_ref": "hermes-session-json://20260520-dog-walk-stress",
        "message_index_range": {"start": 10, "end": 18},
        "anchor_hash": "abc123",
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


def test_parse_preflight_compression_accepts_native_emoji_and_unicode_threshold() -> None:
    result = parse_preflight_compression(
        "📦 Preflight compression: ~142,570 tokens ≥ 136,000 threshold. This may take a moment."
    )

    assert result["threshold_reached"] is True
    assert result["observed_tokens"] == 142570
    assert result["threshold_tokens"] == 136000
    assert result["raw_marker_included"] is False
    assert result["compaction_event"]["marker"] == "Preflight compression"


def test_parse_preflight_compression_accepts_compact_numeric_shape() -> None:
    result = parse_preflight_compression("Preflight compression: 142570 >= 136000 threshold")

    assert result["threshold_reached"] is True
    assert result["observed_tokens"] == 142570
    assert result["threshold_tokens"] == 136000
    assert result["raw_marker_included"] is False


def test_auto_compaction_from_vault_requires_ledger_backed_episode(tmp_path: Path) -> None:
    result = run_auto_compaction_controller_from_vault(
        vault_root=tmp_path,
        run_id="unit-no-ledger",
        preflight_text="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
    )

    assert result["status"] == "typed_unavailable_no_ledger_candidates"
    assert result["episode_count"] == 0
    assert not (tmp_path / "_meta" / "precompact_memento.jsonl").exists()


def test_auto_compaction_from_vault_writes_pointer_memento_from_boundary_ledger(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "_meta" / "pending_episode_ledger.jsonl", _ledger_row())

    candidates = load_compaction_candidate_episodes(vault_root=tmp_path)
    assert len(candidates) == 1
    assert candidates[0]["source_ref"] == "hermes-session-json://20260520-dog-walk-stress"

    result = run_auto_compaction_controller_from_vault(
        vault_root=tmp_path,
        run_id="unit-ledger-compaction",
        preflight_text="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
    )

    assert result["status"] == "pass"
    assert result["episode_count"] == 1
    assert result["actual_compaction_event"]["proven"] is True
    assert result["receipt"]["actual_compaction_event_proven"] is True
    assert result["written_memento_ids"]
    memento_rows = (tmp_path / "_meta" / "precompact_memento.jsonl").read_text(encoding="utf-8").splitlines()
    memento = json.loads(memento_rows[-1])
    assert memento["summary_policy"] == "pointer_only_no_raw_transcript"
    assert memento["raw_transcript_included"] is False
    assert memento["source_ref"] == "hermes-session-json://20260520-dog-walk-stress"


def test_auto_compaction_from_vault_is_idempotent_by_run_id(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "_meta" / "pending_episode_ledger.jsonl", _ledger_row())

    first = run_auto_compaction_controller_from_vault(
        vault_root=tmp_path,
        run_id="unit-idempotent-compaction",
        preflight_text="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
    )
    second = run_auto_compaction_controller_from_vault(
        vault_root=tmp_path,
        run_id="unit-idempotent-compaction",
        preflight_text="Preflight compression: ~142,570 tokens >= 136,000 threshold.",
    )

    assert first["status"] == "pass"
    assert second["status"] == "already_recorded"
    assert len((tmp_path / "_meta" / "precompact_memento.jsonl").read_text(encoding="utf-8").splitlines()) == 1
