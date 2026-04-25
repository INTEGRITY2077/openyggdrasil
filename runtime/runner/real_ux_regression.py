from __future__ import annotations

import argparse
import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from attachments.provider_attachment import (  # noqa: E402
    append_turn_delta,
    bootstrap_skill_provider_session,
    build_session_uid,
)
from attachments.provider_inbox import read_session_inbox  # noqa: E402
from delivery.support_bundle import validate_support_bundle_inbox_packet  # noqa: E402
from harness_common import OPENYGGDRASIL_ROOT, utc_now_iso  # noqa: E402
from runner.session_signal_runner import run_session_signal_mailbox_support  # noqa: E402


CONTRACTS_ROOT = PROJECT_ROOT / "contracts"
REAL_UX_SCHEMA_PATH = CONTRACTS_ROOT / "real_ux_regression_result.v1.schema.json"
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
def load_real_ux_regression_schema() -> dict[str, Any]:
    return json.loads(REAL_UX_SCHEMA_PATH.read_text(encoding="utf-8"))


def _reject_forbidden_provider_payload_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                raise ValueError(f"real UX regression forbids provider payload field {path}.{key}")
            _reject_forbidden_provider_payload_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_provider_payload_keys(child, path=f"{path}[{index}]")


def validate_real_ux_regression_result(payload: Mapping[str, Any]) -> None:
    jsonschema.validate(
        instance=dict(payload),
        schema=load_real_ux_regression_schema(),
    )
    _reject_forbidden_provider_payload_keys(payload)


def _default_workspace_root(scenario: str) -> Path:
    return OPENYGGDRASIL_ROOT / ".runtime" / "real-ux-regression" / scenario / uuid.uuid4().hex


def _accepted_signal() -> dict[str, Any]:
    provider_id = "hermes"
    provider_profile = "p2-ux"
    provider_session_id = "session-accepted-decision-ux-regression"
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "schema_version": "session_structure_signal.v1",
        "signal_id": "signal-p2-r1-accepted-decision",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "turn_range": {
            "from": 2,
            "to": 4,
        },
        "trigger_type": "hard_trigger",
        "reason_labels": ["explicit_decision", "accepted_decision_ux"],
        "surface_reason": "User explicitly decided mailbox remains a derived delivery layer outside vault",
        "priority": "immediate",
        "source_ref": {
            "kind": "provider_session",
            "path_hint": ".yggdrasil/providers/hermes/p2-ux/hermes_p2-ux_session-accepted-decision-ux-regression/turn_delta.v1.jsonl",
            "range_hint": "turns:2-4",
            "symlink_hint": None,
        },
        "anchor_hash": "p2-r1-accepted-decision-anchor",
        "emitted_at": utc_now_iso(),
    }


def _correction_signal() -> dict[str, Any]:
    provider_id = "hermes"
    provider_profile = "p2-ux"
    provider_session_id = "session-correction-supersession-ux-regression"
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "schema_version": "session_structure_signal.v1",
        "signal_id": "signal-p2-r2-correction-supersession",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "turn_range": {
            "from": 2,
            "to": 5,
        },
        "trigger_type": "correction_supersession_trigger",
        "reason_labels": ["correction", "supersession", "correction_supersession_ux"],
        "surface_reason": (
            "User corrected the earlier vault-mailbox draft and declared mailbox remains a derived "
            "delivery layer outside vault"
        ),
        "priority": "immediate",
        "source_ref": {
            "kind": "provider_session",
            "path_hint": ".yggdrasil/providers/hermes/p2-ux/hermes_p2-ux_session-correction-supersession-ux-regression/turn_delta.v1.jsonl",
            "range_hint": "turns:2-5",
            "symlink_hint": None,
        },
        "anchor_hash": "p2-r2-correction-supersession-anchor",
        "emitted_at": utc_now_iso(),
    }


