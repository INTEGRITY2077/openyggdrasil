from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.common.jsonl_io import append_jsonl_atomic


CONTEXT_GUARD_RECEIPTS_RELATIVE_PATH = "_meta/context_guard_receipts.jsonl"
PRECOMPACT_MEMENTO_RELATIVE_PATH = "_meta/precompact_memento.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _require_pointer(episode: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = str(episode.get("source_ref") or "").strip()
    topic_key = str(episode.get("topic_key") or "").strip()
    anchor_hash = str(episode.get("anchor_hash") or "").strip()
    message_range = episode.get("message_index_range")
    if not source_ref:
        raise ValueError("source_ref is required")
    if not topic_key:
        raise ValueError("topic_key is required")
    if not anchor_hash:
        raise ValueError("anchor_hash is required")
    if not isinstance(message_range, Mapping):
        raise ValueError("message_index_range is required")
    return {
        "source_ref": source_ref,
        "topic_key": topic_key,
        "message_index_range": dict(message_range),
        "anchor_hash": anchor_hash,
    }


def _score_episode(episode: Mapping[str, Any]) -> dict[str, Any]:
    signals = dict(episode.get("signals") or {})
    connected_turns = int(signals.get("connected_turns") or 0)
    reusable_distinctions = int(signals.get("reusable_distinctions") or 0)
    durable_decisions = int(signals.get("durable_decisions") or 0)
    still_evolving = bool(signals.get("still_evolving"))
    losing_hurts = bool(signals.get("losing_this_hurts_later"))
    weak = bool(signals.get("weak_or_chitchat"))
    mature = connected_turns >= 3 and reusable_distinctions >= 2 and durable_decisions >= 1
    important_ambiguous = losing_hurts and (still_evolving or not mature)
    if mature and not still_evolving:
        decision = "commit_candidate"
    elif important_ambiguous:
        decision = "precompact_memento"
    elif weak:
        decision = "archive_or_reject"
    else:
        decision = "precompact_memento"
    return {
        "decision": decision,
        "connected_turns": connected_turns,
        "reusable_distinctions": reusable_distinctions,
        "durable_decisions": durable_decisions,
        "still_evolving": still_evolving,
        "losing_this_hurts_later": losing_hurts,
        "weak_or_chitchat": weak,
    }


