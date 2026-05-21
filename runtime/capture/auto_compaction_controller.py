from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.capture.context_guard import build_context_guard_mementos, write_context_guard_result
from runtime.common.jsonl_io import read_jsonl


BOUNDARY_LEDGER_RELATIVE_PATH = "_meta/pending_episode_ledger.jsonl"
CONTEXT_GUARD_RECEIPTS_RELATIVE_PATH = "_meta/context_guard_receipts.jsonl"
COMPACTION_EPISODE_STATES = {"open", "cooling", "bridge", "chunked_continue", "closed"}


PREFLIGHT_COMPRESSION_RE = re.compile(
    r"Preflight compression:\s*~?(?P<observed>[\d,]+)\s+tokens\s*>=\s*(?P<threshold>[\d,]+)\s+threshold",
    re.IGNORECASE,
)


def _to_int(value: str) -> int:
    return int(value.replace(",", "").strip())


def parse_preflight_compression(text: str) -> dict[str, Any]:
    """Parse Hermes preflight compression text without storing raw pane text."""

    match = PREFLIGHT_COMPRESSION_RE.search(str(text or ""))
    if not match:
        return {
            "schema_version": "context_pressure_observation.v1",
            "threshold_reached": False,
            "observed_tokens": 0,
            "threshold_tokens": 0,
            "raw_marker_included": False,
            "reason": "preflight_compression_marker_not_found",
        }
    observed_tokens = _to_int(match.group("observed"))
    threshold_tokens = _to_int(match.group("threshold"))
    return {
        "schema_version": "context_pressure_observation.v1",
        "threshold_reached": observed_tokens >= threshold_tokens,
        "observed_tokens": observed_tokens,
        "threshold_tokens": threshold_tokens,
        "raw_marker_included": False,
        "compaction_event": {
            "observed": True,
            "lane": "provider",
            "marker": "Preflight compression",
            "token_estimate": observed_tokens,
            "threshold": threshold_tokens,
            "summary_failed": False,
            "fallback_context_marker_inserted": False,
        },
        "hard_nonclaims": [
            "preflight_marker_parse_is_not_provider_memory_claim",
            "raw_preflight_text_not_stored",
        ],
    }


def _receipt_run_id_exists(vault_root: Path, run_id: str) -> bool:
    path = vault_root / CONTEXT_GUARD_RECEIPTS_RELATIVE_PATH
    if not path.exists():
        return False
    for row in read_jsonl(path):
        if isinstance(row, Mapping) and str(row.get("run_id") or "") == run_id:
            return True
    return False


def load_compaction_candidate_episodes(
    *,
    vault_root: Path,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Load pointer-safe candidate episodes from the boundary ledger.

    The context guard must not invent summaries during native compaction. It can
    only use ledger rows that already preserve source_ref, range, hash, topic,
    and maturity signals.
    """

    path = vault_root / BOUNDARY_LEDGER_RELATIVE_PATH
    latest_by_episode: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if not isinstance(row, Mapping):
            continue
        state = str(row.get("state") or "")
        if state not in COMPACTION_EPISODE_STATES:
            continue
        episode_id = str(row.get("episode_id") or "").strip()
        topic_key = str(row.get("topic_key") or "").strip()
        source_ref = str(row.get("source_ref") or "").strip()
        anchor_hash = str(row.get("anchor_hash") or "").strip()
        message_range = row.get("message_index_range")
        if not episode_id or not topic_key or not source_ref or not anchor_hash or not isinstance(message_range, Mapping):
            continue
        latest_by_episode[episode_id] = {
            "episode_id": episode_id,
            "source_ref": source_ref,
            "topic_key": topic_key,
            "message_index_range": dict(message_range),
            "anchor_hash": anchor_hash,
            "signals": dict(row.get("signals") or {}),
            "boundary_state": state,
            "boundary_reason_code": row.get("reason_code"),
        }
    return list(latest_by_episode.values())[-max(1, limit):]


def run_auto_compaction_controller(
    *,
    vault_root: Path,
    run_id: str,
    preflight_text: str,
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Convert an observed preflight compression marker into pointer mementos."""

    pressure = parse_preflight_compression(preflight_text)
    result = build_context_guard_mementos(
        run_id=run_id,
        episodes=episodes,
        context_pressure={
            "schema_version": pressure["schema_version"],
            "threshold_reached": pressure["threshold_reached"],
            "threshold": pressure["threshold_tokens"],
            "observed_token_estimate": pressure["observed_tokens"],
            "compaction_event": pressure.get("compaction_event"),
            "hard_nonclaims": pressure.get("hard_nonclaims", []),
        },
    )
    if pressure["threshold_reached"]:
        written = write_context_guard_result(vault_root=vault_root, result=result)
    else:
        written = {"receipt": None, "mementos": []}
    result["written"] = written
    result["receipt"] = written["receipt"]
    written_memento_ids = [
        str(memento.get("memento_id"))
        for memento in written.get("mementos", [])
        if isinstance(memento, Mapping) and memento.get("memento_id")
    ]
    result["written_memento_ids"] = written_memento_ids
    if isinstance(result["receipt"], dict):
        result["receipt"]["written_memento_ids"] = written_memento_ids
    result["preflight_parse"] = pressure
    return result


def run_auto_compaction_controller_from_vault(
    *,
    vault_root: Path,
    run_id: str,
    preflight_text: str,
    max_episodes: int = 20,
) -> dict[str, Any]:
    """Run compaction handling from live vault ledger state.

    This is the runtime bridge used when a live pane shows a native preflight
    compression marker. It never fabricates an episode; without ledger-backed
    candidates it records a blocked/skip result.
    """

    vault_root = vault_root.resolve()
    pressure = parse_preflight_compression(preflight_text)
    episodes = load_compaction_candidate_episodes(vault_root=vault_root, limit=max_episodes)
    if _receipt_run_id_exists(vault_root, run_id):
        return {
            "schema_version": "auto_compaction_controller_result.v1",
            "run_id": run_id,
            "status": "already_recorded",
            "preflight_parse": pressure,
            "episode_count": len(episodes),
            "written": {"receipt": None, "mementos": []},
            "hard_nonclaims": [
                "already_recorded_result_is_not_new_compaction_proof",
            ],
        }
    if not pressure.get("threshold_reached"):
        return {
            "schema_version": "auto_compaction_controller_result.v1",
            "run_id": run_id,
            "status": "blocked",
            "preflight_parse": pressure,
            "episode_count": len(episodes),
            "written": {"receipt": None, "mementos": []},
            "hard_nonclaims": [
                "below_threshold_preflight_marker_does_not_write_mementos",
            ],
        }
    if not episodes:
        return {
            "schema_version": "auto_compaction_controller_result.v1",
            "run_id": run_id,
            "status": "typed_unavailable_no_ledger_candidates",
            "preflight_parse": pressure,
            "episode_count": 0,
            "written": {"receipt": None, "mementos": []},
            "hard_nonclaims": [
                "compaction_memento_requires_ledger_backed_source_ref",
                "provider_long_summary_must_not_be_fabricated",
            ],
        }
    result = run_auto_compaction_controller(
        vault_root=vault_root,
        run_id=run_id,
        preflight_text=preflight_text,
        episodes=episodes,
    )
    result["schema_version"] = "auto_compaction_controller_result.v1"
    result["episode_count"] = len(episodes)
    result["episode_source"] = BOUNDARY_LEDGER_RELATIVE_PATH
    return result


__all__ = [
    "load_compaction_candidate_episodes",
    "parse_preflight_compression",
    "run_auto_compaction_controller",
    "run_auto_compaction_controller_from_vault",
]
