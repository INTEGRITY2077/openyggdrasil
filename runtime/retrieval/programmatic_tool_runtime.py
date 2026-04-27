from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import jsonschema

from harness_common import DEFAULT_VAULT, RUNTIME_STATE_ROOT, utc_now_iso
from ptc.engine import (
    STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE,
    structural_anchor_fallback_evaluator,
)
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
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
TRACE_SCHEMA_PATH = CONTRACTS_ROOT / "programmatic_tool_runtime_trace.v1.schema.json"
DEFAULT_SCRATCH_ROOT = RUNTIME_STATE_ROOT / "programmatic-tool-runtime"
SCHEMA_VERSION = "programmatic_tool_runtime_trace.v1"
DEFAULT_TRACE_CLAIM_SCOPE = "ptc_contract_poc_not_live_provider_readiness"
SAME_RUN_CONTEXT_TRACE_CLAIM_SCOPE = "ptc_same_run_context_accepted_not_live_readiness"
SAME_RUN_CONTEXT_ABSENT = "absent"
SAME_RUN_CONTEXT_ACCEPTED = "accepted"
SAME_RUN_CONTEXT_REQUIRED_KEYS = (
    "same_run_id",
    "same_run_witness_ref",
    "same_run_source_kind",
    "evidence_chain_status",
    "source_authority",
)
SAME_RUN_CONTEXT_ALLOWED_KEYS = frozenset(
    {
        *SAME_RUN_CONTEXT_REQUIRED_KEYS,
        "mailbox_delivery_ref",
        "hermes_consumption_ref",
        "ptc_trace_ref",
        "bubblewrap_trace_ref",
    }
)
SAME_RUN_CONTEXT_SOURCE_KIND = "physical_live_same_run"
SAME_RUN_CONTEXT_VERIFIED_STATUS = "upstream_verified"
UNANCHORED_BRANCH_REASON_CODE = "unanchored_anchor_early_result"


class ProgrammaticToolRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Capability:
    capability_id: str
    required_inputs: Mapping[str, str]
    read_only: bool
    output_kind: str
    handler: Callable[..., Any]

    def validate_input(self, payload: Mapping[str, Any]) -> None:
        missing = [key for key in self.required_inputs if key not in payload]
        if missing:
            raise ProgrammaticToolRuntimeError(
                f"{self.capability_id} input missing required keys: {', '.join(missing)}"
            )
        for key, expected in self.required_inputs.items():
            value = payload[key]
            if not _matches_contract_type(value, expected):
                raise ProgrammaticToolRuntimeError(
                    f"{self.capability_id}.{key} expected {expected}"
                )

    def as_registry_row(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "read_only": self.read_only,
            "input_contract": sorted(self.required_inputs.keys()),
            "output_kind": self.output_kind,
        }


def _matches_contract_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "nullable_string":
        return value is None or isinstance(value, str)
    raise ProgrammaticToolRuntimeError(f"unknown input contract type: {expected}")


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _require_non_empty_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgrammaticToolRuntimeError(f"same_run_context.{field_name} is required")
    return value


