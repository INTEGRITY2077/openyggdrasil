from __future__ import annotations

import json
import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from capture.provider_current_source_bridge import (
    build_memory_ticket_payload_from_current_source,
    build_provider_current_source_bridge,
)
from delivery.postman_live_delivery import submit_live_delivery
from runtime.operator.producer import run_producer
from source_ref.hermes_session_json import resolve_hermes_session_json_source_ref


def _bridge(tmp_path: Path) -> dict:
    return build_provider_current_source_bridge(
        provider_id="hermes",
        provider_profile="openyggdrasil-provider",
        provider_session_id="ygg-pro1-proof",
        final_answer_text=(
            "Provider finalization memory action now has a current-source bridge. "
            "Use it only for durable planning-loop boundaries and keep OP1 storage "
            "completion separate from prepare_OP1."
        ),
        sessions_dir=tmp_path / "sessions",
        created_at="2026-05-07T11:30:00+00:00",
    )


def _ticket(current_source: dict) -> dict:
    return build_memory_ticket_payload_from_current_source(
        current_source=current_source,
        surface_reason="Provider current-source bridge closes the source_ref/range/hash/watermark blocker.",
        intent_field=(
            "Provider may prepare OP1 only after its final answer is captured as a bounded current source "
            "with source_ref, message range, anchor_hash, and commit watermark."
        ),
        why_not_atomic=(
            "Splitting this into field-only atoms would lose the behavioral boundary between prepare_OP1 "
            "and verified storage completion."
        ),
        topic_hint="Provider current-source MemoryTicket bridge",
        category_community_hint="OpenYggdrasil provider behavior contract / memory authoring bridge",
        decision="Provider current-source bridge supplies MemoryTicket source fields before OP1 preparation.",
        context="The previous finalization memory action gate blocked OP1 because current-source fields were missing.",
        conclusion="The bridge can now prepare a schema-valid MemoryTicket payload without claiming OP1 storage completion.",
        trigger_kind="reusable_operational_rule",
        breadcrumb="Use current-source bridge before prepare_OP1 for Provider-authored final answers.",
        reuse_condition="Future Worker2 finalization gates need OP1 storage preparation from Provider-authored answers.",
    )


def test_current_source_bridge_emits_portable_provider_card_and_resolvable_source(tmp_path: Path) -> None:
    current_source = _bridge(tmp_path)

    assert current_source["status"] == "ready"
    assert current_source["current_source_ready"] is True
    provider_card = current_source["provider_visible_card"]
    assert provider_card["source_ref"] == "hermes-session-json://ygg-pro1-proof"
    assert provider_card["message_index_range"] == {"start": 0, "end": 0}
    assert provider_card["commit_watermark"] == "session:ygg-pro1-proof:message_index:0"
    assert len(provider_card["anchor_hash"]) == 64
    assert "sessions_dir" not in json.dumps(provider_card)
    assert "\\" not in json.dumps(provider_card)

    resolved = resolve_hermes_session_json_source_ref(
        source_ref=provider_card["source_ref"],
        message_index_range=provider_card["message_index_range"],
        sessions_dir=tmp_path / "sessions",
        anchor_hash=provider_card["anchor_hash"],
    )
    assert resolved["status"] == "resolved"
    assert resolved["redaction_status"] == "pointer_only"
    assert resolved["commit_watermark"] == provider_card["commit_watermark"]


def test_current_source_bridge_fails_closed_without_final_answer_text(tmp_path: Path) -> None:
    current_source = build_provider_current_source_bridge(
        provider_id="hermes",
        provider_profile="openyggdrasil-provider",
        provider_session_id="ygg-pro1-proof",
        final_answer_text="",
        sessions_dir=tmp_path / "sessions",
    )

    assert current_source["status"] == "typed_unavailable"
    assert current_source["current_source_ready"] is False
    assert current_source["reason_code"] == "final_answer_text_missing"
    assert current_source["hard_nonclaims"]["op1_storage_passed"] is False


def test_current_source_memory_ticket_reaches_op1_producer_with_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    current_source = _bridge(tmp_path)
    payload = _ticket(current_source)

    delivery = submit_live_delivery(
        recipient="OP1",
        message_type="memory_ticket",
        payload=payload,
        provider_id="hermes-dev",
        mail_id="memticket-current-source-bridge-proof",
    )
    mailbox = Path(delivery["mailbox"])
    vault = tmp_path / "vault"
    run_producer(mailbox, vault)

    receipts = [
        json.loads(line)
        for line in (mailbox / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    receipt = receipts[-1]
    assert receipt["in_reply_to"] == "memticket-current-source-bridge-proof"
    assert receipt["status"] == "acknowledged"
    assert receipt["intent"] == "memory_ticket"
    assert receipt["produced_count"] == 1
    assert receipt["source_ref_status"] == "resolved"
    assert receipt["support_bundle_seed"]["source_paths"]
    assert payload["source_ref"] == "hermes-session-json://ygg-pro1-proof"
