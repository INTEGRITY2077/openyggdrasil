from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from admission_stub import admit_decision_candidate
from gardener_stub import cultivate_decision_seed
from nursery_stub import engrave_decision_seed
from decision_contracts import (
    validate_admission_verdict,
    validate_cultivated_decision,
    validate_decision_candidate,
    validate_engraved_seed,
)
from harness_common import DEFAULT_VAULT
from mailbox_status import write_mailbox_status
from mailbox_store import append_claim, claimed_message_ids, read_messages
from packet_factory import (
    build_admission_verdict_packet,
    build_cultivated_decision_packet,
    build_engraved_seed_packet,
)
from postman_gateway import submit_packet


def decision_candidate_messages(
    *,
    profile: str | None,
    session_id: str | None,
    mailbox_namespace: str | None = None,
) -> List[Dict[str, Any]]:
    claimed = claimed_message_ids(
        consumer="decision_roundtrip",
        claim_type="roundtrip_completed",
        namespace=mailbox_namespace,
    )
    messages: List[Dict[str, Any]] = []
    for message in read_messages(namespace=mailbox_namespace):
        if message.get("kind") != "packet":
            continue
        if message.get("message_type") != "decision_candidate":
            continue
        if message.get("status") != "new":
            continue
        if message.get("message_id") in claimed:
            continue
        scope = message.get("scope", {})
        if profile and scope.get("profile") != profile:
            continue
        if session_id and scope.get("session_id") != session_id:
            continue
        messages.append(message)
    return messages


def roundtrip_decision_candidate_message(
    message: Dict[str, Any],
    *,
    vault_root: Path = DEFAULT_VAULT,
    mailbox_namespace: str | None = None,
) -> Dict[str, Any]:
    scope = dict(message.get("scope") or {})
    payload = dict(message.get("payload") or {})
    decision_candidate = payload.get("decision_candidate")
    if not isinstance(decision_candidate, dict):
        raise RuntimeError("decision_candidate packet missing payload.decision_candidate")
    validate_decision_candidate(decision_candidate)

    admission_verdict = admit_decision_candidate(
        decision_candidate=decision_candidate,
        vault_root=vault_root,
    )
    validate_admission_verdict(admission_verdict)
    engraved_seed = engrave_decision_seed(
        admission_verdict=admission_verdict,
        decision_candidate=decision_candidate,
    )
    validate_engraved_seed(engraved_seed)
    cultivated_decision = cultivate_decision_seed(
        engraved_seed=engraved_seed,
        vault_root=vault_root,
    )
    validate_cultivated_decision(cultivated_decision)

    append_claim(
        message_id=message["message_id"],
        consumer="decision_roundtrip",
        claim_type="roundtrip_completed",
        scope=scope,
        namespace=mailbox_namespace,
    )

    profile = str(scope.get("profile") or decision_candidate.get("provider_profile") or "wiki")
    session_id = str(scope.get("session_id") or decision_candidate.get("provider_session_id") or "") or None
    parent_question_id = message.get("parent_question_id")

    admission_packet = build_admission_verdict_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        admission_verdict=admission_verdict,
    )
    engraved_packet = build_engraved_seed_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        engraved_seed=engraved_seed,
    )
    cultivated_packet = build_cultivated_decision_packet(
        profile=profile,
        session_id=session_id,
        parent_question_id=parent_question_id,
        cultivated_decision=cultivated_decision,
    )
    submit_packet(admission_packet, namespace=mailbox_namespace)
    submit_packet(engraved_packet, namespace=mailbox_namespace)
    submit_packet(cultivated_packet, namespace=mailbox_namespace)
    return {
        "candidate_message_id": message["message_id"],
        "admission_packet_id": admission_packet["message_id"],
        "engraved_packet_id": engraved_packet["message_id"],
        "cultivated_packet_id": cultivated_packet["message_id"],
        "seed_identity_key": engraved_seed["seed_identity_key"],
        "integrity_status": engraved_seed["integrity_status"],
        "planting_ready": engraved_seed["planting_ready"],
        "topic_id": cultivated_decision["topic_id"],
        "canonical_relative_path": cultivated_decision["canonical_relative_path"],
        "canonical_note_path": cultivated_decision["canonical_note_path"],
        "provenance_note_path": cultivated_decision["provenance_note_path"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the thin decision roundtrip middle chain once.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--vault-root", default=str(DEFAULT_VAULT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    vault_root = Path(args.vault_root).resolve()
    messages = decision_candidate_messages(
        profile=args.profile,
        session_id=args.session_id,
        mailbox_namespace=args.mailbox_namespace,
    )
    if args.limit:
        messages = messages[: args.limit]
    results = [
        roundtrip_decision_candidate_message(
            message,
            vault_root=vault_root,
            mailbox_namespace=args.mailbox_namespace,
        )
        for message in messages
    ]
    status = write_mailbox_status(namespace=args.mailbox_namespace)
    print(json.dumps({"processed": len(results), "results": results, "status": status["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