def _normalize_same_run_context(
    same_run_context: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    if same_run_context is None:
        return SAME_RUN_CONTEXT_ABSENT, None
    if not isinstance(same_run_context, Mapping):
        raise ProgrammaticToolRuntimeError("same_run_context must be an object")

    unknown_keys = sorted(str(key) for key in set(same_run_context.keys()) - SAME_RUN_CONTEXT_ALLOWED_KEYS)
    if unknown_keys:
        raise ProgrammaticToolRuntimeError(
            f"same_run_context has unsupported keys: {', '.join(unknown_keys)}"
        )

    normalized: dict[str, str] = {}
    for key in SAME_RUN_CONTEXT_REQUIRED_KEYS:
        normalized[key] = _require_non_empty_string(same_run_context.get(key), field_name=key)
    for key in sorted(SAME_RUN_CONTEXT_ALLOWED_KEYS - set(SAME_RUN_CONTEXT_REQUIRED_KEYS)):
        if key in same_run_context:
            normalized[key] = _require_non_empty_string(same_run_context[key], field_name=key)

    if normalized["same_run_source_kind"] != SAME_RUN_CONTEXT_SOURCE_KIND:
        raise ProgrammaticToolRuntimeError(
            "same-run source must be physical_live_same_run from an upstream evidence chain"
        )
    if normalized["evidence_chain_status"] != SAME_RUN_CONTEXT_VERIFIED_STATUS:
        raise ProgrammaticToolRuntimeError(
            "same_run_context.evidence_chain_status must be upstream_verified"
        )
    return SAME_RUN_CONTEXT_ACCEPTED, normalized


def _is_unanchored_anchor_result(result: Any) -> bool:
    if not isinstance(result, Mapping):
        return False
    anchor_type = str(result.get("anchor_type") or "").strip().lower()
    return anchor_type == "none" or result.get("topic_id") is None


def _resolve_path(value: Any, path: Sequence[str]) -> Any:
    current = value
    for part in path:
        if isinstance(current, Mapping):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ProgrammaticToolRuntimeError(f"cannot resolve path through {type(current).__name__}")
    return current


def _resolve_binding(binding: Any, *, context: Mapping[str, Any], step_results: Mapping[str, Any]) -> Any:
    if isinstance(binding, Mapping):
        keys = set(binding.keys())
        if keys == {"literal"}:
            return binding["literal"]
        if "from_context" in binding:
            key = str(binding["from_context"])
            if key not in context:
                raise ProgrammaticToolRuntimeError(f"unknown context binding: {key}")
            return context[key]
        if "from_step" in binding:
            step_id = str(binding["from_step"])
            if step_id not in step_results:
                raise ProgrammaticToolRuntimeError(f"unknown step binding: {step_id}")
            path = [str(part) for part in binding.get("path", [])]
            return _resolve_path(step_results[step_id], path)
        return {
            str(key): _resolve_binding(value, context=context, step_results=step_results)
            for key, value in binding.items()
        }
    if isinstance(binding, list):
        return [
            _resolve_binding(value, context=context, step_results=step_results)
            for value in binding
        ]
    return binding


def _collect_claim_ids(*, recent_rows: list[Any], origin_rows: list[Any]) -> list[str]:
    claim_ids: list[str] = []
    for row in list(recent_rows) + list(origin_rows):
        if not isinstance(row, Mapping):
            continue
        claim_id = str(row.get("claim_id") or "").strip()
        if claim_id and claim_id not in claim_ids:
            claim_ids.append(claim_id)
    return claim_ids


def build_default_pathfinder_program(*, recent_limit: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "region",
            "capability_id": "locate_region",
            "input": {"query_text": {"from_context": "query_text"}},
        },
        {
            "step_id": "anchor",
            "capability_id": "select_topic_anchor",
            "input": {
                "query_text": {"from_context": "query_text"},
                "region_id": {"from_step": "region", "path": ["region_id"]},
            },
        },
        {
            "step_id": "origin",
            "capability_id": "read_origin_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": 1},
            },
        },
        {
            "step_id": "recent",
            "capability_id": "read_recent_claims",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "limit": {"literal": max(1, recent_limit)},
            },
        },
        {
            "step_id": "claim_ids",
            "capability_id": "collect_claim_ids",
            "input": {
                "recent_rows": {"from_step": "recent"},
                "origin_rows": {"from_step": "origin"},
            },
        },
        {
            "step_id": "sources",
            "capability_id": "read_source_paths",
            "input": {
                "topic_id": {"from_step": "anchor", "path": ["topic_id"]},
                "claim_ids": {"from_step": "claim_ids"},
            },
        },
        {
            "step_id": "bundle",
            "capability_id": "assemble_support_bundle",
            "input": {
                "query_text": {"from_context": "query_text"},
                "anchor": {"from_step": "anchor"},
                "origin_rows": {"from_step": "origin"},
                "recent_rows": {"from_step": "recent"},
                "source_paths": {"from_step": "sources"},
            },
        },
    ]


