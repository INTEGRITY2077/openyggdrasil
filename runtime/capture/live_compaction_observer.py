from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from runtime.capture.auto_compaction_controller import (
    parse_preflight_compression,
    run_auto_compaction_controller,
)


PREFLIGHT_THRESHOLD_TOKENS = 136_000
TOKEN_K_RE = re.compile(r"(?P<used>\d+(?:\.\d+)?)K/(?P<max>\d+(?:\.\d+)?)K")
TOKEN_INT_RE = re.compile(r"(?P<used>\d{2,6})/(?P<max>\d{2,6})")
MEMENTO_RE = re.compile(r"precompact_memento|memento|context guard", re.IGNORECASE)

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def parse_token_meter(text: str) -> dict[str, Any]:
    """Parse a Hermes status token meter without treating it as compaction proof."""

    text = str(text or "")
    matches = list(TOKEN_K_RE.finditer(text))
    if matches:
        match = matches[-1]
        used = int(float(match.group("used")) * 1000)
        max_tokens = int(float(match.group("max")) * 1000)
        return {
            "found": True,
            "used_tokens": used,
            "max_tokens": max_tokens,
            "source_shape": "k_meter",
            "source_label": f"{match.group('used')}K/{match.group('max')}K",
            "raw_text_included": False,
        }
    int_matches = list(TOKEN_INT_RE.finditer(text))
    if int_matches:
        match = int_matches[-1]
        return {
            "found": True,
            "used_tokens": int(match.group("used")),
            "max_tokens": int(match.group("max")),
            "source_shape": "int_meter",
            "source_label": f"{match.group('used')}/{match.group('max')}",
            "raw_text_included": False,
        }
    return {
        "found": False,
        "used_tokens": 0,
        "max_tokens": 0,
        "source_shape": None,
        "source_label": None,
        "raw_text_included": False,
    }


def observe_compaction_text(
    text: str,
    *,
    lane: str,
    threshold_tokens: int = PREFLIGHT_THRESHOLD_TOKENS,
) -> dict[str, Any]:
    """Return a sanitized compaction observation from pane text."""

    preflight = parse_preflight_compression(text)
    token_meter = parse_token_meter(text)
    used_tokens = int(token_meter.get("used_tokens") or 0)
    threshold_reached = bool(preflight.get("threshold_reached")) or used_tokens >= threshold_tokens
    preflight_event = dict(preflight.get("compaction_event") or {})
    if preflight_event:
        preflight_event["lane"] = lane
    return {
        "schema_version": "live_compaction_lane_observation.v1",
        "lane": lane,
        "threshold_tokens": threshold_tokens,
        "token_meter": token_meter,
        "preflight": preflight,
        "threshold_reached": threshold_reached,
        "preflight_marker_found": bool(preflight_event),
        "memento_marker_found": bool(MEMENTO_RE.search(str(text or ""))),
        "compaction_event": preflight_event or None,
        "raw_pane_text_included": False,
    }


def capture_tmux_target(
    target: str,
    *,
    lines: int = 320,
    runner: Runner | None = None,
) -> tuple[bool, str, str]:
    """Capture a tmux target. The caller decides whether to persist raw text."""

    command = ["tmux", "capture-pane", "-p", "-t", target, "-S", f"-{max(lines, 1)}"]
    run = runner or _default_runner
    result = run(command)
    text = result.stdout if isinstance(result.stdout, str) else ""
    error = result.stderr if isinstance(result.stderr, str) else ""
    return result.returncode == 0, text, error.strip()


