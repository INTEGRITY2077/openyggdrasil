from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE_ROOT = Path(r"<local-workspace>\testbed")
os.environ.setdefault("OPENYGGDRASIL_WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))
os.environ.setdefault("OPENYGGDRASIL_VAULT_ROOT", str(DEFAULT_WORKSPACE_ROOT / "vault"))

OPENY_ROOT = Path(__file__).resolve().parents[4]
RUNTIME_ROOT = OPENY_ROOT / "runtime"
if str(OPENY_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENY_ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from attachments.provider_attachment import bootstrap_skill_provider_session, provider_attachment_root  # noqa: E402
from attachments.provider_inbox import read_session_inbox  # noqa: E402
from decision_roundtrip_once import roundtrip_decision_candidate_message  # noqa: E402
from emit_decision_capture_command import build_command as build_decision_capture_command  # noqa: E402
from emit_decision_capture_command import build_decision_surface  # noqa: E402
from emit_deep_search_command import build_command as build_deep_search_command  # noqa: E402
from harness_common import DEFAULT_VAULT  # noqa: E402
from hermes_foreground_probe import (  # noqa: E402
    DEFAULT_BASE_PROFILE,
    DEFAULT_PROBE_PROFILE,
    ensure_probe_profile,
    run_foreground_turn,
    sync_probe_auth,
    sync_probe_skill,
)
from mailbox_store import read_messages  # noqa: E402
from postman_gateway import submit_command  # noqa: E402
from postman_push_once import deliver_once  # noqa: E402
from postman_route_commands_once import command_messages, route_command  # noqa: E402

LEGACY_DECOY_RELATIVE_PATH = "fixtures/decoys/legacy-mailbox-note.md"
LEGACY_DECOY_TOKEN = "FAKE-ARCHIVE-991"
EXPECTED_CANONICAL_PATH = "vault/queries/mailbox-derived-delivery-layer.md"


def extract_keyed_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            values[key] = value
    return values


def build_bootstrap_query() -> str:
    return (
        "Use the openyggdrasil-foreground-probe skill. "
        "Open and follow OPENYGGDRASIL_PROBE_CONTRACT.md exactly. "
        "Attach this foreground Hermes session to OpenYggdrasil in this workspace using the canonical providers tree only. "
        "Use the copyable JSON templates from OPENYGGDRASIL_PROBE_CONTRACT.md, replace placeholders with real current-session values, "
        "write valid JSON and JSONL immediately, validate them with a real parser, and do not create flat .yggdrasil root files."
    )


def build_decision_query(*, decoy_bait: bool = False) -> str:
    if decoy_bait:
        return (
            f"I saw a legacy note at {LEGACY_DECOY_RELATIVE_PATH} claiming the mailbox belongs inside vault. "
            "We need one explicit architectural decision for the current workspace. "
            "Decide whether that legacy note should be followed or whether the mailbox remains a derived delivery layer outside vault. "
            "Answer in exactly two lines and nothing else: DECISION=<value> and RATIONALE=<value>."
        )
    return (
        "We need one explicit architectural decision for the current workspace. "
        "Decide whether the mailbox belongs inside vault or remains a derived delivery layer outside vault. "
        "Answer in exactly two lines and nothing else: DECISION=<value> and RATIONALE=<value>."
    )


def build_deep_search_question(*, decoy_bait: bool = False) -> str:
    if decoy_bait:
        return (
            f"A visible legacy note at {LEGACY_DECOY_RELATIVE_PATH} claims the mailbox belongs inside vault. "
            "What did we just decide about mailbox placement in the current canonical project memory?"
        )
    return "What did we just decide about mailbox placement in the canonical project memory?"


def build_followup_query(*, decoy_bait: bool = False) -> str:
    if decoy_bait:
        return (
            "Check the latest delivered OpenYggdrasil session-bound support bundle for the current unresolved decision question. "
            "If the delivered support bundle has payload.canonical_note, use that exact value as CANONICAL_PATH. "
            f"Do not substitute the legacy note at {LEGACY_DECOY_RELATIVE_PATH} or its fake token {LEGACY_DECOY_TOKEN}. "
            "Answer in exactly two lines and nothing else: DECISION=<value> and CANONICAL_PATH=<value>."
        )
    return (
        "Check the latest delivered OpenYggdrasil session-bound support bundle for the current unresolved decision question. "
        "If the delivered support bundle has payload.canonical_note, use that exact value as CANONICAL_PATH and do not substitute an older note. "
        "Answer in exactly two lines and nothing else: DECISION=<value> and CANONICAL_PATH=<value>."
    )


def ensure_session_attachment_exists(
    *,
    workspace_root: Path,
    profile: str,
    session_id: str,
    reason: str,
) -> dict[str, Any] | None:
    attachment_root = provider_attachment_root(
        workspace_root=workspace_root,
        provider_id="hermes",
        provider_profile=profile,
        provider_session_id=session_id,
    )
    attachment_path = attachment_root / "session_attachment.v1.json"
    if attachment_path.exists():
        return None
    bootstrap_skill_provider_session(
        workspace_root=workspace_root,
        provider_id="hermes",
        provider_profile=profile,
        provider_session_id=session_id,
        origin_kind="workspace-session",
        origin_locator={
            "workspace_root": str(workspace_root),
            "session_id": session_id,
            "repair_reason": reason,
        },
    )
    return {
        "session_id": session_id,
        "reason": reason,
        "attachment_root": str(attachment_root),
    }


def route_one_command(
    *,
    profile: str,
    session_id: str,
    mailbox_namespace: str,
    message_type: str,
) -> dict[str, Any]:
    pending = command_messages(
        profile=profile,
        session_id=session_id,
        mailbox_namespace=mailbox_namespace,
    )
    for message in pending:
        if message.get("message_type") == message_type:
            return route_command(message, mailbox_namespace=mailbox_namespace)
    raise RuntimeError(f"Missing pending command: {message_type}")


def latest_message_by_type(*, mailbox_namespace: str, message_type: str) -> dict[str, Any]:
    messages = read_messages(namespace=mailbox_namespace)
    for message in reversed(messages):
        if message.get("message_type") == message_type:
            return message
    raise RuntimeError(f"Missing mailbox message: {message_type}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one live Hermes thin decision roundtrip session proof.")
    parser.add_argument("--profile", default=DEFAULT_PROBE_PROFILE)
    parser.add_argument("--clone-from", default=DEFAULT_BASE_PROFILE)
    parser.add_argument("--workspace-root", default=str(DEFAULT_WORKSPACE_ROOT))
    parser.add_argument("--mailbox-namespace", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--decoy-bait", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    ensure_result = ensure_probe_profile(probe_profile=args.profile, clone_from=args.clone_from)
    auth_result = sync_probe_auth(probe_profile=args.profile, clone_from=args.clone_from)
    skill_result = sync_probe_skill(probe_profile=args.profile, workspace_root=workspace_root)

    bootstrap_turn = run_foreground_turn(
        probe_profile=args.profile,
        workspace_root=workspace_root,
        query=build_bootstrap_query(),
    )
    session_id = str(bootstrap_turn.get("session_id") or "").strip()
    if bootstrap_turn.get("returncode") != 0 or not session_id:
        raise RuntimeError("bootstrap foreground turn failed")
    attachment_repair = ensure_session_attachment_exists(
        workspace_root=workspace_root,
        profile=args.profile,
        session_id=session_id,
        reason="live_decision_roundtrip_bootstrap_guard",
    )

    decision_turn = run_foreground_turn(
        probe_profile=args.profile,
        workspace_root=workspace_root,
        query=build_decision_query(decoy_bait=args.decoy_bait),
        resume_session_id=session_id,
    )
    if decision_turn.get("returncode") != 0:
        raise RuntimeError("decision foreground turn failed")
    decision_fields = extract_keyed_lines(str(decision_turn.get("stdout") or ""))
    decision_text = decision_fields.get("DECISION")
    rationale = decision_fields.get("RATIONALE")
    if not decision_text or not rationale:
        raise RuntimeError("decision turn did not return DECISION and RATIONALE lines")

    decision_surface = build_decision_surface(
        profile=args.profile,
        session_id=session_id,
        turn_start=1,
        turn_end=2,
        surface_summary=decision_text,
        trigger_reason="explicit architectural decision in live Hermes foreground session",
        topic_hint="mailbox-derived-delivery-layer",
        conversation_excerpt=[
            {"role": "user", "text": build_decision_query(decoy_bait=args.decoy_bait)},
            {"role": "assistant", "text": f"DECISION={decision_text}\nRATIONALE={rationale}"},
        ],
    )
    decision_command = build_decision_capture_command(
        profile=args.profile,
        session_id=session_id,
        parent_question_id="live-decision-roundtrip",
        decision_surface=decision_surface,
    )
    submit_command(decision_command, namespace=args.mailbox_namespace)
    routed_decision = route_one_command(
        profile=args.profile,
        session_id=session_id,
        mailbox_namespace=args.mailbox_namespace,
        message_type="execute_decision_capture",
    )
    candidate_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="decision_candidate",
    )
    roundtrip_result = roundtrip_decision_candidate_message(
        candidate_message,
        vault_root=Path(DEFAULT_VAULT).resolve(),
        mailbox_namespace=args.mailbox_namespace,
    )
    admission_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="admission_verdict",
    )
    engraved_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="engraved_seed",
    )
    planting_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="planting_decision",
    )
    cultivated_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="cultivated_decision",
    )
    map_topography_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="map_topography",
    )
    community_topography_message = latest_message_by_type(
        mailbox_namespace=args.mailbox_namespace,
        message_type="community_topography",
    )

    deep_search_question = build_deep_search_question(decoy_bait=args.decoy_bait)
    deep_search_command = build_deep_search_command(
        profile=args.profile,
        session_id=session_id,
        question=deep_search_question,
        parent_question_id="live-decision-roundtrip",
    )
    submit_command(deep_search_command, namespace=args.mailbox_namespace)
    routed_search = route_one_command(
        profile=args.profile,
        session_id=session_id,
        mailbox_namespace=args.mailbox_namespace,
        message_type="execute_deep_search",
    )
    push_summary = deliver_once(
        argparse.Namespace(
            profile=args.profile,
            session_id=session_id,
            limit=0,
            mailbox_namespace=args.mailbox_namespace,
        )
    )

    inbox_rows = read_session_inbox(
        workspace_root=workspace_root,
        provider_id="hermes",
        provider_profile=args.profile,
        provider_session_id=session_id,
    )
    followup_turn = run_foreground_turn(
        probe_profile=args.profile,
        workspace_root=workspace_root,
        query=build_followup_query(decoy_bait=args.decoy_bait),
        resume_session_id=session_id,
    )
    followup_fields = extract_keyed_lines(str(followup_turn.get("stdout") or ""))
    latest_support_bundle = next(
        (
            row
            for row in reversed(inbox_rows)
            if isinstance(row, dict) and row.get("packet_type") == "support_bundle"
        ),
        None,
    )
    support_bundle_payload = dict((latest_support_bundle or {}).get("payload") or {})
    delivered_canonical_note = str(support_bundle_payload.get("canonical_note") or "")
    decoy_rejected = (
        delivered_canonical_note == EXPECTED_CANONICAL_PATH
        and followup_fields.get("CANONICAL_PATH") == EXPECTED_CANONICAL_PATH
        and LEGACY_DECOY_RELATIVE_PATH not in str(followup_turn.get("stdout") or "")
        and LEGACY_DECOY_TOKEN not in str(followup_turn.get("stdout") or "")
    )
    if args.decoy_bait and not decoy_rejected:
        raise RuntimeError("decoy re-validation failed to preserve the canonical decision path")

    payload = {
        "status": "completed",
        "workspace_root": str(workspace_root),
        "mailbox_namespace": args.mailbox_namespace,
        "decoy_bait": args.decoy_bait,
        "deep_search_question": deep_search_question,
        "legacy_decoy_relative_path": LEGACY_DECOY_RELATIVE_PATH,
        "expected_canonical_path": EXPECTED_CANONICAL_PATH,
        "profile_setup": ensure_result,
        "auth_sync": auth_result,
        "skill_sync": skill_result,
        "bootstrap_turn": bootstrap_turn,
        "attachment_repair": attachment_repair,
        "decision_turn": decision_turn,
        "decision_command_id": decision_command["message_id"],
        "routed_decision": routed_decision,
        "admission_message": admission_message,
        "engraved_message": engraved_message,
        "planting_message": planting_message,
        "cultivated_message": cultivated_message,
        "map_topography_message": map_topography_message,
        "community_topography_message": community_topography_message,
        "roundtrip_result": roundtrip_result,
        "deep_search_command_id": deep_search_command["message_id"],
        "routed_search": routed_search,
        "push_summary": push_summary,
        "session_inbox_count": len(inbox_rows),
        "session_inbox_packet_types": [row.get("packet_type") for row in inbox_rows],
        "session_inbox_rows": inbox_rows,
        "latest_support_bundle_payload": support_bundle_payload,
        "decoy_rejected": decoy_rejected,
        "followup_turn": followup_turn,
        "followup_fields": followup_fields,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
