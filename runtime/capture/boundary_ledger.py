from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.common.jsonl_io import append_jsonl_atomic


BOUNDARY_LEDGER_RELATIVE_PATH = "_meta/pending_episode_ledger.jsonl"
BOUNDARY_DECISION_RECEIPTS_RELATIVE_PATH = "_meta/boundary_decision_receipts.jsonl"
VALID_STATES = {"open", "cooling", "bridge", "chunked_continue", "closed", "rejected"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]}"


def _signals(episode: Mapping[str, Any]) -> dict[str, Any]:
    return dict(episode.get("signals") or {})


def decide_boundary_state(episode: Mapping[str, Any]) -> dict[str, Any]:
    signals = _signals(episode)
    connected_turns = int(signals.get("connected_turns") or 0)
    topic_switch_count = int(signals.get("topic_switch_count") or 0)
    return_count = int(signals.get("return_to_topic_count") or 0)
    reusable_distinctions = int(signals.get("reusable_distinctions") or 0)
    durable_decisions = int(signals.get("durable_decisions") or 0)
    source_ref_resolved = bool(signals.get("source_ref_resolved"))
    weak_or_chitchat = bool(signals.get("weak_or_chitchat"))

    if weak_or_chitchat or not source_ref_resolved:
        state = "rejected"
        reason = "weak_or_unresolved_source"
    elif connected_turns >= 12:
        state = "chunked_continue"
        reason = "long_connected_topic"
    elif return_count >= 1 and topic_switch_count >= 1:
        state = "bridge"
        reason = "topic_return_after_switch"
    elif connected_turns >= 3 and reusable_distinctions >= 2 and durable_decisions >= 1:
        state = "closed"
        reason = "mature_episode"
    elif topic_switch_count >= 1:
        state = "cooling"
        reason = "single_topic_switch_not_enough_to_close"
    else:
        state = "open"
        reason = "still_collecting"
    return {
        "state": state,
        "reason_code": reason,
        "signals": {
            "connected_turns": connected_turns,
            "topic_switch_count": topic_switch_count,
            "return_to_topic_count": return_count,
            "reusable_distinctions": reusable_distinctions,
            "durable_decisions": durable_decisions,
            "source_ref_resolved": source_ref_resolved,
            "weak_or_chitchat": weak_or_chitchat,
        },
    }


def build_boundary_ledger_record(*, run_id: str, episode: Mapping[str, Any]) -> dict[str, Any]:
    episode_id = str(episode.get("episode_id") or "").strip()
    topic_key = str(episode.get("topic_key") or "").strip()
    source_ref = str(episode.get("source_ref") or "").strip()
    anchor_hash = str(episode.get("anchor_hash") or "").strip()
    message_range = episode.get("message_index_range")
    if not episode_id:
        episode_id = _id("episode", topic_key + source_ref + anchor_hash)
    if not topic_key:
        raise ValueError("topic_key is required")
    if not source_ref:
        raise ValueError("source_ref is required")
    if not anchor_hash:
        raise ValueError("anchor_hash is required")
    if not isinstance(message_range, Mapping):
        raise ValueError("message_index_range is required")
    decision = decide_boundary_state(episode)
    now = _now_iso()
    return {
        "schema_version": "boundary_ledger_entry.v1",
        "run_id": run_id,
        "episode_id": episode_id,
        "topic_key": topic_key,
        "source_ref": source_ref,
        "message_index_range": dict(message_range),
        "anchor_hash": anchor_hash,
        "state": decision["state"],
        "reason_code": decision["reason_code"],
        "signals": decision["signals"],
        "created_at": now,
        "updated_at": now,
        "is_vault_node": False,
        "is_mf_final_support": False,
        "hard_nonclaims": [
            "pending_ledger_entry_is_not_wiki_node",
            "boundary_state_is_not_provider_memory_claim",
        ],
    }


def write_boundary_ledger_record(*, vault_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    state = str(record.get("state") or "")
    if state not in VALID_STATES:
        raise ValueError(f"invalid boundary state: {state}")
    append_jsonl_atomic(vault_root / BOUNDARY_LEDGER_RELATIVE_PATH, record)
    receipt = {
        "schema_version": "boundary_decision_receipt.v1",
        "run_id": record.get("run_id"),
        "receipt_id": _id("boundary", json.dumps(dict(record), ensure_ascii=False, sort_keys=True)),
        "episode_id": record.get("episode_id"),
        "topic_key": record.get("topic_key"),
        "state": state,
        "source_ref": record.get("source_ref"),
        "anchor_hash": record.get("anchor_hash"),
        "boundary_ledger_state": True,
        "is_vault_node": False,
        "is_mf_final_support": False,
        "created_at": _now_iso(),
        "hard_nonclaims": [
            "boundary_receipt_is_not_full_hysteresis_scenario",
            "pending_ledger_entry_is_not_final_support",
        ],
    }
    append_jsonl_atomic(vault_root / BOUNDARY_DECISION_RECEIPTS_RELATIVE_PATH, receipt)
    return receipt


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--episode-json", required=True, type=Path)
    args = parser.parse_args()
    episode = json.loads(args.episode_json.read_text(encoding="utf-8"))
    record = build_boundary_ledger_record(run_id=args.run_id, episode=episode)
    receipt = write_boundary_ledger_record(vault_root=args.vault_root, record=record)
    print(json.dumps({"record": record, "receipt": receipt}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
