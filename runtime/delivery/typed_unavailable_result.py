from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = OPENYGGDRASIL_ROOT / "contracts"
TYPED_UNAVAILABLE_SCHEMA = "typed_unavailable.v1.schema.json"

SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s]+$")
FORBIDDEN_REF_TOKENS = (
    "file://",
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    ".skill.md",
    "transcript.txt",
)
NO_OVERCLAIM_BOUNDARY = {
    "live_readiness_claimed": False,
    "production_readiness_claimed": False,
    "reasoning_lease_solved_claimed": False,
    "public_runtime_integration_complete_claimed": False,
    "readiness_91_percent_claimed": False,
}
DEFAULT_UNAVAILABLE_REF = "typed-unavailable-ref://openyggdrasil/delivery/unavailable-001"


@lru_cache(maxsize=1)
def _load_typed_unavailable_schema() -> dict[str, Any]:
    return json.loads((CONTRACTS_ROOT / TYPED_UNAVAILABLE_SCHEMA).read_text(encoding="utf-8"))


def validate_typed_unavailable(payload: Mapping[str, Any]) -> None:
    schema = _load_typed_unavailable_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        dict(payload)
    )


def _safe_ref(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower().replace("\\", "/")
    if not text or not SAFE_REF_RE.match(text):
        raise ValueError(f"{field_name} must be a safe ref")
    if any(token.replace("\\", "/").lower() in lowered for token in FORBIDDEN_REF_TOKENS):
        raise ValueError(f"{field_name} contains unsafe material")
    return text


def _typed_unavailable_ref(ref: str, reason_code: str, rejection_kind: str) -> dict[str, str]:
    return {
        "ref": _safe_ref(ref, field_name="missing_or_rejected_ref.ref"),
        "reason_code": reason_code,
        "rejection_kind": rejection_kind,
    }


def _fallback_unavailable_ref(reason_code: str, blocked_stage: str) -> str:
    token = hashlib.sha256(f"{reason_code}:{blocked_stage}".encode("utf-8")).hexdigest()[:16]
    return f"typed-unavailable-ref://openyggdrasil/delivery/{token}"


def build_typed_unavailable(
    *,
    reason_code: str,
    blocked_stage: str,
    missing_or_rejected_refs: Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
    unavailable_ref: str | None = None,
) -> dict[str, Any]:
    rows = []
    for raw in missing_or_rejected_refs or ():
        rows.append(
            _typed_unavailable_ref(
                str(raw.get("ref") or DEFAULT_UNAVAILABLE_REF),
                str(raw.get("reason_code") or reason_code),
                str(raw.get("rejection_kind") or "missing"),
            )
        )
    payload = {
        "schema_version": "typed_unavailable.v1",
        "unavailable_ref": _safe_ref(
            unavailable_ref or _fallback_unavailable_ref(reason_code, blocked_stage),
            field_name="unavailable_ref",
        ),
        "created_at": created_at or utc_now_iso(),
        "reason_code": reason_code,
        "blocked_stage": blocked_stage,
        "missing_or_rejected_refs": rows,
        "raw_provider_material_included": False,
        "skill_body_included": False,
        "portable_local_path_included": False,
        "fabricated_answer": False,
        "no_overclaim_boundary": dict(NO_OVERCLAIM_BOUNDARY),
    }
    validate_typed_unavailable(payload)
    return payload


__all__ = ["build_typed_unavailable", "validate_typed_unavailable"]
