from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from attachments.deploy_skill import DEPLOY_TARGETS
from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "provider_packaging_known_limitations_matrix.v1.schema.json"
P6_CR1_ACTION = "P6.CR1.phase-close-code-review"

PROVIDER_ORDER = (
    "hermes",
    "codex",
    "claude-code",
    "gemini-antigravity",
    "windsurf",
    "cursor",
    "openclaw-oas",
)
BASE_CONTRACTS = (
    "provider_descriptor.v1",
    "session_attachment.v1",
    "inbox_binding.v1",
    "turn_delta.v1",
)


@lru_cache(maxsize=1)
def load_provider_packaging_known_limitations_matrix_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_provider_packaging_known_limitations_matrix(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_provider_packaging_known_limitations_matrix_schema(),
    )


def _safety() -> dict[str, bool]:
    return {
        "doc_committed": False,
        "raw_transcript_copied": False,
        "raw_session_copied": False,
        "global_inbox_created": False,
        "product_behavior_claimed": False,
        "provider_specific_contract_bypass": False,
        "phase5_memory_gates_weakened": False,
    }


def _deploy_target(provider_id: str) -> str | None:
    target = DEPLOY_TARGETS.get(provider_id)
    return target.as_posix() if target is not None else None


def _base_row(
    *,
    provider_id: str,
    provider_family: str,
    support_level: str,
    matrix_status: str,
    deploy_surface_status: str,
    deploy_target: str | None,
    packaging_contract_ref: str | None,
    provider_specific_smoke_status: str,
    failure_mode: str,
    clear_failure_instruction: str,
    operator_instruction: str,
    limitation_refs: list[str],
    extra_contracts: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "provider_family": provider_family,
        "support_level": support_level,
        "matrix_status": matrix_status,
        "deploy_surface_status": deploy_surface_status,
        "deploy_target": deploy_target,
        "packaging_contract_ref": packaging_contract_ref,
        "provider_specific_smoke_status": provider_specific_smoke_status,
        "failure_mode": failure_mode,
        "clear_failure_instruction": clear_failure_instruction,
        "operator_instruction": operator_instruction,
        "expected_contracts": list(BASE_CONTRACTS + extra_contracts),
        "limitation_refs": limitation_refs,
        "safety": _safety(),
    }


