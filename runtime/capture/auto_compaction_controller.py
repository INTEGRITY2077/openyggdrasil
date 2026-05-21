from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.capture.context_guard import build_context_guard_mementos, write_context_guard_result


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


__all__ = ["parse_preflight_compression", "run_auto_compaction_controller"]
