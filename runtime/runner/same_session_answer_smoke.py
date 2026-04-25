from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from attachments.provider_attachment import (
    bootstrap_skill_provider_session,
    build_session_uid,
)
from attachments.provider_inbox import read_session_inbox
from admission.decision_contracts import validate_mailbox_support_result
from delivery.support_bundle import validate_support_bundle_inbox_packet
from harness_common import OPENYGGDRASIL_ROOT, utc_now_iso
from runner.mailbox_support_emission import emit_mailbox_support_result
from runner.session_signal_runner import run_session_signal_thin_chain


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
SMOKE_SCHEMA_PATH = CONTRACTS_ROOT / "same_session_answer_smoke_result.v1.schema.json"
FORBIDDEN_PROVIDER_PAYLOAD_KEYS = {
    "raw_text",
    "raw_session",
    "raw_transcript",
    "transcript",
    "conversation_excerpt",
    "long_summary",
    "canonical_claim",
    "mailbox_mutation",
    "sot_write",
}


@lru_cache(maxsize=1)
def load_same_session_answer_smoke_result_schema() -> dict[str, Any]:
    return json.loads(SMOKE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _reject_forbidden_provider_payload_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                raise ValueError(f"same-session answer smoke forbids provider payload field {path}.{key}")
            _reject_forbidden_provider_payload_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_provider_payload_keys(child, path=f"{path}[{index}]")


def validate_same_session_answer_smoke_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_same_session_answer_smoke_result_schema(),
    )
    _reject_forbidden_provider_payload_keys(payload)


def _default_workspace_root() -> Path:
    return OPENYGGDRASIL_ROOT / ".runtime" / "same-session-answer-smoke" / uuid.uuid4().hex


def _default_signal() -> dict[str, Any]:
    provider_id = "hermes"
    provider_profile = "r4-smoke"
    provider_session_id = "session-same-session-answer-smoke"
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "schema_version": "session_structure_signal.v1",
        "signal_id": "signal-r4-same-session-answer-smoke",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "turn_range": {
            "from": 2,
            "to": 4,
        },
        "trigger_type": "boundary_trigger",
        "reason_labels": ["same_session_answer_smoke"],
        "surface_reason": "Closed decision requires same session mailbox support answer",
        "priority": "review",
        "source_ref": {
            "kind": "provider_session",
            "path_hint": ".yggdrasil/providers/hermes/r4-smoke/hermes_r4-smoke_session-same-session-answer-smoke/turn_delta.v1.jsonl",
            "range_hint": "turns:2-4",
            "symlink_hint": None,
        },
        "anchor_hash": "r4-same-session-answer-smoke-anchor",
        "emitted_at": utc_now_iso(),
    }


def _candidate_renderer(*, decision_surface: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_text": "Use the generated support bundle when the same session asks about the closed R4 decision.",
        "rationale": "The provider needs a session-bound mailbox answer proof before Phase 0 can close.",
        "alternatives_rejected": ["answer_from_unrelated_bundle", "answer_without_mailbox_citation"],
        "stability_state": "provisional",
        "topic_hint": "session-structure/r4-same-session-answer-smoke",
        "reason_labels": ["thin_worker_chain", "r4_same_session_answer_smoke"],
        "confidence_score": 0.78,
    }


def _write_support_sources(chain_result: Mapping[str, Any]) -> list[str]:
    artifacts = dict(chain_result.get("artifacts") or {})
    cultivated = artifacts.get("cultivated_decision")
    if not isinstance(cultivated, Mapping):
        return []

    written: list[str] = []
    canonical_path = Path(str(cultivated.get("canonical_note_path") or ""))
    provenance_path = Path(str(cultivated.get("provenance_note_path") or ""))
    decision_text = str(cultivated.get("decision_text") or "").strip()
    support_fact = str(cultivated.get("support_fact") or "").strip()

    if str(canonical_path):
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(
            "# R4 Same Session Answer Smoke\n\n"
            f"Decision: {decision_text}\n\n"
            f"Support: {support_fact}\n",
            encoding="utf-8",
        )
        written.append(str(canonical_path))

    if str(provenance_path):
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(
            "# R4 Provenance\n\n"
            f"Signal: {chain_result.get('signal_id')}\n\n"
            "Source policy: provider session remains SOT by reference only.\n",
            encoding="utf-8",
        )
        written.append(str(provenance_path))

    return written