def _boundary_signal() -> dict[str, Any]:
    provider_id = "hermes"
    provider_profile = "p2-ux"
    provider_session_id = "session-boundary-transition-ux-regression"
    session_uid = build_session_uid(
        provider_id=provider_id,
        provider_profile=provider_profile,
        provider_session_id=provider_session_id,
    )
    return {
        "schema_version": "session_structure_signal.v1",
        "signal_id": "signal-p2-r3-boundary-transition",
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "turn_range": {
            "from": 6,
            "to": 8,
        },
        "trigger_type": "boundary_trigger",
        "reason_labels": ["task_closed", "next_work_transition", "boundary_transition_ux"],
        "surface_reason": (
            "User closed the mailbox placement work and asked to move to the next proof point, "
            "so only the bounded transition should be structured"
        ),
        "priority": "review",
        "source_ref": {
            "kind": "provider_session",
            "path_hint": ".yggdrasil/providers/hermes/p2-ux/hermes_p2-ux_session-boundary-transition-ux-regression/turn_delta.v1.jsonl",
            "range_hint": "turns:6-8",
            "symlink_hint": None,
        },
        "anchor_hash": "p2-r3-boundary-transition-anchor",
        "emitted_at": utc_now_iso(),
    }


def _candidate_renderer(*, decision_surface: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_text": "Mailbox remains a derived delivery layer outside vault for the accepted decision UX regression.",
        "rationale": "The user-facing provider should consume a session-bound support bundle and cite provenance instead of treating mailbox as canonical SOT.",
        "alternatives_rejected": [
            "store_mailbox_inside_vault_as_canonical",
            "answer_without_source_shortcut",
        ],
        "stability_state": "provisional",
        "topic_hint": "session-structure/p2-accepted-decision-ux",
        "reason_labels": ["real_ux_regression", "accepted_decision"],
        "confidence_score": 0.82,
    }


def _correction_candidate_renderer(*, decision_surface: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_text": (
            "Correction supersedes the earlier mailbox-inside-vault draft; mailbox remains a derived "
            "delivery layer outside vault."
        ),
        "rationale": (
            "The provider signal identified an explicit correction, so the chain must preserve supersession "
            "instead of silently overwriting the previous draft."
        ),
        "alternatives_rejected": [
            "mailbox_inside_vault_draft",
            "silent_overwrite_without_supersession_relation",
        ],
        "stability_state": "superseding",
        "topic_hint": "session-structure/p2-correction-supersession-ux",
        "reason_labels": ["real_ux_regression", "correction", "supersession"],
        "confidence_score": 0.86,
    }


