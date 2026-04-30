from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
PERSONAS_ROOT = OPENYGGDRASIL_ROOT / "personas"
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
SCHEMA_VERSION = "subagent_persona_manifest.v1"
SCHEMA_PATH = CONTRACTS_ROOT / f"{SCHEMA_VERSION}.schema.json"

ROLE_PERSONA_FILES = {
    "distiller": "PERSONA_DISTILLER.md",
    "evaluator": "PERSONA_EVALUATOR.md",
    "amundsen": "PERSONA_AMUNDSEN.md",
    "pathfinder": "PERSONA_PATHFINDER.md",
    "postman": "PERSONA_POSTMAN.md",
    "map_maker": "PERSONA_MAP_MAKER.md",
}

REQUIRED_SECTIONS = (
    "Identity",
    "Use this when",
    "Do not use this when",
    "If ambiguous",
    "Typed unavailable when",
    "Required evidence refs",
    "Hard nonclaims",
    "Planning Phase",
    "Self-Check",
    "Self-Review",
    "Input Contract",
    "Output Contract",
    "Gotchas",
    "Forbidden Claims",
)

GLOBAL_HARD_NONCLAIMS = (
    "Reasoning Lease solved",
    "R10 Hermes subagent bridge complete",
    "live readiness",
    "production readiness",
    "production PTC implemented",
    "public runtime integration complete",
    "background live integration",
    "Hermes answer quality",
    "consumer UX complete",
    "full product readiness",
)

WEAKENING_TOKENS = (
    "override global",
    "weaken global",
    "remove global",
    "ignore global",
    "relax global",
    "waive global",
    "claim reasoning lease solved",
    "claim live readiness",
    "claim production readiness",
    "claim full product readiness",
)


def _normalize_role(role: Any) -> str:
    return str(role or "").strip().lower().replace("-", "_").replace(" ", "_")


def _persona_ref(role: str) -> str:
    return f"persona-ref://openyggdrasil/{role}/v1"


def _read_persona(filename: str) -> str:
    return (PERSONAS_ROOT / filename).read_text(encoding="utf-8")


def _markdown_sections(markdown: str) -> set[str]:
    return {
        match.group(1).strip()
        for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown)
    }


def _missing_required_sections(markdown: str) -> list[str]:
    sections = _markdown_sections(markdown)
    return [section for section in REQUIRED_SECTIONS if section not in sections]


def _string_list(values: Sequence[str] | None) -> list[str]:
    if values is None:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _assert_additive_only_packet_nonclaims(packet_hard_nonclaims: Sequence[str]) -> None:
    normalized = "\n".join(packet_hard_nonclaims).lower()
    for token in WEAKENING_TOKENS:
        if token in normalized:
            raise ValueError("packet_hard_nonclaims must not weaken global_hard_nonclaims")


@lru_cache(maxsize=1)
def load_subagent_persona_manifest_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_subagent_persona_manifest(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_subagent_persona_manifest_schema(),
    )
    if payload["missing_sections"]:
        raise ValueError("persona manifest has missing required sections")
    if payload["additive_only_hard_nonclaims"] is not True:
        raise ValueError("hard nonclaims must be additive-only")
    _assert_additive_only_packet_nonclaims(payload["packet_hard_nonclaims"])


def build_subagent_persona_manifest(
    *,
    role: str,
    packet_hard_nonclaims: Sequence[str] | None = None,
) -> dict[str, Any]:
    normalized_role = _normalize_role(role)
    if normalized_role not in ROLE_PERSONA_FILES:
        raise ValueError(f"unknown subagent persona role: {role}")

    common_text = _read_persona("PERSONA_COMMON.md")
    role_text = _read_persona(ROLE_PERSONA_FILES[normalized_role])
    prompt_surface = "\n\n".join(
        [
            "# OpenYggdrasil Subagent Persona Surface",
            "## Common Persona",
            common_text,
            "## Role Persona",
            role_text,
        ]
    )
    missing_sections = sorted(
        set(_missing_required_sections(common_text))
        | set(_missing_required_sections(role_text))
    )
    packet_nonclaims = _string_list(packet_hard_nonclaims)
    _assert_additive_only_packet_nonclaims(packet_nonclaims)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": f"persona-manifest:{uuid.uuid4().hex}",
        "role": normalized_role,
        "common_persona_ref": _persona_ref("common"),
        "role_persona_ref": _persona_ref(normalized_role),
        "required_sections": list(REQUIRED_SECTIONS),
        "missing_sections": missing_sections,
        "prompt_surface": prompt_surface,
        "global_hard_nonclaims": list(GLOBAL_HARD_NONCLAIMS),
        "packet_hard_nonclaims": packet_nonclaims,
        "additive_only_hard_nonclaims": True,
        "runtime_owner": "runtime/reasoning/persona_loader.py",
        "reason_codes": [
            "subagent_persona_manifest_built",
            "schema_validates_persona_persuades_runtime_enforces",
            f"role:{normalized_role}",
        ],
        "created_at": utc_now_iso(),
    }
    validate_subagent_persona_manifest(payload)
    return payload