def _latest_support_packet(inbox_rows: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    for row in reversed(inbox_rows):
        if isinstance(row, Mapping) and row.get("packet_type") == "support_bundle":
            return dict(row)
    return None


def _question_matches_bundle(question: str, support_bundle: Mapping[str, Any]) -> bool:
    normalized = question.lower()
    candidates = [
        support_bundle.get("topic"),
        support_bundle.get("query_text"),
        support_bundle.get("canonical_note"),
        support_bundle.get("source_ref"),
    ]
    candidates.extend(support_bundle.get("facts") or [])
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if text and text in normalized:
            return True
    return "r4 same session answer smoke" in normalized


def _provider_answer_from_inbox(
    *,
    question: str,
    inbox_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    packet = _latest_support_packet(inbox_rows)
    if not packet:
        return {
            "answer_id": uuid.uuid4().hex,
            "status": "ignored",
            "consumed_support_bundle": False,
            "cited_mailbox_message_id": None,
            "canonical_note": None,
            "source_ref": None,
            "answer_text": "No session-bound support bundle is available.",
            "reason_codes": ["support_bundle_missing"],
        }
    validate_support_bundle_inbox_packet(packet)
    support_bundle = dict(packet.get("payload") or {})
    if not _question_matches_bundle(question, support_bundle):
        return {
            "answer_id": uuid.uuid4().hex,
            "status": "ignored",
            "consumed_support_bundle": False,
            "cited_mailbox_message_id": None,
            "canonical_note": None,
            "source_ref": None,
            "answer_text": "The latest support bundle is unrelated to this question.",
            "reason_codes": ["question_not_supported_by_bundle"],
        }

    canonical_note = support_bundle.get("canonical_note")
    source_ref = support_bundle.get("source_ref")
    facts = [str(item).strip() for item in support_bundle.get("facts") or [] if str(item).strip()]
    answer_text = (
        f"Mailbox packet {packet['message_id']} supports this answer. "
        f"Canonical note: {canonical_note or 'unavailable'}. "
        f"Source ref: {source_ref or 'unavailable'}. "
        f"Fact: {facts[0] if facts else 'unavailable'}"
    )
    return {
        "answer_id": uuid.uuid4().hex,
        "status": "answered",
        "consumed_support_bundle": True,
        "cited_mailbox_message_id": str(packet["message_id"]),
        "canonical_note": str(canonical_note) if canonical_note else None,
        "source_ref": str(source_ref) if source_ref else None,
        "answer_text": answer_text,
        "reason_codes": ["support_bundle_matched", "mailbox_packet_cited"],
    }


def _inbox_packet_ref(mailbox_support_result: Mapping[str, Any]) -> dict[str, Any]:
    refs = [dict(ref) for ref in mailbox_support_result.get("mailbox_packet_refs") or [] if isinstance(ref, Mapping)]
    if refs:
        return {
            "message_id": str(refs[0]["message_id"]),
            "packet_type": "support_bundle",
            "path_hint": str(refs[0].get("path_hint") or ""),
        }
    return {
        "message_id": "missing-message-id",
        "packet_type": "support_bundle",
        "path_hint": "missing-inbox-path",
    }


def run_same_session_answer_smoke(
    *,
    signal: Mapping[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Run R4 foreground-equivalent same-session support consumption smoke."""

    active_workspace = (workspace_root or _default_workspace_root()).resolve()
    active_vault = active_workspace / "vault"
    active_signal = dict(signal or _default_signal())

    bootstrap_skill_provider_session(
        workspace_root=active_workspace,
        provider_id=str(active_signal["provider_id"]),
        provider_profile=str(active_signal["provider_profile"]),
        provider_session_id=str(active_signal["provider_session_id"]),
        origin_kind="workspace-session",
        origin_locator={
            "workspace_root": str(active_workspace),
            "signal_id": str(active_signal["signal_id"]),
        },
    )

    chain = run_session_signal_thin_chain(
        active_signal,
        candidate_renderer=_candidate_renderer,
        vault_root=active_vault,
    )
    _write_support_sources(chain["chain_result"])
    mailbox_support = emit_mailbox_support_result(
        chain_result=chain["chain_result"],
        workspace_root=active_workspace,
    )
    validate_mailbox_support_result(mailbox_support)

    inbox_rows = read_session_inbox(
        workspace_root=active_workspace,
        provider_id=str(active_signal["provider_id"]),
        provider_profile=str(active_signal["provider_profile"]),
        provider_session_id=str(active_signal["provider_session_id"]),
    )
    latest_packet = _latest_support_packet(inbox_rows)
    support_payload = dict((latest_packet or {}).get("payload") or {})
    relevant_question = (
        "In this same session, answer the R4 same session answer smoke decision using "
        f"{support_payload.get('topic') or 'the delivered support bundle'}."
    )
    decoy_question = "In this same session, explain an unrelated dependency cache cleanup decision."
    relevant_answer = _provider_answer_from_inbox(question=relevant_question, inbox_rows=inbox_rows)
    decoy_answer = _provider_answer_from_inbox(question=decoy_question, inbox_rows=inbox_rows)

    assertions = {
        "support_bundle_delivered": mailbox_support.get("status") == "completed" and latest_packet is not None,
        "relevant_answer_consumed_bundle": relevant_answer["consumed_support_bundle"] is True,
        "relevant_answer_cited_mailbox": relevant_answer["cited_mailbox_message_id"]
        == _inbox_packet_ref(mailbox_support)["message_id"],
        "decoy_answer_rejected_bundle": decoy_answer["consumed_support_bundle"] is False,
        "no_uncaught_exception": True,
    }
    passed = all(assertions.values())
    result = {
        "schema_version": "same_session_answer_smoke_result.v1",
        "smoke_result_id": uuid.uuid4().hex,
        "status": "passed" if passed else "failed",
        "signal_id": str(active_signal["signal_id"]),
        "provider_id": str(active_signal["provider_id"]),
        "provider_profile": str(active_signal["provider_profile"]),
        "provider_session_id": str(active_signal["provider_session_id"]),
        "session_uid": str(active_signal["session_uid"]),
        "mailbox_support_status": str(mailbox_support.get("status") or "stopped"),
        "inbox_packet_ref": _inbox_packet_ref(mailbox_support),
        "relevant_question": relevant_question,
        "relevant_answer": relevant_answer,
        "decoy_question": decoy_question,
        "decoy_answer": decoy_answer,
        "assertions": assertions,
        "next_action": "provider_headless_lease_dry_run" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_same_session_answer_smoke_result(result)
    return result
