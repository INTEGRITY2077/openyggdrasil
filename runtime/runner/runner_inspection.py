from __future__ import annotations

import argparse
import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
INSPECTION_SCHEMA_PATH = CONTRACTS_ROOT / "runner_inspection_summary.v1.schema.json"
FORBIDDEN_INPUT_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "summary",
    "canonical_claim",
    "canonical_path",
    "mailbox_mutation",
    "sot_write",
}
FORBIDDEN_OUTPUT_KEYS = {
    *FORBIDDEN_INPUT_KEYS,
    "answer_text",
    "decision_text",
    "facts",
    "human_summary",
    "query_text",
    "rationale",
    "support_fact",
    "surface_reason",
}


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@lru_cache(maxsize=1)
def load_runner_inspection_summary_schema() -> dict[str, Any]:
    return json.loads(INSPECTION_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_runner_inspection_summary(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_runner_inspection_summary_schema())
    _reject_forbidden_provider_payload_keys(payload, forbidden_keys=FORBIDDEN_OUTPUT_KEYS)


def _reject_forbidden_provider_payload_keys(
    value: Any,
    *,
    forbidden_keys: set[str],
    path: str = "$",
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in forbidden_keys:
                raise ValueError(f"runner inspection forbids provider payload field {path}.{key}")
            _reject_forbidden_provider_payload_keys(child, forbidden_keys=forbidden_keys, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_provider_payload_keys(child, forbidden_keys=forbidden_keys, path=f"{path}[{index}]")


def _first_mapping(payload: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _first_string(payloads: Iterable[Mapping[str, Any]], key: str) -> str | None:
    for payload in payloads:
        value = _string_or_none(payload.get(key))
        if value:
            return value
    return None


def _sanitize_status_rows(rows: Any, *, allowed_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return sanitized
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = {key: row.get(key) for key in allowed_keys if key in row}
        reason_codes = clean.get("reason_codes")
        if isinstance(reason_codes, list):
            clean["reason_codes"] = [str(item) for item in reason_codes if str(item).strip()]
        sanitized.append(clean)
    return sanitized


def _safe_refs(*payloads: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        for ref in payload.get(key) or []:
            if not isinstance(ref, Mapping):
                continue
            clean = {str(k): v for k, v in dict(ref).items() if str(k) in {"kind", "path_hint", "range_hint", "symlink_hint", "message_id", "packet_type"}}
            fingerprint = json.dumps(clean, ensure_ascii=False, sort_keys=True)
            if fingerprint not in seen:
                refs.append(clean)
                seen.add(fingerprint)
    return refs


def _merge_fallback_state(*payloads: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    fallback_used = False
    quarantine = False
    reasons: list[str] = []
    for label, payload in zip(("entrypoint", "chain", "mailbox_support"), payloads):
        state = payload.get("fallback_state")
        if not isinstance(state, Mapping):
            continue
        used = bool(state.get("fallback_used"))
        fallback_used = fallback_used or used
        quarantine = quarantine or bool(state.get("quarantine"))
        reason = _string_or_none(state.get("fallback_reason"))
        if reason and reason not in reasons:
            reasons.append(reason)
        rows.append(
            {
                "scope": label,
                "fallback_used": used,
                "fallback_reason": reason,
                "quarantine": bool(state.get("quarantine")),
            }
        )
    return {
        "fallback_used": fallback_used,
        "fallback_reasons": reasons,
        "quarantine": quarantine,
        "by_scope": rows,
    }


def _support_bundle_shortcuts(mailbox_support: Mapping[str, Any]) -> dict[str, Any]:
    bundle = mailbox_support.get("support_bundle")
    if not isinstance(bundle, Mapping):
        return {
            "canonical_note": None,
            "provenance_note": None,
            "source_ref": None,
            "source_paths": [],
        }
    return {
        "canonical_note": _string_or_none(bundle.get("canonical_note")),
        "provenance_note": _string_or_none(bundle.get("provenance_note")),
        "source_ref": _string_or_none(bundle.get("source_ref")),
        "source_paths": [str(item) for item in bundle.get("source_paths") or [] if str(item).strip()],
    }


def _source_ref_resolution(entrypoint: Mapping[str, Any]) -> dict[str, Any] | None:
    admission = entrypoint.get("admission_verdict")
    if not isinstance(admission, Mapping):
        return None
    resolution = admission.get("source_ref_resolution")
    return dict(resolution) if isinstance(resolution, Mapping) else None


def _delivery_status(mailbox_support: Mapping[str, Any]) -> str | None:
    inbox_delivery = mailbox_support.get("inbox_delivery")
    if not isinstance(inbox_delivery, Mapping):
        return None
    return _string_or_none(inbox_delivery.get("delivery_status"))


def _inbox_delivery(mailbox_support: Mapping[str, Any]) -> dict[str, Any] | None:
    inbox_delivery = mailbox_support.get("inbox_delivery")
    if not isinstance(inbox_delivery, Mapping):
        return None
    return {
        "delivery_status": _string_or_none(inbox_delivery.get("delivery_status")),
        "message_id": _string_or_none(inbox_delivery.get("message_id")),
        "inbox_path": _string_or_none(inbox_delivery.get("inbox_path")),
        "dedup_fingerprint": _string_or_none(inbox_delivery.get("dedup_fingerprint")),
    }


def _origin_shortcut(mailbox_support: Mapping[str, Any]) -> dict[str, Any] | None:
    origin = mailbox_support.get("origin_shortcut_result")
    if not isinstance(origin, Mapping):
        return None
    return {
        "shortcut_kind": _string_or_none(origin.get("shortcut_kind")),
        "shortcut_path": _string_or_none(origin.get("shortcut_path")),
        "resolved_path": _string_or_none(origin.get("resolved_path")),
        "exists": bool(origin.get("exists")),
    }


def _overall_status(*payloads: Mapping[str, Any]) -> str:
    statuses = [_string_or_none(payload.get("status")) for payload in payloads if payload]
    if any(status == "stopped" for status in statuses):
        return "stopped"
    if statuses and all(status in {"completed", "runner_plan_ready"} for status in statuses):
        return "completed"
    return "unknown"


def inspect_runner_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize runner output without exposing provider raw/session text."""

    _reject_forbidden_provider_payload_keys(payload, forbidden_keys=FORBIDDEN_INPUT_KEYS)
    entrypoint = _first_mapping(payload, ("entrypoint_result", "runner_result"))
    chain = _first_mapping(payload, ("chain_result", "thin_worker_chain_result"))
    mailbox_support = _first_mapping(payload, ("mailbox_support_result", "support_result"))
    payloads = [entrypoint, chain, mailbox_support]
    summary = {
        "schema_version": "runner_inspection_summary.v1",
        "inspection_id": uuid.uuid4().hex,
        "status": _overall_status(entrypoint, chain, mailbox_support),
        "signal_id": _first_string(payloads, "signal_id"),
        "provider_id": _first_string(payloads, "provider_id"),
        "provider_profile": _first_string(payloads, "provider_profile"),
        "provider_session_id": _first_string(payloads, "provider_session_id"),
        "session_uid": _first_string(payloads, "session_uid"),
        "step_statuses": _sanitize_status_rows(
            entrypoint.get("step_statuses"),
            allowed_keys=("step", "status", "reason_codes"),
        ),
        "role_steps": _sanitize_status_rows(
            chain.get("role_steps"),
            allowed_keys=("role", "status", "artifact_kind", "artifact_id", "reason_codes"),
        ),
        "fallback_state": _merge_fallback_state(entrypoint, chain, mailbox_support),
        "source_refs": _safe_refs(entrypoint, chain, mailbox_support, key="source_refs"),
        "mailbox_packet_refs": _safe_refs(entrypoint, chain, mailbox_support, key="mailbox_packet_refs"),
        "support_bundle_shortcuts": _support_bundle_shortcuts(mailbox_support),
        "source_ref_resolution": _source_ref_resolution(entrypoint),
        "delivery_status": _delivery_status(mailbox_support),
        "inbox_delivery": _inbox_delivery(mailbox_support),
        "origin_shortcut": _origin_shortcut(mailbox_support),
        "next_action": _first_string((mailbox_support, chain, entrypoint), "next_action"),
        "created_at": utc_now_iso(),
    }
    validate_runner_inspection_summary(summary)
    return summary


def _load_input(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect OpenYggdrasil runner output without provider raw text.")
    parser.add_argument("--input", "-i", required=True, help="Runner result JSON path, or '-' for stdin.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)
    try:
        summary = inspect_runner_output(_load_input(args.input))
    except Exception as exc:
        error = {
            "schema_version": "runner_inspection_error.v1",
            "status": "rejected",
            "reason_code": f"runner_inspection_failed:{exc.__class__.__name__}",
            "message": str(exc),
        }
        print(json.dumps(error, ensure_ascii=False, indent=2 if args.pretty else None), file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=bool(args.pretty)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
