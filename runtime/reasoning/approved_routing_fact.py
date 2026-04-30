from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from harness_common import utc_now_iso


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
HERMES_RECEIPT_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT / "contracts" / "hermes_routing_receipt.v1.schema.json"
)

APPROVED_FACT_SCHEMA_VERSION = "approved_routing_fact.v1"
HERMES_RECEIPT_SCHEMA_VERSION = "hermes_routing_receipt.v1"
SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s]+$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
EFFORT_LEVELS = {"none", "low", "medium", "high", "xhigh"}
LEASE_GROUPS = {"deep_reasoning", "semantic_routing", "deterministic"}
EVIDENCE_KINDS = {
    "approved_routing_fact",
    "pathfinder_trace",
    "ptc_trace",
    "support_bundle",
    "route_decision",
}
FORBIDDEN_TEXT_TOKENS = (
    "---\nname:",
    "```",
    ".skill.md",
    "<instructions>",
)
FORBIDDEN_REF_TOKENS = (
    "file://",
    "d:/",
    "d:\\",
    "c:/",
    "c:\\",
    ".skill.md",
    "transcript.txt",
    "transcripts/",
    "auth.json",
    ".env",
)


@lru_cache(maxsize=1)
def load_hermes_routing_receipt_schema() -> dict[str, Any]:
    return json.loads(HERMES_RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_hermes_routing_receipt(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_hermes_routing_receipt_schema(),
    )


def _token(value: Any, *, length: int = 32) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _identifier(value: Any, *, field_name: str, prefix: str | None = None) -> str:
    text = str(value or "").strip()
    if prefix and not text:
        text = f"{prefix}-{_token(value)}"
    if not text:
        raise ValueError(f"{field_name} is required")
    if len(text) > 128 or not IDENTIFIER_RE.match(text):
        if prefix is None:
            raise ValueError(f"{field_name} must be a safe identifier")
        text = f"{prefix}-{_token(text)}"
    return text


def _safe_ref(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    lowered = text.lower().replace("\\", "/")
    if not SAFE_REF_RE.match(text):
        raise ValueError(f"{field_name} must be a provider-safe ref")
    if any(token.replace("\\", "/") in lowered for token in FORBIDDEN_REF_TOKENS):
        raise ValueError(f"{field_name} contains unsafe provider material")
    return text


def _provider_safe_text(value: Any, *, field_name: str) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        raise ValueError(f"{field_name} is required")
    lowered = text.lower().replace("\\", "/")
    if any(token in lowered for token in FORBIDDEN_TEXT_TOKENS):
        raise ValueError(f"{field_name} contains raw provider or skill material")
    return text[:600]


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_memory_refs(value: Any, *, field_name: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a list")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw_row in enumerate(value):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"{field_name}[{index}] must be an object")
        row = {
            "ref": _safe_ref(raw_row.get("ref"), field_name=f"{field_name}[{index}].ref"),
            "role": _identifier(raw_row.get("role"), field_name=f"{field_name}[{index}].role"),
            "reason_code": _identifier(
                raw_row.get("reason_code"),
                field_name=f"{field_name}[{index}].reason_code",
            ),
        }
        dedup_key = (row["ref"], row["role"], row["reason_code"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        rows.append(row)
    return rows


def _normalize_evidence_refs(value: Any, *, field_name: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a list")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_row in enumerate(value):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"{field_name}[{index}] must be an object")
        evidence_kind = str(raw_row.get("evidence_kind") or "").strip()
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"{field_name}[{index}].evidence_kind is unsupported")
        row = {
            "evidence_id": _identifier(
                raw_row.get("evidence_id"),
                field_name=f"{field_name}[{index}].evidence_id",
            ),
            "ref": _safe_ref(raw_row.get("ref"), field_name=f"{field_name}[{index}].ref"),
            "evidence_kind": evidence_kind,
            "pointer_accounting_key": _identifier(
                raw_row.get("pointer_accounting_key"),
                field_name=f"{field_name}[{index}].pointer_accounting_key",
            ),
        }
        dedup_key = (row["evidence_kind"], row["ref"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        rows.append(row)
    return rows


def _ensure_evidence_ref(
    rows: list[dict[str, str]],
    *,
    evidence_id_prefix: str,
    ref: str,
    evidence_kind: str,
    pointer_accounting_key: str,
) -> None:
    if any(row["evidence_kind"] == evidence_kind and row["ref"] == ref for row in rows):
        return
    rows.append(
        {
            "evidence_id": _identifier(
                f"{evidence_id_prefix}-{_token(ref, length=16)}",
                field_name=f"{evidence_kind}.evidence_id",
            ),
            "ref": _safe_ref(ref, field_name=f"{evidence_kind}.ref"),
            "evidence_kind": evidence_kind,
            "pointer_accounting_key": _identifier(
                pointer_accounting_key,
                field_name=f"{evidence_kind}.pointer_accounting_key",
            ),
        }
    )


def build_approved_routing_fact_from_ptc_trace(
    ptc_trace: Mapping[str, Any],
    *,
    approved_at: str | None = None,
) -> dict[str, Any]:
    """Build the runtime-owned fact that Hermes may consume through a receipt."""

    trace = dict(ptc_trace)
    route_id = _identifier(trace.get("route_id"), field_name="route_id", prefix="route")
    approved_routing_fact_ref = _safe_ref(
        trace.get("approved_routing_fact_ref")
        or f"approved-routing-fact-ref://openyggdrasil/pathfinder/{route_id}",
        field_name="approved_routing_fact_ref",
    )
    query_ref = _safe_ref(trace.get("query_ref"), field_name="query_ref")
    support_bundle_ref = _safe_ref(trace.get("support_bundle_ref"), field_name="support_bundle_ref")
    ptc_trace_ref = _safe_ref(trace.get("ptc_trace_ref"), field_name="ptc_trace_ref")
    approved_effort = str(trace.get("approved_effort") or "high").strip()
    lease_group = str(trace.get("lease_group") or "semantic_routing").strip()
    if approved_effort not in EFFORT_LEVELS:
        raise ValueError("approved_effort is unsupported")
    if lease_group not in LEASE_GROUPS:
        raise ValueError("lease_group is unsupported")

    selected_memory_refs = _normalize_memory_refs(
        trace.get("selected_memory_refs"),
        field_name="selected_memory_refs",
    ) or [
        {
            "ref": support_bundle_ref,
            "role": "support_bundle_source",
            "reason_code": "runtime_approved_route",
        }
    ]
    rejected_memory_refs = _normalize_memory_refs(
        trace.get("rejected_memory_refs"),
        field_name="rejected_memory_refs",
    )
    evidence_refs = _normalize_evidence_refs(trace.get("evidence_refs"), field_name="evidence_refs")
    _ensure_evidence_ref(
        evidence_refs,
        evidence_id_prefix="ptc-trace",
        ref=ptc_trace_ref,
        evidence_kind="ptc_trace",
        pointer_accounting_key="ptc_trace_ref",
    )
    _ensure_evidence_ref(
        evidence_refs,
        evidence_id_prefix="approved-routing-fact",
        ref=approved_routing_fact_ref,
        evidence_kind="approved_routing_fact",
        pointer_accounting_key="approved_routing_fact_ref",
    )

    reason_codes = _unique(
        [
            *(str(code) for code in trace.get("reason_codes") or []),
            "runtime_authoritative_route",
            "approved_routing_fact_projected_from_ptc_trace",
        ]
    )
    return {
        "schema_version": APPROVED_FACT_SCHEMA_VERSION,
        "route_id": route_id,
        "approved_routing_fact_ref": approved_routing_fact_ref,
        "query_ref": query_ref,
        "support_bundle_ref": support_bundle_ref,
        "ptc_trace_ref": ptc_trace_ref,
        "runtime_authoritative": True,
        "approved_effort": approved_effort,
        "lease_group": lease_group,
        "route_summary": _provider_safe_text(
            trace.get("provider_route_summary")
            or trace.get("route_summary")
            or "Use the runtime-approved Pathfinder support bundle route with provenance refs.",
            field_name="route_summary",
        ),
        "selected_memory_refs": selected_memory_refs,
        "rejected_memory_refs": rejected_memory_refs,
        "evidence_refs": evidence_refs,
        "reason_codes": reason_codes,
        "approved_at": approved_at or str(trace.get("generated_at") or utc_now_iso()),
    }


def build_hermes_routing_receipt(
    approved_routing_fact: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    fact = dict(approved_routing_fact)
    if fact.get("schema_version") != APPROVED_FACT_SCHEMA_VERSION:
        raise ValueError("approved_routing_fact schema_version is required")
    if fact.get("runtime_authoritative") is not True:
        raise ValueError("approved_routing_fact.runtime_authoritative must be true")

    route_id = _identifier(fact.get("route_id"), field_name="route_id")
    approved_routing_fact_ref = _safe_ref(
        fact.get("approved_routing_fact_ref"),
        field_name="approved_routing_fact_ref",
    )
    query_ref = _safe_ref(fact.get("query_ref"), field_name="query_ref")
    support_bundle_ref = _safe_ref(fact.get("support_bundle_ref"), field_name="support_bundle_ref")
    ptc_trace_ref = _safe_ref(fact.get("ptc_trace_ref"), field_name="ptc_trace_ref")
    approved_effort = str(fact.get("approved_effort") or "").strip()
    lease_group = str(fact.get("lease_group") or "").strip()
    if approved_effort not in EFFORT_LEVELS:
        raise ValueError("approved_effort is unsupported")
    if lease_group not in LEASE_GROUPS:
        raise ValueError("lease_group is unsupported")

    selected_memory_refs = _normalize_memory_refs(
        fact.get("selected_memory_refs"),
        field_name="selected_memory_refs",
    )
    if not selected_memory_refs:
        selected_memory_refs = [
            {
                "ref": support_bundle_ref,
                "role": "support_bundle_source",
                "reason_code": "runtime_approved_route",
            }
        ]
    rejected_memory_refs = _normalize_memory_refs(
        fact.get("rejected_memory_refs"),
        field_name="rejected_memory_refs",
    )
    evidence_refs = _normalize_evidence_refs(fact.get("evidence_refs"), field_name="evidence_refs")
    _ensure_evidence_ref(
        evidence_refs,
        evidence_id_prefix="ptc-trace",
        ref=ptc_trace_ref,
        evidence_kind="ptc_trace",
        pointer_accounting_key="ptc_trace_ref",
    )
    _ensure_evidence_ref(
        evidence_refs,
        evidence_id_prefix="approved-routing-fact",
        ref=approved_routing_fact_ref,
        evidence_kind="approved_routing_fact",
        pointer_accounting_key="approved_routing_fact_ref",
    )

    reason_codes = _unique(
        [
            *(str(code) for code in fact.get("reason_codes") or []),
            "skill_body_excluded",
            "provider_safe_refs_only",
            "advisory_metadata_not_authoritative",
        ]
    )
    receipt = {
        "schema_version": HERMES_RECEIPT_SCHEMA_VERSION,
        "receipt_id": _identifier(
            fact.get("receipt_id") or f"receipt-{route_id}",
            field_name="receipt_id",
            prefix="receipt",
        ),
        "route_id": route_id,
        "approved_routing_fact_ref": approved_routing_fact_ref,
        "query_ref": query_ref,
        "support_bundle_ref": support_bundle_ref,
        "ptc_trace_ref": ptc_trace_ref,
        "runtime_authoritative": True,
        "approved_effort": approved_effort,
        "lease_group": lease_group,
        "provider_route_summary": _provider_safe_text(
            fact.get("route_summary") or fact.get("provider_route_summary"),
            field_name="provider_route_summary",
        ),
        "selected_memory_refs": selected_memory_refs,
        "rejected_memory_refs": rejected_memory_refs,
        "evidence_refs": evidence_refs,
        "skill_body_included": False,
        "raw_provider_material_included": False,
        "portable_local_path_included": False,
        "advisory_metadata_lowered_effort": False,
        "live_readiness_claimed": False,
        "production_readiness_claimed": False,
        "reasoning_lease_solved_claimed": False,
        "target_readiness_claimed": False,
        "reason_codes": reason_codes,
        "generated_at": generated_at or str(fact.get("approved_at") or utc_now_iso()),
    }
    validate_hermes_routing_receipt(receipt)
    return receipt


__all__ = [
    "APPROVED_FACT_SCHEMA_VERSION",
    "HERMES_RECEIPT_SCHEMA_VERSION",
    "build_approved_routing_fact_from_ptc_trace",
    "build_hermes_routing_receipt",
    "load_hermes_routing_receipt_schema",
    "validate_hermes_routing_receipt",
]