@lru_cache(maxsize=1)
def load_programmatic_tool_runtime_trace_schema() -> dict[str, Any]:
    return json.loads(TRACE_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_programmatic_tool_runtime_trace(payload: Mapping[str, Any]) -> None:
    trace = dict(payload)
    jsonschema.validate(
        instance=trace,
        schema=load_programmatic_tool_runtime_trace_schema(),
    )
    program_ids = [str(step["step_id"]) for step in trace["program"]]
    call_ids = [str(call["step_id"]) for call in trace["capability_calls"]]
    if program_ids != call_ids:
        raise ValueError("program step order must match completed capability calls")
    final_step_id = str(trace["final_result"]["final_step_id"])
    if final_step_id not in call_ids:
        raise ValueError("final_result.final_step_id must be a completed call")
    registered = {str(row["capability_id"]) for row in trace["capability_registry"]}
    called = {str(call["capability_id"]) for call in trace["capability_calls"]}
    if not called.issubset(registered):
        raise ValueError("capability call references an unregistered capability")
    same_run_status = trace["same_run_context_status"]
    same_run_context = trace["same_run_context"]
    if same_run_status == SAME_RUN_CONTEXT_ABSENT and same_run_context is not None:
        raise ValueError("absent same_run_context_status must not carry same_run_context")
    if same_run_status == SAME_RUN_CONTEXT_ABSENT:
        if trace["claim_scope"] != DEFAULT_TRACE_CLAIM_SCOPE:
            raise ValueError("absent same_run_context_status must use structural claim scope")
        if trace["gates"]["same_run_context_upstream_verified"]:
            raise ValueError("absent same_run_context_status must not be upstream verified")
    if same_run_status == SAME_RUN_CONTEXT_ACCEPTED:
        if not isinstance(same_run_context, Mapping):
            raise ValueError("accepted same_run_context_status requires same_run_context")
        if trace["claim_scope"] != SAME_RUN_CONTEXT_TRACE_CLAIM_SCOPE:
            raise ValueError("accepted same_run_context_status must use same-run context claim scope")
        if not trace["gates"]["same_run_context_upstream_verified"]:
            raise ValueError("accepted same_run_context_status must be upstream verified")
        if same_run_context["evidence_chain_status"] != SAME_RUN_CONTEXT_VERIFIED_STATUS:
            raise ValueError("same_run_context must be upstream_verified")
        if same_run_context["same_run_source_kind"] != SAME_RUN_CONTEXT_SOURCE_KIND:
            raise ValueError("same_run_context must come from a physical live same-run source")
        if trace["gates"]["same_run_context_fabricated"]:
            raise ValueError("same_run_context must not be fabricated by the runtime")


class ProgrammaticToolRuntime:
    def __init__(
        self,
        *,
        capabilities: Mapping[str, Capability],
        scratch_root: Path = DEFAULT_SCRATCH_ROOT,
        max_steps: int = 16,
    ) -> None:
        self.capabilities = dict(capabilities)
        self.scratch_root = scratch_root
        self.max_steps = max_steps

    def execute(
        self,
        *,
        query_text: str,
        program: Sequence[Mapping[str, Any]],
        final_step_id: str | None = None,
        program_source: str | None = None,
        final_result_kind: str = "pathfinder_bundle",
        same_run_context: Mapping[str, Any] | None = None,
        extra_reason_codes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if program_source is not None:
            raise ProgrammaticToolRuntimeError(
                "program_source execution is disabled; use bounded JSON plan steps"
            )
        if not query_text.strip():
            raise ProgrammaticToolRuntimeError("query_text is required")
        if not program:
            raise ProgrammaticToolRuntimeError("program must include at least one step")
        if len(program) > self.max_steps:
            raise ProgrammaticToolRuntimeError("program exceeds max_steps")
        same_run_context_status, normalized_same_run_context = _normalize_same_run_context(
            same_run_context
        )
        claim_scope = (
            SAME_RUN_CONTEXT_TRACE_CLAIM_SCOPE
            if same_run_context_status == SAME_RUN_CONTEXT_ACCEPTED
            else DEFAULT_TRACE_CLAIM_SCOPE
        )

        self.scratch_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=str(self.scratch_root)))
        context = {"query_text": query_text}
        step_results: dict[str, Any] = {}
        program_rows: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []
        runtime_reason_codes: list[str] = []
        seen_steps: set[str] = set()

        for index, raw_step in enumerate(program, start=1):
            step_id = str(raw_step.get("step_id") or "").strip()
            capability_id = str(raw_step.get("capability_id") or "").strip()
            if not step_id or step_id in seen_steps:
                raise ProgrammaticToolRuntimeError("program step_id must be unique and non-empty")
            seen_steps.add(step_id)
            capability = self.capabilities.get(capability_id)
            if capability is None:
                raise ProgrammaticToolRuntimeError(f"unknown capability: {capability_id}")
            if not capability.read_only:
                raise ProgrammaticToolRuntimeError(f"write capability forbidden: {capability_id}")

            raw_input = raw_step.get("input")
            if not isinstance(raw_input, Mapping):
                raise ProgrammaticToolRuntimeError(f"{step_id}.input must be an object")
            resolved_input = {
                str(key): _resolve_binding(value, context=context, step_results=step_results)
                for key, value in raw_input.items()
            }
            capability.validate_input(resolved_input)
            result = capability.handler(**resolved_input)
            result_ref = run_dir / f"{index:02d}_{step_id}.json"
            _write_json(result_ref, result)
            result_sha256 = _sha256_payload(result)
            step_results[step_id] = result
            program_rows.append(
                {
                    "step_id": step_id,
                    "capability_id": capability_id,
                    "input_binding_keys": sorted(str(key) for key in raw_input.keys()),
                }
            )
            calls.append(
                {
                    "step_id": step_id,
                    "capability_id": capability_id,
                    "status": "completed",
                    "read_only": True,
                    "input_keys": sorted(resolved_input.keys()),
                    "output_kind": capability.output_kind,
                    "result_sha256": result_sha256,
                    "result_ref": str(result_ref),
                }
            )
            if (
                step_id == "anchor"
                and _is_unanchored_anchor_result(result)
                and final_result_kind == "pathfinder_bundle"
                and (final_step_id is None or final_step_id == "bundle")
                and "bundle" not in seen_steps
            ):
                unanchored_capability_id = "assemble_unanchored_bundle"
                unanchored_capability = self.capabilities.get(unanchored_capability_id)
                if unanchored_capability is None:
                    raise ProgrammaticToolRuntimeError(
                        "unanchored branch requires assemble_unanchored_bundle"
                    )
                if not unanchored_capability.read_only:
                    raise ProgrammaticToolRuntimeError(
                        f"write capability forbidden: {unanchored_capability_id}"
                    )
                step_id = "bundle"
                seen_steps.add(step_id)
                raw_input = {"query_text": {"from_context": "query_text"}}
                resolved_input = {"query_text": query_text}
                unanchored_capability.validate_input(resolved_input)
                result = unanchored_capability.handler(**resolved_input)
                result_ref = run_dir / f"{len(calls) + 1:02d}_{step_id}.json"
                _write_json(result_ref, result)
                result_sha256 = _sha256_payload(result)
                step_results[step_id] = result
                program_rows.append(
                    {
                        "step_id": step_id,
                        "capability_id": unanchored_capability_id,
                        "input_binding_keys": sorted(str(key) for key in raw_input.keys()),
                    }
                )
                calls.append(
                    {
                        "step_id": step_id,
                        "capability_id": unanchored_capability_id,
                        "status": "completed",
                        "read_only": True,
                        "input_keys": sorted(resolved_input.keys()),
                        "output_kind": unanchored_capability.output_kind,
                        "result_sha256": result_sha256,
                        "result_ref": str(result_ref),
                    }
                )
                runtime_reason_codes.append(UNANCHORED_BRANCH_REASON_CODE)
                break

        final_id = final_step_id or program_rows[-1]["step_id"]
        if final_id not in step_results:
            raise ProgrammaticToolRuntimeError(f"unknown final_step_id: {final_id}")
        final_result = step_results[final_id]
        if final_result_kind != "pathfinder_bundle":
            raise ProgrammaticToolRuntimeError(f"unsupported final_result_kind: {final_result_kind}")
        if not isinstance(final_result, Mapping):
            raise ProgrammaticToolRuntimeError("final result must be an object")
        validate_pathfinder_bundle(final_result)
        final_result_ref = run_dir / "final_result.json"
        _write_json(final_result_ref, final_result)
        final_sha256 = _sha256_payload(final_result)
        reason_codes = [
            "bounded_programmatic_tool_contract_executed",
            "json_plan_no_dynamic_code_execution",
            "pathfinder_bundle_final_gate_validated",
            (
                "same_run_context_accepted_from_upstream"
                if same_run_context_status == SAME_RUN_CONTEXT_ACCEPTED
                else "same_run_context_absent_structural_trace"
            ),
        ]
        for reason_code in list(extra_reason_codes or []) + runtime_reason_codes:
            if reason_code not in reason_codes:
                reason_codes.append(str(reason_code))

        trace = {
            "schema_version": SCHEMA_VERSION,
            "trace_id": uuid.uuid4().hex,
            "runtime_mode": "bounded_programmatic_tool_plan",
            "query_text": query_text,
            "decision": "completed",
            "claim_scope": claim_scope,
            "same_run_context_status": same_run_context_status,
            "same_run_context": normalized_same_run_context,
            "policy": {
                "program_source_execution": "disabled",
                "allow_write_capabilities": False,
                "sandbox_claim": "not_claimed_read_only_contract",
                "max_steps": self.max_steps,
            },
            "capability_registry": [
                capability.as_registry_row()
                for capability in sorted(self.capabilities.values(), key=lambda item: item.capability_id)
                if capability.read_only
            ],
            "program": program_rows,
            "capability_calls": calls,
            "final_result": {
                "final_step_id": final_id,
                "result_kind": final_result_kind,
                "result_sha256": final_sha256,
                "result_ref": str(final_result_ref),
            },
            "gates": {
                "unknown_capability_blocked": True,
                "input_validation_enforced": True,
                "permission_policy_enforced": True,
                "final_result_validated": True,
                "dynamic_code_execution_allowed": False,
                "private_source_copied": False,
                "graph_output_treated_as_sot": False,
                "live_provider_readiness_claimed": False,
                "same_run_context_upstream_verified": (
                    same_run_context_status == SAME_RUN_CONTEXT_ACCEPTED
                ),
                "same_run_context_fabricated": False,
                "historical_fixture_or_contract_only_trace_accepted": False,
            },
            "reason_codes": reason_codes,
            "generated_at": utc_now_iso(),
        }
        validate_programmatic_tool_runtime_trace(trace)
        trace_ref = run_dir / "trace.json"
        _write_json(trace_ref, trace)
        return {
            "trace": trace,
            "final_result": final_result,
            "step_results": step_results,
            "scratch_dir": str(run_dir),
            "trace_ref": str(trace_ref),
            "final_result_ref": str(final_result_ref),
        }