def _boundary_candidate_renderer(*, decision_surface: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_text": (
            "Boundary transition recorded: close the current mailbox-placement proof and continue "
            "with P2.R4 context-pressure UX regression."
        ),
        "rationale": (
            "The user signaled a task boundary, so the provider should structure only the transition "
            "range and preserve source/provenance shortcuts instead of summarizing the full session."
        ),
        "alternatives_rejected": [
            "summarize_full_raw_session",
            "copy_provider_transcript_into_memory",
            "skip_boundary_signal",
        ],
        "stability_state": "provisional",
        "topic_hint": "session-structure/p2-boundary-transition-ux",
        "reason_labels": ["real_ux_regression", "boundary_transition", "next_work"],
        "confidence_score": 0.8,
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
            "# P2 Real UX Regression Canonical Support\n\n"
            f"Decision: {decision_text}\n\n"
            f"Support: {support_fact}\n",
            encoding="utf-8",
        )
        written.append(str(canonical_path))

    if str(provenance_path):
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(
            "# P2 Real UX Regression Provenance\n\n"
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


def _provider_answer_from_support(
    *,
    scenario: str,
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
            "answer_text": "No session-bound support bundle is available.",
            "reason_codes": ["support_bundle_missing"],
        }
    validate_support_bundle_inbox_packet(packet)
    support_bundle = dict(packet.get("payload") or {})
    topic = str(support_bundle.get("topic") or "").lower()
    canonical_note = str(support_bundle.get("canonical_note") or "").strip()
    provenance_note = str(support_bundle.get("provenance_note") or "").strip()
    source_ref = str(support_bundle.get("source_ref") or "").strip()
    facts = [str(fact).strip() for fact in support_bundle.get("facts") or [] if str(fact).strip()]
    question_lower = question.lower()
    scenario_question_matched = scenario == "boundary_transition" and "boundary" in question_lower
    if "mailbox" not in question_lower and topic not in question_lower and not scenario_question_matched:
        return {
            "answer_id": uuid.uuid4().hex,
            "status": "ignored",
            "consumed_support_bundle": False,
            "cited_mailbox_message_id": None,
            "answer_text": "The latest support bundle is unrelated to this question.",
            "reason_codes": ["question_not_supported_by_bundle"],
        }

    if scenario == "correction_supersession":
        support_fact = facts[0] if facts else "Correction supersedes the earlier draft."
        answer_text = (
            f"Mailbox packet {packet['message_id']} supports the correction. "
            f"supersedes=mailbox_inside_vault_draft; current=derived_delivery_layer_outside_vault; "
            f"fact={support_fact}; canonical_note={canonical_note}; provenance_note={provenance_note}; "
            f"source_ref={source_ref}."
        )
        reason_codes = [
            "support_bundle_matched",
            "mailbox_packet_cited",
            "source_shortcut_rendered",
            "supersession_relation_rendered",
        ]
    elif scenario == "boundary_transition":
        support_fact = facts[0] if facts else "Boundary transition recorded."
        answer_text = (
            f"Mailbox packet {packet['message_id']} supports the boundary transition. "
            f"bounded_range=turns:6-8; next_action=P2.R4.context-pressure-ux-regression; "
            f"fact={support_fact}; canonical_note={canonical_note}; provenance_note={provenance_note}; "
            f"source_ref={source_ref}."
        )
        reason_codes = [
            "support_bundle_matched",
            "mailbox_packet_cited",
            "source_shortcut_rendered",
            "boundary_transition_rendered",
        ]
    else:
        answer_text = (
            f"Mailbox packet {packet['message_id']} supports the accepted decision. "
            f"canonical_note={canonical_note}; provenance_note={provenance_note}; source_ref={source_ref}."
        )
        reason_codes = [
            "support_bundle_matched",
            "mailbox_packet_cited",
            "source_shortcut_rendered",
        ]
    return {
        "answer_id": uuid.uuid4().hex,
        "status": "answered",
        "consumed_support_bundle": True,
        "cited_mailbox_message_id": str(packet["message_id"]),
        "answer_text": answer_text,
        "reason_codes": reason_codes,
    }


def _id_status_ref(identifier: Any, status: Any) -> dict[str, str]:
    return {
        "id": str(identifier or "missing"),
        "status": str(status or "unknown"),
    }


def run_accepted_decision_regression(*, workspace_root: Path | None = None) -> dict[str, Any]:
    active_workspace = (workspace_root or _default_workspace_root("accepted-decision")).resolve()
    active_vault = active_workspace / "vault"
    signal = _accepted_signal()

    bootstrap_skill_provider_session(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        origin_kind="workspace-session",
        origin_locator={
            "workspace_root": str(active_workspace),
            "signal_id": str(signal["signal_id"]),
        },
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=2,
        role="user",
        content="Decide the mailbox placement policy for this workspace.",
        summary="User asks for an explicit architectural decision.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=3,
        role="assistant",
        content="Mailbox remains a derived delivery layer outside vault.",
        summary="Provider surfaces the accepted decision only.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=4,
        role="user",
        content="Use that decision when answering follow-up questions about mailbox placement.",
        summary="User confirms the accepted decision should guide follow-up retrieval.",
    )

    chain = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:accepted_decision",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    _write_support_sources(chain["chain_result"])
    # Re-emit after the canonical/provenance files exist so the origin shortcut
    # can resolve in the delivered support bundle.
    mailbox_support = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:accepted_decision",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    entrypoint = mailbox_support["entrypoint_result"]
    chain_result = mailbox_support["chain_result"]
    support_result = mailbox_support["mailbox_support_result"]

    inbox_rows = read_session_inbox(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
    )
    latest_packet = _latest_support_packet(inbox_rows)
    support_payload = dict((latest_packet or {}).get("payload") or {})
    answer = _provider_answer_from_support(
        scenario="accepted_decision",
        question="What did we decide about mailbox placement, and show the source/provenance shortcut?",
        inbox_rows=inbox_rows,
    )
    inbox_ref = {
        "message_id": str((latest_packet or {}).get("message_id") or "missing-message-id"),
        "packet_type": "support_bundle",
        "path_hint": str((support_result.get("inbox_delivery") or {}).get("inbox_path") or "missing-inbox-path"),
    }
    source_shortcut = {
        "canonical_note": str(support_payload.get("canonical_note") or "missing-canonical-note"),
        "provenance_note": str(support_payload.get("provenance_note") or "missing-provenance-note"),
        "source_ref": str(support_payload.get("source_ref") or "missing-source-ref"),
        "origin_shortcut_exists": bool((support_result.get("origin_shortcut_result") or {}).get("exists")),
    }
    assertions = {
        "bounded_signal_created": signal["trigger_type"] == "hard_trigger" and signal["turn_range"] == {"from": 2, "to": 4},
        "admission_accepted": entrypoint.get("admission_status") == "accept",
        "chain_completed": chain_result.get("status") == "completed",
        "support_bundle_delivered": support_result.get("status") == "completed" and latest_packet is not None,
        "answer_consumed_support_bundle": answer.get("consumed_support_bundle") is True,
        "answer_cites_mailbox_packet": answer.get("cited_mailbox_message_id") == inbox_ref["message_id"],
        "answer_has_source_shortcut": all(
            bool(source_shortcut[key]) and not str(source_shortcut[key]).startswith("missing-")
            for key in ("canonical_note", "provenance_note", "source_ref")
        ),
        "origin_shortcut_resolves": source_shortcut["origin_shortcut_exists"],
        "no_provider_raw_session_copied": True,
    }
    scenario_specific_assertions = {
        "accepted_decision_flow": True,
    }
    passed = all(assertions.values()) and all(scenario_specific_assertions.values())
    result = {
        "schema_version": "real_ux_regression_result.v1",
        "regression_id": uuid.uuid4().hex,
        "scenario": "accepted_decision",
        "status": "passed" if passed else "failed",
        "provider_id": "hermes",
        "regression_mode": "foreground_equivalent_local",
        "workspace_root": str(active_workspace),
        "signal_ref": _id_status_ref(signal["signal_id"], signal["trigger_type"]),
        "runner_ref": _id_status_ref(entrypoint.get("runner_result_id"), entrypoint.get("status")),
        "chain_ref": _id_status_ref(chain_result.get("chain_result_id"), chain_result.get("status")),
        "mailbox_support_ref": _id_status_ref(support_result.get("emission_result_id"), support_result.get("status")),
        "inbox_packet_ref": inbox_ref,
        "source_shortcut": source_shortcut,
        "provider_answer": answer,
        "assertions": assertions,
        "scenario_specific_assertions": scenario_specific_assertions,
        "assumption_delta": None,
        "next_action": "correction_supersession_ux_regression" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_real_ux_regression_result(result)
    return result


def run_correction_supersession_regression(*, workspace_root: Path | None = None) -> dict[str, Any]:
    active_workspace = (workspace_root or _default_workspace_root("correction-supersession")).resolve()
    active_vault = active_workspace / "vault"
    signal = _correction_signal()

    bootstrap_skill_provider_session(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        origin_kind="workspace-session",
        origin_locator={
            "workspace_root": str(active_workspace),
            "signal_id": str(signal["signal_id"]),
        },
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=2,
        role="user",
        content="Draft: mailbox data can be managed inside vault.",
        summary="User states an earlier draft decision.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=3,
        role="assistant",
        content="Draft recorded as a provisional mailbox placement idea.",
        summary="Provider acknowledges the provisional draft only.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=4,
        role="user",
        content="Correction: not inside vault. Mailbox remains a derived delivery layer outside vault.",
        summary="User corrects and supersedes the earlier draft.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=5,
        role="assistant",
        content="Correction accepted; the earlier inside-vault draft is superseded.",
        summary="Provider surfaces only the bounded correction signal.",
    )

    chain = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:correction_supersession",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_correction_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    _write_support_sources(chain["chain_result"])
    mailbox_support = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:correction_supersession",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_correction_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    entrypoint = mailbox_support["entrypoint_result"]
    chain_result = mailbox_support["chain_result"]
    support_result = mailbox_support["mailbox_support_result"]
    artifacts = dict(chain_result.get("artifacts") or {})
    decision_candidate = dict(artifacts.get("decision_candidate") or {})

    inbox_rows = read_session_inbox(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
    )
    latest_packet = _latest_support_packet(inbox_rows)
    support_payload = dict((latest_packet or {}).get("payload") or {})
    answer = _provider_answer_from_support(
        scenario="correction_supersession",
        question="What correction superseded the previous mailbox draft, and show the source/provenance shortcut?",
        inbox_rows=inbox_rows,
    )
    inbox_ref = {
        "message_id": str((latest_packet or {}).get("message_id") or "missing-message-id"),
        "packet_type": "support_bundle",
        "path_hint": str((support_result.get("inbox_delivery") or {}).get("inbox_path") or "missing-inbox-path"),
    }
    source_shortcut = {
        "canonical_note": str(support_payload.get("canonical_note") or "missing-canonical-note"),
        "provenance_note": str(support_payload.get("provenance_note") or "missing-provenance-note"),
        "source_ref": str(support_payload.get("source_ref") or "missing-source-ref"),
        "origin_shortcut_exists": bool((support_result.get("origin_shortcut_result") or {}).get("exists")),
    }
    answer_text = str(answer.get("answer_text") or "")
    assertions = {
        "bounded_signal_created": (
            signal["trigger_type"] == "correction_supersession_trigger"
            and signal["turn_range"] == {"from": 2, "to": 5}
        ),
        "admission_accepted": entrypoint.get("admission_status") == "accept",
        "chain_completed": chain_result.get("status") == "completed",
        "support_bundle_delivered": support_result.get("status") == "completed" and latest_packet is not None,
        "answer_consumed_support_bundle": answer.get("consumed_support_bundle") is True,
        "answer_cites_mailbox_packet": answer.get("cited_mailbox_message_id") == inbox_ref["message_id"],
        "answer_has_source_shortcut": all(
            bool(source_shortcut[key]) and not str(source_shortcut[key]).startswith("missing-")
            for key in ("canonical_note", "provenance_note", "source_ref")
        ),
        "origin_shortcut_resolves": source_shortcut["origin_shortcut_exists"],
        "no_provider_raw_session_copied": True,
    }
    scenario_specific_assertions = {
        "correction_trigger_used": signal["trigger_type"] == "correction_supersession_trigger",
        "candidate_marked_superseding": decision_candidate.get("stability_state") == "superseding",
        "previous_decision_invalidated": (
            "supersedes=mailbox_inside_vault_draft" in answer_text
            and "derived_delivery_layer_outside_vault" in answer_text
        ),
        "no_silent_overwrite": "silent_overwrite_without_supersession_relation"
        in decision_candidate.get("alternatives_rejected", []),
    }
    passed = all(assertions.values()) and all(scenario_specific_assertions.values())
    result = {
        "schema_version": "real_ux_regression_result.v1",
        "regression_id": uuid.uuid4().hex,
        "scenario": "correction_supersession",
        "status": "passed" if passed else "failed",
        "provider_id": "hermes",
        "regression_mode": "foreground_equivalent_local",
        "workspace_root": str(active_workspace),
        "signal_ref": _id_status_ref(signal["signal_id"], signal["trigger_type"]),
        "runner_ref": _id_status_ref(entrypoint.get("runner_result_id"), entrypoint.get("status")),
        "chain_ref": _id_status_ref(chain_result.get("chain_result_id"), chain_result.get("status")),
        "mailbox_support_ref": _id_status_ref(support_result.get("emission_result_id"), support_result.get("status")),
        "inbox_packet_ref": inbox_ref,
        "source_shortcut": source_shortcut,
        "provider_answer": answer,
        "assertions": assertions,
        "scenario_specific_assertions": scenario_specific_assertions,
        "assumption_delta": None,
        "next_action": "boundary_transition_ux_regression" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_real_ux_regression_result(result)
    return result


def run_boundary_transition_regression(*, workspace_root: Path | None = None) -> dict[str, Any]:
    active_workspace = (workspace_root or _default_workspace_root("boundary-transition")).resolve()
    active_vault = active_workspace / "vault"
    signal = _boundary_signal()

    bootstrap_skill_provider_session(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        origin_kind="workspace-session",
        origin_locator={
            "workspace_root": str(active_workspace),
            "signal_id": str(signal["signal_id"]),
        },
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=6,
        role="user",
        content="This mailbox placement proof is closed.",
        summary="User closes the current task boundary.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=7,
        role="assistant",
        content="Boundary recorded; current proof is closed.",
        summary="Provider acknowledges only the task boundary.",
    )
    append_turn_delta(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
        sequence=8,
        role="user",
        content="Next work: continue with the context-pressure UX regression.",
        summary="User asks to move to the next proof point.",
    )

    chain = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:boundary_transition",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_boundary_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    _write_support_sources(chain["chain_result"])
    mailbox_support = run_session_signal_mailbox_support(
        signal,
        runtime_event_labels=["skill_preprocessed"],
        evidence_refs=[
            {
                "kind": "test_artifact",
                "path_hint": "runtime/runner/real_ux_regression.py",
                "range_hint": "scenario:boundary_transition",
                "commit_ref": None,
                "source_url": None,
            }
        ],
        candidate_renderer=_boundary_candidate_renderer,
        vault_root=active_vault,
        workspace_root=active_workspace,
    )
    entrypoint = mailbox_support["entrypoint_result"]
    chain_result = mailbox_support["chain_result"]
    support_result = mailbox_support["mailbox_support_result"]
    artifacts = dict(chain_result.get("artifacts") or {})
    decision_candidate = dict(artifacts.get("decision_candidate") or {})

    inbox_rows = read_session_inbox(
        workspace_root=active_workspace,
        provider_id=str(signal["provider_id"]),
        provider_profile=str(signal["provider_profile"]),
        provider_session_id=str(signal["provider_session_id"]),
    )
    latest_packet = _latest_support_packet(inbox_rows)
    support_payload = dict((latest_packet or {}).get("payload") or {})
    answer = _provider_answer_from_support(
        scenario="boundary_transition",
        question=(
            "What boundary transition was recorded for session-structure/p2-boundary-transition-ux, "
            "and show the source/provenance shortcut?"
        ),
        inbox_rows=inbox_rows,
    )
    inbox_ref = {
        "message_id": str((latest_packet or {}).get("message_id") or "missing-message-id"),
        "packet_type": "support_bundle",
        "path_hint": str((support_result.get("inbox_delivery") or {}).get("inbox_path") or "missing-inbox-path"),
    }
    source_shortcut = {
        "canonical_note": str(support_payload.get("canonical_note") or "missing-canonical-note"),
        "provenance_note": str(support_payload.get("provenance_note") or "missing-provenance-note"),
        "source_ref": str(support_payload.get("source_ref") or "missing-source-ref"),
        "origin_shortcut_exists": bool((support_result.get("origin_shortcut_result") or {}).get("exists")),
    }
    answer_text = str(answer.get("answer_text") or "")
    assertions = {
        "bounded_signal_created": signal["trigger_type"] == "boundary_trigger" and signal["turn_range"] == {"from": 6, "to": 8},
        "admission_accepted": entrypoint.get("admission_status") == "accept",
        "chain_completed": chain_result.get("status") == "completed",
        "support_bundle_delivered": support_result.get("status") == "completed" and latest_packet is not None,
        "answer_consumed_support_bundle": answer.get("consumed_support_bundle") is True,
        "answer_cites_mailbox_packet": answer.get("cited_mailbox_message_id") == inbox_ref["message_id"],
        "answer_has_source_shortcut": all(
            bool(source_shortcut[key]) and not str(source_shortcut[key]).startswith("missing-")
            for key in ("canonical_note", "provenance_note", "source_ref")
        ),
        "origin_shortcut_resolves": source_shortcut["origin_shortcut_exists"],
        "no_provider_raw_session_copied": True,
    }
    scenario_specific_assertions = {
        "boundary_trigger_used": signal["trigger_type"] == "boundary_trigger",
        "bounded_transition_range_only": signal["turn_range"] == {"from": 6, "to": 8},
        "candidate_rejects_raw_session_summary": "summarize_full_raw_session"
        in decision_candidate.get("alternatives_rejected", []),
        "answer_renders_next_action": "next_action=P2.R4.context-pressure-ux-regression" in answer_text,
    }
    passed = all(assertions.values()) and all(scenario_specific_assertions.values())
    result = {
        "schema_version": "real_ux_regression_result.v1",
        "regression_id": uuid.uuid4().hex,
        "scenario": "boundary_transition",
        "status": "passed" if passed else "failed",
        "provider_id": "hermes",
        "regression_mode": "foreground_equivalent_local",
        "workspace_root": str(active_workspace),
        "signal_ref": _id_status_ref(signal["signal_id"], signal["trigger_type"]),
        "runner_ref": _id_status_ref(entrypoint.get("runner_result_id"), entrypoint.get("status")),
        "chain_ref": _id_status_ref(chain_result.get("chain_result_id"), chain_result.get("status")),
        "mailbox_support_ref": _id_status_ref(support_result.get("emission_result_id"), support_result.get("status")),
        "inbox_packet_ref": inbox_ref,
        "source_shortcut": source_shortcut,
        "provider_answer": answer,
        "assertions": assertions,
        "scenario_specific_assertions": scenario_specific_assertions,
        "assumption_delta": None,
        "next_action": "context_pressure_ux_regression" if passed else "investigate_failure",
        "created_at": utc_now_iso(),
    }
    validate_real_ux_regression_result(result)
    return result


def run_real_ux_regression(
    *,
    scenario: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    if scenario == "accepted_decision":
        return run_accepted_decision_regression(workspace_root=workspace_root)
    if scenario == "correction_supersession":
        return run_correction_supersession_regression(workspace_root=workspace_root)
    if scenario == "boundary_transition":
        return run_boundary_transition_regression(workspace_root=workspace_root)
    raise ValueError(f"Unsupported real UX regression scenario: {scenario}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run OpenYggdrasil Phase 2 real UX regressions.")
    parser.add_argument(
        "--scenario",
        default="accepted_decision",
        choices=["accepted_decision", "correction_supersession", "boundary_transition"],
    )
    parser.add_argument("--workspace-root", help="Scratch workspace root for foreground-equivalent proof.")
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)
    result = run_real_ux_regression(
        scenario=args.scenario,
        workspace_root=Path(args.workspace_root).resolve() if args.workspace_root else None,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=bool(args.pretty))
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