def build_provider_packaging_known_limitations_matrix(
    *,
    next_action: str = P6_CR1_ACTION,
) -> dict[str, Any]:
    rows = [
        _base_row(
            provider_id="hermes",
            provider_family="Hermes",
            support_level="supported",
            matrix_status="baseline_ready",
            deploy_surface_status="profile_skill_sync_available",
            deploy_target="~/.hermes/profiles/<provider_profile>/skills/autonomous-ai-agents/openyggdrasil-foreground-probe/SKILL.md",
            packaging_contract_ref="hermes_provider_packaging_baseline.v1",
            provider_specific_smoke_status="typed_unavailable",
            failure_mode="known_limitation",
            clear_failure_instruction=(
                "Hermes packaging may be used through the profile skill baseline, but live foreground must remain typed_unavailable until the provider harness foreground probe exists."
            ),
            operator_instruction=(
                "Use the Hermes profile skill sync path and treat live foreground as hermes_foreground_unavailable_contract.v1, not as proven foreground behavior."
            ),
            extra_contracts=("hermes_foreground_unavailable_contract.v1",),
            limitation_refs=[
                "contracts/hermes_provider_packaging_baseline.v1.schema.json",
                "contracts/hermes_foreground_unavailable_contract.v1.schema.json",
                "providers/hermes/projects/harness/hermes_foreground_probe.py missing",
            ],
        ),
        _base_row(
            provider_id="codex",
            provider_family="Codex",
            support_level="degraded",
            matrix_status="typed_degrade_ready",
            deploy_surface_status="provider_neutral_only",
            deploy_target=None,
            packaging_contract_ref="codex_provider_packaging_baseline.v1",
            provider_specific_smoke_status="passed",
            failure_mode="typed_degrade",
            clear_failure_instruction=(
                "Codex has no provider-native file deployment target; use provider-neutral attachment contracts and do not claim a Codex-native package."
            ),
            operator_instruction=(
                "Generate .yggdrasil/providers/codex/... through the shared provider/session contracts; deploy_skill.py intentionally rejects provider_ids=['codex']."
            ),
            extra_contracts=("codex_provider_packaging_baseline.v1",),
            limitation_refs=[
                "contracts/codex_provider_packaging_baseline.v1.schema.json",
                "runtime/attachments/deploy_skill.py has no codex target",
            ],
        ),
        _base_row(
            provider_id="claude-code",
            provider_family="Claude Code / Claude-compatible",
            support_level="supported",
            matrix_status="baseline_ready",
            deploy_surface_status="provider_native_file_target_available",
            deploy_target=_deploy_target("claude-code"),
            packaging_contract_ref="claude_code_provider_packaging_baseline.v1",
            provider_specific_smoke_status="passed",
            failure_mode="known_limitation",
            clear_failure_instruction=(
                "Claude Code packaging must remain clean-room and may not copy, vendor, translate, or mechanically port local Claude Code implementation source."
            ),
            operator_instruction=(
                "Use deploy_skill.py to generate .claude/skills/openyggdrasil/SKILL.md and keep product behavior claims out of the package baseline."
            ),
            extra_contracts=("claude_code_provider_packaging_baseline.v1",),
            limitation_refs=[
                "contracts/claude_code_provider_packaging_baseline.v1.schema.json",
                "providers/claude-code/README.md clean-room boundary",
            ],
        ),
        _base_row(
            provider_id="gemini-antigravity",
            provider_family="Gemini / Antigravity",
            support_level="supported",
            matrix_status="baseline_ready",
            deploy_surface_status="provider_native_file_target_available",
            deploy_target=_deploy_target("gemini"),
            packaging_contract_ref="antigravity_provider_packaging_baseline.v1",
            provider_specific_smoke_status="passed",
            failure_mode="known_limitation",
            clear_failure_instruction=(
                "Gemini / Antigravity packaging proves repo-owned GEMINI.md generation and Antigravity workspace scaffold only; it does not claim current product behavior."
            ),
            operator_instruction=(
                "Use deploy_skill.py for GEMINI.md and antigravity_router_bootstrap.py for .agents plus .yggdrasil/providers/antigravity/... scaffold."
            ),
            extra_contracts=("antigravity_provider_packaging_baseline.v1",),
            limitation_refs=[
                "contracts/antigravity_provider_packaging_baseline.v1.schema.json",
                "providers/antigravity/README.md product behavior boundary",
            ],
        ),
        _base_row(
            provider_id="windsurf",
            provider_family="Windsurf",
            support_level="limited",
            matrix_status="typed_limitations_only",
            deploy_surface_status="provider_native_file_target_available",
            deploy_target=_deploy_target("windsurf"),
            packaging_contract_ref=None,
            provider_specific_smoke_status="not_claimed",
            failure_mode="known_limitation",
            clear_failure_instruction=(
                "Windsurf has a generated file target but no provider-specific packaging baseline or smoke; treat it as limited until a dedicated baseline exists."
            ),
            operator_instruction=(
                "Use deploy_skill.py --providers windsurf only as a generated-file surface; require shared provider/session contracts before any memory claim."
            ),
            limitation_refs=[
                "runtime/attachments/deploy_skill.py windsurf target",
                "no contracts/windsurf_provider_packaging_baseline.v1.schema.json",
            ],
        ),
        _base_row(
            provider_id="cursor",
            provider_family="Cursor",
            support_level="limited",
            matrix_status="typed_limitations_only",
            deploy_surface_status="provider_native_file_target_available",
            deploy_target=_deploy_target("cursor"),
            packaging_contract_ref=None,
            provider_specific_smoke_status="not_claimed",
            failure_mode="known_limitation",
            clear_failure_instruction=(
                "Cursor has a generated rule target but no provider-specific packaging baseline or smoke; treat it as limited until a dedicated baseline exists."
            ),
            operator_instruction=(
                "Use deploy_skill.py --providers cursor only as a generated-rule surface; require shared provider/session contracts before any memory claim."
            ),
            limitation_refs=[
                "runtime/attachments/deploy_skill.py cursor target",
                "no contracts/cursor_provider_packaging_baseline.v1.schema.json",
            ],
        ),
        _base_row(
            provider_id="openclaw-oas",
            provider_family="OpenClaw / Open Agent Skills-compatible",
            support_level="unsupported",
            matrix_status="missing_surface_unsupported",
            deploy_surface_status="missing_surface",
            deploy_target=None,
            packaging_contract_ref=None,
            provider_specific_smoke_status="not_available",
            failure_mode="unsupported_missing_surface",
            clear_failure_instruction=(
                "OpenClaw / Open Agent Skills-compatible providers are unsupported in Phase 6 because no repo-owned deploy surface or provider packaging baseline exists."
            ),
            operator_instruction=(
                "Add a repo-owned provider deploy surface, a provider packaging baseline contract, and local attachment smoke before enabling this provider family."
            ),
            limitation_refs=[
                "no deploy_skill.py target for openclaw-oas",
                "no providers/openclaw-oas surface",
                "no Open Agent Skills-compatible provider baseline contract",
            ],
        ),
    ]
    baseline_ready_count = sum(row["matrix_status"] == "baseline_ready" for row in rows)
    unsupported_count = sum(row["support_level"] == "unsupported" for row in rows)
    degraded_or_limited_count = len(rows) - baseline_ready_count - unsupported_count
    payload = {
        "schema_version": "provider_packaging_known_limitations_matrix.v1",
        "matrix_id": uuid.uuid4().hex,
        "provider_order": list(PROVIDER_ORDER),
        "rows": rows,
        "matrix_summary": {
            "baseline_ready_count": baseline_ready_count,
            "degraded_or_limited_count": degraded_or_limited_count,
            "unsupported_count": unsupported_count,
            "official_doc_recheck_required": False,
            "phase_close_review_next": True,
        },
        "safety": _safety(),
        "next_action": next_action,
        "created_at": utc_now_iso(),
    }
    validate_provider_packaging_known_limitations_matrix(payload)
    return payload


def provider_packaging_row_by_id(matrix: Mapping[str, Any], provider_id: str) -> dict[str, Any]:
    for row in matrix.get("rows", []):
        if row.get("provider_id") == provider_id:
            return dict(row)
    raise KeyError(f"unknown provider packaging row: {provider_id}")
