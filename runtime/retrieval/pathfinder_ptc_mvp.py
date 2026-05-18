from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from runtime.harness_common import DEFAULT_VAULT, RUNTIME_STATE_ROOT, utc_now_iso
from runtime.reasoning.approved_routing_fact import (
    build_approved_routing_fact_from_ptc_trace,
    build_hermes_routing_receipt,
)
from runtime.retrieval.pathfinder import validate_pathfinder_bundle
from runtime.retrieval.pathfinder_tools import (
    build_support_bundle,
    build_unanchored_bundle,
    find_region,
    find_topic_anchor,
    get_origin_claims,
    get_raw_sources,
    get_recent_episodes,
)
from runtime.ptc.engine import (
    build_pathfinder_ptc_routing_trace,
    structural_anchor_fallback_evaluator,
    render_default_pathfinder_program,
)


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCRATCH_ROOT = RUNTIME_STATE_ROOT / "pathfinder-ptc-mvp"


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
        self.structural_anchor_fallback_used = anchor_evaluator is None
        self.anchor_evaluator = anchor_evaluator or structural_anchor_fallback_evaluator
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
        advisory_effort: str | None = None,
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
        query_token = hashlib.sha256(query_text.strip().encode("utf-8")).hexdigest()[:32]
        bundle_token = hashlib.sha256(
            json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        trace_token = hashlib.sha256(f"{query_token}:{bundle_token}:{run_dir.name}".encode("utf-8")).hexdigest()[:32]
        query_ref = f"query-ref://openyggdrasil/pathfinder-ptc-mvp/{query_token}"
        support_bundle_ref = f"support-bundle-ref://openyggdrasil/pathfinder-ptc-mvp/{bundle_token}"
        ptc_trace_ref = f"ptc-trace-ref://openyggdrasil/pathfinder-ptc-mvp/{trace_token}"
        routing_trace = build_pathfinder_ptc_routing_trace(
            query_ref=query_ref,
            support_bundle_ref=support_bundle_ref,
            ptc_trace_ref=ptc_trace_ref,
            advisory_effort=advisory_effort,
        )
        approved_routing_fact = build_approved_routing_fact_from_ptc_trace(routing_trace)
        hermes_routing_receipt = build_hermes_routing_receipt(approved_routing_fact)
        routing_trace_path = run_dir / "pathfinder_ptc_routing_trace.json"
        routing_trace_path.write_text(
            json.dumps(routing_trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        approved_fact_path = run_dir / "approved_routing_fact.json"
        approved_fact_path.write_text(
            json.dumps(approved_routing_fact, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        hermes_receipt_path = run_dir / "hermes_routing_receipt.json"
        hermes_receipt_path.write_text(
            json.dumps(hermes_routing_receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        runtime_meta = {
            "runtime_mode": "ptc-inspired-deterministic-tool-plan",
            "query_text": query_text,
            "recent_limit": recent_limit,
            "claim_scope": "structural_readiness_only",
            "anchor_evaluator_status": (
                "structural_fallback_used"
                if self.structural_anchor_fallback_used
                else "caller_supplied"
            ),
            "program_path": str(program_path),
            "program_source_status": "deterministic_plan_not_executed_as_code",
            "tool_calls_path": str(tool_calls_path),
            "bundle_path": str(bundle_path),
            "route_id": hermes_routing_receipt["route_id"],
            "receipt_id": hermes_routing_receipt["receipt_id"],
            "approved_effort": hermes_routing_receipt["approved_effort"],
            "lease_group": hermes_routing_receipt["lease_group"],
            "query_ref": query_ref,
            "support_bundle_ref": support_bundle_ref,
            "ptc_trace_ref": ptc_trace_ref,
            "approved_routing_fact_ref": hermes_routing_receipt["approved_routing_fact_ref"],
            "routing_trace_path": str(routing_trace_path),
            "approved_routing_fact_path": str(approved_fact_path),
            "hermes_routing_receipt_path": str(hermes_receipt_path),
            "skill_body_included": False,
            "raw_provider_material_included": False,
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
            "routing_trace": routing_trace,
            "approved_routing_fact": approved_routing_fact,
            "hermes_routing_receipt": hermes_routing_receipt,
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
    advisory_effort: str | None = None,
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
        advisory_effort=advisory_effort,
    )
