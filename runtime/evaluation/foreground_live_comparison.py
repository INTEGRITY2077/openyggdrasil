from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
FOREGROUND_LIVE_COMPARISON_SCHEMA_PATH = CONTRACTS_ROOT / "foreground_live_comparison.v1.schema.json"
LANE_ORDER = ["no_memory", "foreground_equivalent", "live_provider"]


@lru_cache(maxsize=1)
def load_foreground_live_comparison_schema() -> dict[str, Any]:
    return json.loads(FOREGROUND_LIVE_COMPARISON_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_foreground_live_comparison(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_foreground_live_comparison_schema())


def _int_metric(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _state_for_lane(payload: Mapping[str, Any], *, live_provider: bool = False) -> str:
    status = str(payload.get("status") or "not_implemented")
    if live_provider and status == "green_passed":
        return "live_proven"
    allowed = {"green_passed", "red_captured", "typed_unavailable", "not_implemented"}
    return status if status in allowed else "not_implemented"


def _claim_scope(
    *,
    failing_metrics: list[str],
    foreground_equivalent_state: str,
    live_provider_state: str,
) -> str:
    if failing_metrics:
        return "not_claimable"
    if live_provider_state == "live_proven":
        return "live_provider_proven"
    if foreground_equivalent_state == "green_passed" and live_provider_state == "typed_unavailable":
        return "foreground_equivalent_with_typed_live_unavailable"
    if foreground_equivalent_state == "green_passed":
        return "foreground_equivalent_only"
    return "not_claimable"


def build_foreground_live_comparison(
    *,
    scenario_id: str,
    no_memory_baseline: Mapping[str, Any],
    foreground_equivalent: Mapping[str, Any],
    live_provider: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare P9 evidence lanes without allowing live/foreground relabeling."""

    no_memory_state = _state_for_lane(no_memory_baseline)
    foreground_equivalent_state = _state_for_lane(foreground_equivalent)
    live_provider_state = _state_for_lane(live_provider, live_provider=True)
    raw_leaks = sum(
        _int_metric(payload, "raw_transcript_leak_count")
        for payload in (no_memory_baseline, foreground_equivalent, live_provider)
    )
    live_mislabels = sum(
        _int_metric(payload, "live_mislabel_count")
        for payload in (no_memory_baseline, foreground_equivalent, live_provider)
    )
    safe_pointers = sum(
        _int_metric(payload, "safe_evidence_pointer_count")
        for payload in (no_memory_baseline, foreground_equivalent, live_provider)
    )
    failing = []
    if raw_leaks > 0:
        failing.append("raw_transcript_leak_count")
    if live_mislabels > 0:
        failing.append("live_mislabel_count")
    if no_memory_state == "red_captured":
        failing.append("no_memory_state")
    if foreground_equivalent_state == "red_captured":
        failing.append("foreground_equivalent_state")
    if live_provider_state == "red_captured":
        failing.append("live_provider_state")
    if foreground_equivalent_state == "green_passed" and safe_pointers <= 0:
        failing.append("safe_evidence_pointer_count")
    failing_metrics = sorted(set(failing))
    comparison = {
        "schema_version": "foreground_live_comparison.v1",
        "comparison_id": uuid.uuid4().hex,
        "scenario_id": str(scenario_id),
        "decision": "green_passed" if not failing_metrics else "red_captured",
        "claim_scope": _claim_scope(
            failing_metrics=failing_metrics,
            foreground_equivalent_state=foreground_equivalent_state,
            live_provider_state=live_provider_state,
        ),
        "lane_order": LANE_ORDER,
        "no_memory_state": no_memory_state,
        "foreground_equivalent_state": foreground_equivalent_state,
        "live_provider_state": live_provider_state,
        "raw_transcript_leak_count": raw_leaks,
        "live_mislabel_count": live_mislabels,
        "safe_evidence_pointer_count": safe_pointers,
        "failing_metrics": failing_metrics,
        "checked_at": utc_now_iso(),
    }
    validate_foreground_live_comparison(comparison)
    return comparison
