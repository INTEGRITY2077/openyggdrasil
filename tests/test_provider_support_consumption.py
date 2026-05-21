from __future__ import annotations

import json

import pytest


def _cpr_result() -> dict:
    return {
        "schema_version": "ygg_provider_cpr_inbox_read.v1",
        "status": "done",
        "provider_id": "hermes",
        "provider_profile": "openyggdrasil-provider",
        "provider_session_id": "ygg-pro1",
        "message_id": "msg-support-001",
        "handoff_status": "ready_for_provider_current_dialogue",
        "manual_prompt_injection_required": False,
        "mailbox_correlation": {
            "mail_id": "ask-support-001",
            "receipt_id": "receipt-support-001",
        },
        "mf1_support_metadata": {
            "status": "available",
            "support_facts_count": 2,
            "source_paths_count": 2,
            "typed_unavailable_present": False,
        },
    }


def test_provider_support_consumption_receipt_passes_for_route_free_support() -> None:
    from runtime.reasoning.provider_support_consumption import (
        build_provider_support_consumption_receipt,
        validate_provider_support_consumption_receipt,
    )

    receipt = build_provider_support_consumption_receipt(
        run_id="provider-natural-boundary-001",
        cpr_read_result=_cpr_result(),
        answer_segment="Agent runtime role and plugin distribution location are separate boundaries.",
        support_packet_ref="oy-support://provider-natural-boundary-001/cpr/msg-support-001",
        answer_segment_ref="oy-pane://provider-natural-boundary-001/answer/lines-41-65",
        answer_support_alignment="enough_with_limits",
    )

    validate_provider_support_consumption_receipt(receipt)
    assert receipt["status"] == "consumed"
    assert receipt["route_free_consumption_proven"] is True
    assert receipt["route_free_surface"]["visible_route_notice_present"] is False
    assert receipt["route_free_surface"]["visible_cpr_command_used"] is False
    assert receipt["production_readiness_claimed"] is False
    assert receipt["full_ux_passed"] is False
    assert "production readiness" in " ".join(receipt["hard_nonclaims"]).lower()


@pytest.mark.parametrize(
    "answer_segment,reason_code",
    [
        (
            "OpenYggdrasil result arrived. Provider-bound brief says run ygg cpr.",
            "visible_route_or_internal_marker_present",
        ),
        ("", "answer_segment_missing"),
    ],
)
def test_provider_support_consumption_receipt_fails_closed_for_bad_answer_surface(
    answer_segment: str,
    reason_code: str,
) -> None:
    from runtime.reasoning.provider_support_consumption import (
        build_provider_support_consumption_receipt,
    )

    receipt = build_provider_support_consumption_receipt(
        run_id="provider-natural-boundary-001",
        cpr_read_result=_cpr_result(),
        answer_segment=answer_segment,
        support_packet_ref="oy-support://provider-natural-boundary-001/cpr/msg-support-001",
        answer_segment_ref="oy-pane://provider-natural-boundary-001/answer/lines-41-65",
        answer_support_alignment="enough_with_limits",
    )

    assert receipt["status"] == "typed_unavailable"
    assert receipt["route_free_consumption_proven"] is False
    assert reason_code in receipt["reason_codes"]


def test_provider_support_consumption_receipt_fails_closed_without_safe_support() -> None:
    from runtime.reasoning.provider_support_consumption import (
        build_provider_support_consumption_receipt,
    )

    cpr_result = _cpr_result()
    cpr_result["mf1_support_metadata"]["support_facts_count"] = 0
    cpr_result["mf1_support_metadata"]["typed_unavailable_present"] = True

    receipt = build_provider_support_consumption_receipt(
        run_id="provider-natural-boundary-001",
        cpr_read_result=cpr_result,
        answer_segment="Agent runtime role and plugin distribution location are separate boundaries.",
        support_packet_ref="oy-support://provider-natural-boundary-001/cpr/msg-support-001",
        answer_segment_ref="oy-pane://provider-natural-boundary-001/answer/lines-41-65",
        answer_support_alignment="enough_with_limits",
    )

    assert receipt["status"] == "typed_unavailable"
    assert "support_facts_missing" in receipt["reason_codes"]
    assert "typed_unavailable_present" in receipt["reason_codes"]


def test_provider_support_consumption_schema_rejects_overclaim_mutation() -> None:
    from runtime.reasoning.provider_support_consumption import (
        build_provider_support_consumption_receipt,
        validate_provider_support_consumption_receipt,
    )

    receipt = build_provider_support_consumption_receipt(
        run_id="provider-natural-boundary-001",
        cpr_read_result=_cpr_result(),
        answer_segment="Agent runtime role and plugin distribution location are separate boundaries.",
        support_packet_ref="oy-support://provider-natural-boundary-001/cpr/msg-support-001",
        answer_segment_ref="oy-pane://provider-natural-boundary-001/answer/lines-41-65",
        answer_support_alignment="enough_with_limits",
    )
    mutated = json.loads(json.dumps(receipt))
    mutated["production_readiness_claimed"] = True

    with pytest.raises(ValueError, match="production readiness"):
        validate_provider_support_consumption_receipt(mutated)
