from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from runtime.capture.auto_compaction_controller import load_compaction_candidate_episodes
from runtime.capture.live_compaction_observer import run_live_compaction_observer
from runtime.common.vault_root import resolve_vault_root


DEFAULT_COMPACTION_TARGETS = {
    "provider": "ygg-pro1:1",
    "ms1": "ygg-ms1:1",
    "mf1": "ygg-mf1:1",
}


def _parse_targets(values: list[str]) -> dict[str, str]:
    targets = dict(DEFAULT_COMPACTION_TARGETS)
    for value in values:
        if "=" not in value:
            raise ValueError("target must be lane=tmux-target")
        lane, target = value.split("=", 1)
        lane = lane.strip()
        target = target.strip()
        if not lane or not target:
            raise ValueError("target must be lane=tmux-target")
        targets[lane] = target
    return targets


def _default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"live-compact-check-{stamp}"


def run_compaction_check(
    *,
    vault_root: Path | None = None,
    run_id: str | None = None,
    targets: Mapping[str, str] | None = None,
    lines: int = 320,
    runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Observe current lanes and write pointer mementos only for real preflight markers."""

    resolved_vault = resolve_vault_root(workspace_root=Path.cwd()) if vault_root is None else Path(vault_root)
    candidate_episodes = load_compaction_candidate_episodes(vault_root=resolved_vault)
    result = run_live_compaction_observer(
        vault_root=resolved_vault,
        run_id=run_id or _default_run_id(),
        targets=dict(targets or DEFAULT_COMPACTION_TARGETS),
        episodes=candidate_episodes,
        runner=runner,
        lines=lines,
    )
    result["cli"] = {
        "schema_version": "ygg_compaction_check_cli.v1",
        "command": "ygg compact-check",
        "vault_root_resolved": str(resolved_vault),
        "candidate_episode_count": len(candidate_episodes),
        "writes_only_after_preflight_marker": True,
        "watch_supported": True,
        "raw_pane_text_included": False,
    }
    if not result.get("production_ready_axis_pass"):
        result.setdefault("hard_nonclaims", []).append(
            "compact_check_blocked_result_is_not_compact_memento_continuity_pass"
        )
    return result


def run_compaction_watch(
    *,
    vault_root: Path | None = None,
    run_id: str | None = None,
    targets: Mapping[str, str] | None = None,
    lines: int = 320,
    interval_seconds: float = 2.0,
    timeout_seconds: float = 120.0,
    max_attempts: int | None = None,
    runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Repeatedly observe lanes until real compaction proof appears or remains blocked."""

    started = time.monotonic()
    attempt = 0
    last_result: dict[str, Any] | None = None
    effective_run_id = run_id or _default_run_id()
    while True:
        attempt += 1
        last_result = run_compaction_check(
            vault_root=vault_root,
            run_id=effective_run_id,
            targets=targets,
            lines=lines,
            runner=runner,
        )
        last_result["watch"] = {
            "schema_version": "ygg_compaction_watch.v1",
            "attempts": attempt,
            "interval_seconds": interval_seconds,
            "timeout_seconds": timeout_seconds,
            "max_attempts": max_attempts,
            "completed_reason": "pass" if last_result.get("production_ready_axis_pass") else "still_blocked",
            "raw_pane_text_included": False,
        }
        if last_result.get("production_ready_axis_pass"):
            return last_result
        if max_attempts is not None and attempt >= max(1, int(max_attempts)):
            last_result["watch"]["completed_reason"] = "max_attempts_reached"
            return last_result
        if time.monotonic() - started >= max(0.0, float(timeout_seconds)):
            last_result["watch"]["completed_reason"] = "timeout_reached"
            return last_result
        if interval_seconds > 0:
            time.sleep(float(interval_seconds))


def cmd_compact_check(args: list[str]) -> None:
    json_mode = False
    watch_mode = False
    run_id: str | None = None
    vault_root: Path | None = None
    lines = 320
    interval_seconds = 2.0
    timeout_seconds = 120.0
    max_attempts: int | None = None
    target_values: list[str] = []
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--json":
            json_mode = True
            idx += 1
        elif arg == "--watch":
            watch_mode = True
            idx += 1
        elif arg == "--run-id" and idx + 1 < len(args):
            run_id = args[idx + 1]
            idx += 2
        elif arg == "--vault-root" and idx + 1 < len(args):
            vault_root = Path(args[idx + 1])
            idx += 2
        elif arg == "--lines" and idx + 1 < len(args):
            try:
                lines = max(1, int(args[idx + 1]))
            except ValueError:
                print("Usage: ygg compact-check [--json] [--run-id ID] [--vault-root PATH] [--lines N] [--target lane=tmux-target]")
                raise SystemExit(2)
            idx += 2
        elif arg == "--interval" and idx + 1 < len(args):
            try:
                interval_seconds = max(0.0, float(args[idx + 1]))
            except ValueError:
                print("Usage: ygg compact-check [--watch] [--interval N] [--timeout N] [--max-attempts N]")
                raise SystemExit(2)
            idx += 2
        elif arg == "--timeout" and idx + 1 < len(args):
            try:
                timeout_seconds = max(0.0, float(args[idx + 1]))
            except ValueError:
                print("Usage: ygg compact-check [--watch] [--interval N] [--timeout N] [--max-attempts N]")
                raise SystemExit(2)
            idx += 2
        elif arg == "--max-attempts" and idx + 1 < len(args):
            try:
                max_attempts = max(1, int(args[idx + 1]))
            except ValueError:
                print("Usage: ygg compact-check [--watch] [--interval N] [--timeout N] [--max-attempts N]")
                raise SystemExit(2)
            idx += 2
        elif arg == "--target" and idx + 1 < len(args):
            target_values.append(args[idx + 1])
            idx += 2
        else:
            print("Usage: ygg compact-check [--json] [--run-id ID] [--vault-root PATH] [--lines N] [--target lane=tmux-target]")
            raise SystemExit(2)
    try:
        targets = _parse_targets(target_values)
    except ValueError as exc:
        print(f"Error: {exc}")
        raise SystemExit(2)
    if watch_mode:
        result = run_compaction_watch(
            vault_root=vault_root,
            run_id=run_id,
            targets=targets,
            lines=lines,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )
    else:
        result = run_compaction_check(
            vault_root=vault_root,
            run_id=run_id,
            targets=targets,
            lines=lines,
        )
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "pass" if result.get("production_ready_axis_pass") else "blocked"
        print(f"compact-check: {status}")
        blockers = result.get("compact_memento_blockers") or []
        if blockers:
            print("blockers: " + ", ".join(str(item) for item in blockers))
        conditions = result.get("compaction_continuity_conditions") or {}
        print(
            "conditions: "
            f"threshold={conditions.get('threshold_reached')}, "
            f"preflight={conditions.get('preflight_marker_found')}, "
            f"memento={conditions.get('context_guard_memento_write_proven')}"
        )
        watch = result.get("watch") or {}
        if watch:
            print(f"watch: attempts={watch.get('attempts')}, reason={watch.get('completed_reason')}")
    if not result.get("production_ready_axis_pass"):
        raise SystemExit(1)


__all__ = [
    "DEFAULT_COMPACTION_TARGETS",
    "cmd_compact_check",
    "run_compaction_check",
    "run_compaction_watch",
]