def _actual_compaction_event(context_pressure: Mapping[str, Any]) -> dict[str, Any]:
    event = context_pressure.get("compaction_event")
    if not isinstance(event, Mapping):
        return {"proven": False, "reason": "missing_compaction_event"}
    marker = str(event.get("marker") or "")
    token_estimate = int(event.get("token_estimate") or 0)
    threshold = int(event.get("threshold") or context_pressure.get("threshold") or 0)
    observed = bool(event.get("observed"))
    lane = str(event.get("lane") or "").strip()
    proven = observed and "Preflight compression" in marker and threshold > 0 and token_estimate >= threshold
    event_basis = json.dumps(
        {
            "lane": lane,
            "marker": marker,
            "token_estimate": token_estimate,
            "threshold": threshold,
            "summary_failed": bool(event.get("summary_failed")),
            "fallback_context_marker_inserted": bool(event.get("fallback_context_marker_inserted")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "proven": proven,
        "event_id": f"compaction-event-{_short_hash(event_basis)}",
        "lane": lane,
        "marker": marker,
        "token_estimate": token_estimate,
        "threshold": threshold,
        "summary_failed": bool(event.get("summary_failed")),
        "fallback_context_marker_inserted": bool(event.get("fallback_context_marker_inserted")),
        "reason": "observed_preflight_compression" if proven else "insufficient_compaction_marker",
    }


def build_context_guard_mementos(
    *,
    run_id: str,
    episodes: Sequence[Mapping[str, Any]],
    context_pressure: Mapping[str, Any],
) -> dict[str, Any]:
    pressure = dict(context_pressure)
    threshold_reached = bool(pressure.get("threshold_reached"))
    actual_compaction_event = _actual_compaction_event(pressure)
    compaction_event_id = str(actual_compaction_event.get("event_id") or "")
    decisions: list[dict[str, Any]] = []
    mementos: list[dict[str, Any]] = []
    for episode in episodes:
        pointer = _require_pointer(episode)
        score = _score_episode(episode)
        episode_id = str(episode.get("episode_id") or pointer["topic_key"])
        decision = {
            "episode_id": episode_id,
            **pointer,
            "decision": score["decision"],
            "signals": score,
        }
        decisions.append(decision)
        if score["decision"] in {"commit_candidate", "precompact_memento"}:
            mementos.append(
                {
                    "schema_version": "precompact_memento.v1",
                    "run_id": run_id,
                    "compaction_event_id": compaction_event_id,
                    "memento_id": f"memento-{_short_hash(compaction_event_id + episode_id + pointer['anchor_hash'])}",
                    "episode_id": episode_id,
                    **pointer,
                    "triage_decision": score["decision"],
                    "summary_policy": "pointer_only_no_raw_transcript",
                    "raw_transcript_included": False,
                    "provider_long_summary_required": False,
                    "created_at": _now_iso(),
                    "hard_nonclaims": [
                        "memento_is_pointer_not_memory_claim",
                        "context_guard_does_not_write_wiki_page",
                    ],
                }
            )
    status = "pass" if threshold_reached and decisions and mementos else "partial"
    hard_nonclaims = ["pointer_memento_is_not_provider_self_memory"]
    if not actual_compaction_event["proven"]:
        hard_nonclaims.append("context_guard_slice_is_not_actual_compaction_event")
    if actual_compaction_event.get("summary_failed"):
        hard_nonclaims.append("native_compression_summary_failed_so_pointer_memento_is_the_recovery_surface")
    return {
        "schema_version": "context_guard_result.v1",
        "run_id": run_id,
        "status": status,
        "context_pressure": pressure,
        "actual_compaction_event": actual_compaction_event,
        "decisions": decisions,
        "mementos": mementos,
        "open_episode_triage": bool(decisions),
        "precompact_memento_or_source_ref": bool(mementos),
        "no_provider_long_summary": all(
            not bool(item.get("provider_long_summary_required")) and item.get("raw_transcript_included") is False
            for item in mementos
        ),
        "hard_nonclaims": hard_nonclaims,
    }


def write_context_guard_result(*, vault_root: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    written_mementos = []
    for memento in result.get("mementos") or []:
        if isinstance(memento, Mapping):
            append_jsonl_atomic(vault_root / PRECOMPACT_MEMENTO_RELATIVE_PATH, memento)
            written_mementos.append(dict(memento))
    receipt = {
        "schema_version": "context_guard_receipt.v1",
        "run_id": result.get("run_id"),
        "receipt_id": f"context-guard-{_short_hash(json.dumps(result, ensure_ascii=False, sort_keys=True))}",
        "status": result.get("status"),
        "created_at": _now_iso(),
        "open_episode_triage": result.get("open_episode_triage") is True,
        "precompact_memento_or_source_ref": result.get("precompact_memento_or_source_ref") is True,
        "no_provider_long_summary": result.get("no_provider_long_summary") is True,
        "memento_count": len(written_mementos),
        "actual_compaction_event_proven": bool(
            isinstance(result.get("actual_compaction_event"), Mapping)
            and result["actual_compaction_event"].get("proven") is True
        ),
        "actual_compaction_event": dict(result.get("actual_compaction_event") or {}),
        "compaction_event_id": dict(result.get("actual_compaction_event") or {}).get("event_id"),
        "hard_nonclaims": list(result.get("hard_nonclaims") or []),
    }
    append_jsonl_atomic(vault_root / CONTEXT_GUARD_RECEIPTS_RELATIVE_PATH, receipt)
    return {"receipt": receipt, "mementos": written_mementos}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--episodes-json", required=True, type=Path)
    parser.add_argument("--context-pressure-json", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    episodes = json.loads(args.episodes_json.read_text(encoding="utf-8"))
    pressure = json.loads(args.context_pressure_json.read_text(encoding="utf-8"))
    result = build_context_guard_mementos(
        run_id=args.run_id,
        episodes=episodes,
        context_pressure=pressure,
    )
    if not args.dry_run:
        result["written"] = write_context_guard_result(vault_root=args.vault_root, result=result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