def build_pathfinder_capabilities(
    *,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Capability]:
    return {
        "locate_region": Capability(
            capability_id="locate_region",
            required_inputs={"query_text": "string"},
            read_only=True,
            output_kind="region_hint",
            handler=lambda **kwargs: find_region(vault_root=vault_root, **kwargs),
        ),
        "select_topic_anchor": Capability(
            capability_id="select_topic_anchor",
            required_inputs={"query_text": "string", "region_id": "string"},
            read_only=True,
            output_kind="topic_anchor",
            handler=lambda **kwargs: find_topic_anchor(
                vault_root=vault_root,
                evaluator=anchor_evaluator,
                **kwargs,
            ),
        ),
        "read_origin_claims": Capability(
            capability_id="read_origin_claims",
            required_inputs={"topic_id": "string", "limit": "integer"},
            read_only=True,
            output_kind="origin_claim_rows",
            handler=lambda **kwargs: get_origin_claims(vault_root=vault_root, **kwargs),
        ),
        "read_recent_claims": Capability(
            capability_id="read_recent_claims",
            required_inputs={"topic_id": "string", "limit": "integer"},
            read_only=True,
            output_kind="recent_claim_rows",
            handler=lambda **kwargs: get_recent_episodes(vault_root=vault_root, **kwargs),
        ),
        "collect_claim_ids": Capability(
            capability_id="collect_claim_ids",
            required_inputs={"recent_rows": "array", "origin_rows": "array"},
            read_only=True,
            output_kind="claim_id_list",
            handler=_collect_claim_ids,
        ),
        "read_source_paths": Capability(
            capability_id="read_source_paths",
            required_inputs={"topic_id": "string", "claim_ids": "array"},
            read_only=True,
            output_kind="source_path_list",
            handler=lambda **kwargs: get_raw_sources(vault_root=vault_root, **kwargs),
        ),
        "assemble_support_bundle": Capability(
            capability_id="assemble_support_bundle",
            required_inputs={
                "query_text": "string",
                "anchor": "object",
                "origin_rows": "array",
                "recent_rows": "array",
                "source_paths": "array",
            },
            read_only=True,
            output_kind="pathfinder_bundle",
            handler=build_support_bundle,
        ),
        "assemble_unanchored_bundle": Capability(
            capability_id="assemble_unanchored_bundle",
            required_inputs={"query_text": "string"},
            read_only=True,
            output_kind="pathfinder_bundle",
            handler=build_unanchored_bundle,
        ),
    }


def build_pathfinder_bundle_via_programmatic_tool_runtime(
    *,
    query_text: str,
    vault_root: Path = DEFAULT_VAULT,
    anchor_evaluator: Callable[..., Mapping[str, Any]] | None = None,
    program: Sequence[Mapping[str, Any]] | None = None,
    recent_limit: int = 3,
    scratch_root: Path = DEFAULT_SCRATCH_ROOT,
    program_source: str | None = None,
    same_run_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structural_anchor_fallback_used = anchor_evaluator is None
    active_anchor_evaluator = anchor_evaluator or structural_anchor_fallback_evaluator
    runtime = ProgrammaticToolRuntime(
        capabilities=build_pathfinder_capabilities(
            vault_root=vault_root,
            anchor_evaluator=active_anchor_evaluator,
        ),
        scratch_root=scratch_root,
    )
    active_program = list(program or build_default_pathfinder_program(recent_limit=recent_limit))
    return runtime.execute(
        query_text=query_text,
        program=active_program,
        final_step_id="bundle",
        program_source=program_source,
        same_run_context=same_run_context,
        extra_reason_codes=(
            [STRUCTURAL_ANCHOR_FALLBACK_REASON_CODE]
            if structural_anchor_fallback_used
            else None
        ),
    )