def observe_tmux_targets(
    targets: Mapping[str, str],
    *,
    lines: int = 320,
    runner: Runner | None = None,
    threshold_tokens: int = PREFLIGHT_THRESHOLD_TOKENS,
) -> dict[str, Any]:
    lanes: dict[str, Any] = {}
    blockers: list[str] = []
    for lane, target in targets.items():
        ok, text, error = capture_tmux_target(target, lines=lines, runner=runner)
        if not ok:
            lanes[lane] = {
                "schema_version": "live_compaction_lane_observation.v1",
                "lane": lane,
                "target": target,
                "capture_ok": False,
                "error": error or "tmux_capture_failed",
                "raw_pane_text_included": False,
            }
            blockers.append(f"{lane}:tmux_capture_failed")
            continue
        row = observe_compaction_text(text, lane=lane, threshold_tokens=threshold_tokens)
        row["target"] = target
        row["capture_ok"] = True
        lanes[lane] = row
    threshold_reached = any(bool(row.get("threshold_reached")) for row in lanes.values())
    preflight_marker_found = any(bool(row.get("preflight_marker_found")) for row in lanes.values())
    memento_marker_found = any(bool(row.get("memento_marker_found")) for row in lanes.values())
    if not threshold_reached:
        blockers.append("live_panes_below_preflight_threshold")
    if not preflight_marker_found:
        blockers.append("live_panes_no_preflight_marker")
    if not memento_marker_found:
        blockers.append("live_panes_no_memento_marker")
    return {
        "schema_version": "live_compaction_observation.v1",
        "status": "pass" if threshold_reached and preflight_marker_found and memento_marker_found else "blocked",
        "threshold_tokens": threshold_tokens,
        "pass_conditions": {
            "threshold_reached": threshold_reached,
            "preflight_marker_found": preflight_marker_found,
            "memento_marker_found": memento_marker_found,
        },
        "blockers": blockers,
        "lanes": lanes,
        "raw_pane_text_included": False,
        "hard_nonclaims": [
            "token_meter_is_not_actual_compaction_event",
            "preflight_marker_without_pointer_memento_is_not_continuity",
            "raw_pane_text_is_not_stored",
        ],
    }


def run_live_compaction_observer(
    *,
    vault_root: Path,
    run_id: str,
    targets: Mapping[str, str],
    episodes: Sequence[Mapping[str, Any]],
    runner: Runner | None = None,
    lines: int = 320,
) -> dict[str, Any]:
    observation = observe_tmux_targets(targets, lines=lines, runner=runner)
    marker_text = ""
    for row in observation["lanes"].values():
        event = row.get("compaction_event") if isinstance(row, Mapping) else None
        if isinstance(event, Mapping) and event.get("token_estimate") and event.get("threshold"):
            marker_text = (
                f"Preflight compression: ~{event['token_estimate']} tokens >= "
                f"{event['threshold']} threshold."
            )
            break
    if marker_text:
        context_guard = run_auto_compaction_controller(
            vault_root=vault_root,
            run_id=run_id,
            preflight_text=marker_text,
            episodes=episodes,
        )
    else:
        context_guard = None
    return {
        "schema_version": "live_compaction_observer_result.v1",
        "run_id": run_id,
        "observation": observation,
        "context_guard_result": context_guard,
        "production_ready_axis_pass": bool(
            context_guard
            and context_guard.get("status") == "pass"
            and context_guard.get("actual_compaction_event", {}).get("proven") is True
            and context_guard.get("precompact_memento_or_source_ref") is True
        ),
        "hard_nonclaims": [
            "observer_result_is_not_production_ready_by_itself",
            "absence_of_marker_must_remain_blocked",
            "graphify_product_ux_is_unrelated_to_compaction_observer",
        ],
    }


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--targets-json", required=True, type=Path)
    parser.add_argument("--episodes-json", required=True, type=Path)
    parser.add_argument("--lines", type=int, default=320)
    args = parser.parse_args()
    targets = json.loads(args.targets_json.read_text(encoding="utf-8"))
    episodes = json.loads(args.episodes_json.read_text(encoding="utf-8"))
    result = run_live_compaction_observer(
        vault_root=args.vault_root,
        run_id=args.run_id,
        targets=targets,
        episodes=episodes,
        lines=args.lines,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["production_ready_axis_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "capture_tmux_target",
    "observe_compaction_text",
    "observe_tmux_targets",
    "parse_token_meter",
    "run_live_compaction_observer",
]
