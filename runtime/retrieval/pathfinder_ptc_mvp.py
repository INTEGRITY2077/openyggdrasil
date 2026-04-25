from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from harness_common import DEFAULT_VAULT, RUNTIME_STATE_ROOT, utc_now_iso
from retrieval.pathfinder import validate_pathfinder_bundle
from retrieval.pathfinder_tools import (
    build_support_bundle,
    build_unanchored_bundle,
    find_region,
    find_topic_anchor,
    get_origin_claims,
    get_raw_sources,
    get_recent_episodes,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCRATCH_ROOT = RUNTIME_STATE_ROOT / "pathfinder-ptc-mvp"

def render_default_pathfinder_program(*, recent_limit: int) -> str:
    return (
        "region = tools['find_region'](query_text=query_text)\n"
        "anchor = tools['find_topic_anchor'](query_text=query_text, region_id=region['region_id'])\n"
        "if anchor['topic_id'] is None:\n"
        "    RESULT = tools['build_unanchored_bundle'](query_text=query_text)\n"
        "else:\n"
        "    origin_rows = tools['get_origin_claims'](topic_id=anchor['topic_id'], limit=1)\n"
        f"    recent_rows = tools['get_recent_episodes'](topic_id=anchor['topic_id'], limit={max(1, recent_limit)})\n"
        "    claim_ids = [row['claim_id'] for row in recent_rows + origin_rows if row.get('claim_id')]\n"
        "    source_paths = tools['get_raw_sources'](topic_id=anchor['topic_id'], claim_ids=claim_ids)\n"
        "    RESULT = tools['build_support_bundle'](\n"
        "        query_text=query_text,\n"
        "        anchor=anchor,\n"
        "        origin_rows=origin_rows,\n"
        "        recent_rows=recent_rows,\n"
        "        source_paths=source_paths,\n"
        "    )\n"
    )


class PathfinderPTCResultGate:
    def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise RuntimeError("Pathfinder PTC runtime did not return a mapping payload")
        bundle = dict(payload)
        validate_pathfinder_bundle(bundle)
        return bundle


class PathfinderPTCMVPRuntime:
    """PTC-inspired bounded scratch-runtime for Pathfinder.

    This MVP does not execute dynamic Python programs. It provides:
    - scratch workspace materialization
    - explicit read-only retrieval tool surface
    - tool-call transcript capture
    - final result gating against the Pathfinder bundle schema
    """

    def __init__(
        self,
        *,
        vault_root: Path = DEFAULT_VAULT,
        scratch_root: Path = DEFAULT_SCRATCH_ROOT,
        anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        self.vault_root = vault_root
        self.scratch_root = scratch_root
        self.anchor_evaluator = anchor_evaluator
        self.result_gate = PathfinderPTCResultGate()

    def _tool_surface(self, transcript: list[dict[str, Any]]) -> dict[str, Callable[..., Any]]:
        def wrap(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def inner(**kwargs: Any) -> Any:
                result = fn(**kwargs)
                transcript.append(
                    {
                        "tool": name,
                        "kwargs": kwargs,
                        "result_preview": str(result)[:600],
                    }
                )
                return result

            return inner

        return {
            "find_region": wrap(
                "find_region",
                lambda **kwargs: find_region(vault_root=self.vault_root, **kwargs),
            ),
            "find_topic_anchor": wrap(
                "find_topic_anchor",
                lambda **kwargs: find_topic_anchor(
                    vault_root=self.vault_root,
                    evaluator=self.anchor_evaluator,
                    **kwargs,
                ),
            ),
            "get_origin_claims": wrap(
                "get_origin_claims",
                lambda **kwargs: get_origin_claims(vault_root=self.vault_root, **kwargs),
            ),
            "get_recent_episodes": wrap(
                "get_recent_episodes",
                lambda **kwargs: get_recent_episodes(vault_root=self.vault_root, **kwargs),
            ),
            "get_raw_sources": wrap(
                "get_raw_sources",
                lambda **kwargs: get_raw_sources(vault_root=self.vault_root, **kwargs),
            ),
            "build_support_bundle": wrap("build_support_bundle", build_support_bundle),
            "build_unanchored_bundle": wrap("build_unanchored_bundle", build_unanchored_bundle),
        }

    def _execute_default_plan(
        self,
        *,
        query_text: str,
        recent_limit: int,
        tools: Mapping[str, Callable[..., Any]],
    ) -> dict[str, Any]:
        region = tools["find_region"](query_text=query_text)
        anchor = tools["find_topic_anchor"](query_text=query_text, region_id=region["region_id"])
        if anchor["topic_id"] is None:
            return tools["build_unanchored_bundle"](query_text=query_text)

        origin_rows = tools["get_origin_claims"](topic_id=anchor["topic_id"], limit=1)
        recent_rows = tools["get_recent_episodes"](
            topic_id=anchor["topic_id"],
            limit=max(1, recent_limit),
        )
        claim_ids = [
            row["claim_id"]
            for row in recent_rows + origin_rows
            if row.get("claim_id")
        ]
        source_paths = tools["get_raw_sources"](
            topic_id=anchor["topic_id"],
            claim_ids=claim_ids,
        )
        return tools["build_support_bundle"](
            query_text=query_text,
            anchor=anchor,
            origin_rows=origin_rows,
            recent_rows=recent_rows,
            source_paths=source_paths,
        )

    def execute(
        self,
        *,
        query_text: str,
        program_source: str | None = None,
        recent_limit: int = 3,
    ) -> dict[str, Any]:
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(
            tempfile.mkdtemp(
                prefix="run-",
                dir=str(self.scratch_root),
            )
        )
        if program_source is not None:
            raise RuntimeError(
                "custom Pathfinder PTC program_source is disabled; use the deterministic default plan"
            )
        active_program = program_source or render_default_pathfinder_program(recent_limit=recent_limit)
        program_path = run_dir / "worker_plan.py"
        program_path.write_text(active_program, encoding="utf-8")

        transcript: list[dict[str, Any]] = []
        tool_surface = self._tool_surface(transcript)
        raw_result = self._execute_default_plan(
            query_text=query_text,
            recent_limit=recent_limit,
            tools=tool_surface,
        )
        bundle = self.result_gate.validate(raw_result)

        tool_calls_path = run_dir / "tool_calls.json"
        tool_calls_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_path = run_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        runtime_meta = {
            "runtime_mode": "ptc-inspired-deterministic-tool-plan",
            "query_text": query_text,
            "recent_limit": recent_limit,
            "program_path": str(program_path),
            "program_source_status": "deterministic_plan_not_executed_as_code",
            "tool_calls_path": str(tool_calls_path),
            "bundle_path": str(bundle_path),
            "tool_call_count": len(transcript),
            "generated_at": utc_now_iso(),
        }
        (run_dir / "runtime.json").write_text(
            json.dumps(runtime_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "bundle": bundle,
            "runtime": runtime_meta,
            "tool_calls": transcript,
            "scratch_dir": str(run_dir),
        }


def build_pathfinder_bundle_via_ptc_mvp(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    program_source: str | None = None,
    recent_limit: int = 3,
    scratch_root: Path = DEFAULT_SCRATCH_ROOT,
) -> dict[str, Any]:
    runtime = PathfinderPTCMVPRuntime(
        vault_root=vault_root,
        scratch_root=scratch_root,
        anchor_evaluator=anchor_evaluator,
    )
    return runtime.execute(
        query_text=query_text,
        program_source=program_source,
        recent_limit=recent_limit,
    )
