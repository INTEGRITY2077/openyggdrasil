from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import jsonschema

from attachments.provider_attachment import provider_inbox_path
from attachments.provider_inbox import inject_session_packet, validate_inbox_packet
from delivery.mailbox_contamination_guard import MailboxGuardPolicy, ensure_mailbox_message_accepted
from harness_common import WORKSPACE_ROOT


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
SUPPORT_BUNDLE_SCHEMA_PATH = CONTRACTS_ROOT / "support_bundle.v1.schema.json"
SUPPORT_BUNDLE_SOURCE_PACKET_TYPES = (
    "graph_hint",
    "decision_candidate",
    "admission_verdict",
    "engraved_seed",
    "planting_decision",
    "cultivated_decision",
    "map_topography",
    "community_topography",
    "operator_brief",
)


@lru_cache(maxsize=1)
def load_support_bundle_schema() -> Dict[str, Any]:
    return json.loads(SUPPORT_BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_support_bundle(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(instance=dict(payload), schema=load_support_bundle_schema())


def validate_support_bundle_inbox_packet(packet: Mapping[str, Any]) -> None:
    validate_inbox_packet(packet)
    if packet.get("packet_type") != "support_bundle":
        raise ValueError("Expected packet_type='support_bundle'")
    validate_support_bundle(dict(packet.get("payload") or {}))


def _non_empty_strings(values: Iterable[Any]) -> list[str]:
    return [str(item).strip() for item in values if str(item).strip()]


def _workspace_relative_path(path_value: str, *, workspace_root: Path) -> str:
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path_value).replace("\\", "/")


def _normalize_paths(source_paths: Iterable[str], *, workspace_root: Path) -> list[str]:
    return [
        _workspace_relative_path(path_value, workspace_root=workspace_root)
        for path_value in _non_empty_strings(source_paths)
    ]


def _normalize_pathfinder_bundle(
    pathfinder_bundle: Mapping[str, Any],
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    normalized = dict(pathfinder_bundle)
    source_paths = normalized.get("source_paths")
    if isinstance(source_paths, list):
        normalized["source_paths"] = _normalize_paths(
            [str(item) for item in source_paths],
            workspace_root=workspace_root,
        )
    return normalized


def _first_matching_path(
    relative_source_paths: Iterable[str],
    *,
    prefixes: tuple[str, ...],
) -> str | None:
    for path_value in relative_source_paths:
        lowered = path_value.lower()
        if any(lowered.startswith(prefix.lower()) for prefix in prefixes):
            return path_value
    return None


def _load_runtime_support_registry(*, workspace_root: Path) -> list[dict[str, Any]]:
    registry_path = workspace_root / ".yggdrasil" / "ops" / "support-registry" / "support_truth.v1.json"
    if not registry_path.exists():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _select_support_overlay(
    *,
    query_text: str,
    source_paths: list[str],
    workspace_root: Path,
) -> dict[str, Any]:
    normalized_query = query_text.lower()
    normalized_paths = {
        _workspace_relative_path(path_value, workspace_root=workspace_root).lower()
        for path_value in source_paths
    }
    best_score = 0
    best_overlay: dict[str, Any] = {}
    for entry in _load_runtime_support_registry(workspace_root=workspace_root):
        score = 0
        canonical_note = str(entry.get("canonical_note") or "").strip().lower()
        has_source_paths = bool(normalized_paths)
        if has_source_paths:
            if canonical_note and canonical_note in normalized_paths:
                score += 5
            else:
                continue
        else:
            for term in entry.get("match_terms") or []:
                if str(term).strip().lower() in normalized_query:
                    score += 1
        if score > best_score:
            best_score = score
            overlay = entry.get("support_bundle")
            best_overlay = dict(overlay) if isinstance(overlay, dict) else {}
    return best_overlay


def build_support_bundle_payload(
    message: Mapping[str, Any],
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    ensure_mailbox_message_accepted(
        message,
        policy=MailboxGuardPolicy(
            allowed_message_types=SUPPORT_BUNDLE_SOURCE_PACKET_TYPES,
            require_delivery_match=False,
        ),
    )
    active_workspace = (workspace_root or WORKSPACE_ROOT).resolve()
    scope = dict(message.get("scope") or {})
    payload = dict(message.get("payload") or {})
    source_paths = [str(item) for item in payload.get("source_paths") or []]
    relative_source_paths = _normalize_paths(source_paths, workspace_root=active_workspace)
    query_text = str(payload.get("query_text") or scope.get("topic") or "").strip()
    pathfinder_bundle = _normalize_pathfinder_bundle(
        dict(payload.get("pathfinder_bundle") or {}),
        workspace_root=active_workspace,
    )
    facts = _non_empty_strings(payload.get("facts") or [])
    if not facts and pathfinder_bundle:
        facts = _non_empty_strings(pathfinder_bundle.get("support_facts") or [])
    bundle = {
        "schema_version": "support_bundle.v1",
        "source_packet_id": str(message.get("message_id") or ""),
        "source_packet_type": str(message.get("message_type") or ""),
        "query_text": query_text,
        "topic": str(scope.get("topic") or "") or None,
        "human_summary": str(message.get("human_summary") or "") or None,
        "facts": facts,
        "source_paths": relative_source_paths,
        "graph_freshness": dict(payload.get("graph_freshness") or {}),
        "pathfinder_bundle": pathfinder_bundle,
        "decision_key": None,
        "mailbox_location": None,
        "proof_token": None,
        "rationale_code": None,
        "canonical_note": _first_matching_path(
            relative_source_paths,
            prefixes=("vault/topics/", "vault/queries/"),
        ),
        "community_note": None,
        "provenance_note": _first_matching_path(
            relative_source_paths,
            prefixes=("vault/provenance/", "vault/_meta/provenance/"),
        ),
        "community_id": None,
        "source_ref": None,
    }
    overlay = _select_support_overlay(
        query_text=query_text,
        source_paths=source_paths,
        workspace_root=active_workspace,
    )
    for key, value in overlay.items():
        if key in bundle and bundle[key] in (None, "", [], {}):
            bundle[key] = value
    validate_support_bundle(bundle)
    return bundle


def deliver_session_support_packet(
    message: Mapping[str, Any],
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any] | None:
    scope = dict(message.get("scope") or {})
    provider_profile = str(scope.get("profile") or "").strip()
    provider_session_id = str(scope.get("session_id") or "").strip()
    if not provider_profile or not provider_session_id:
        return None
    provider_id = str(scope.get("provider_id") or "hermes").strip() or "hermes"
    active_workspace = (workspace_root or WORKSPACE_ROOT).resolve()
    payload = build_support_bundle_payload(message, workspace_root=active_workspace)
    packet = inject_session_packet(
        workspace_root=active_workspace,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
        packet_type="support_bundle",
        payload=payload,
    )
    validate_support_bundle_inbox_packet(packet)
    inbox_path = provider_inbox_path(
        workspace_root=active_workspace,
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "message_id": packet["message_id"],
        "inbox_path": str(inbox_path),
        "packet": packet,
    }
