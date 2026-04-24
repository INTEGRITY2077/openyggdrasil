from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from decision_roundtrip_once import decision_candidate_messages, roundtrip_decision_candidate_message
from harness_common import DEFAULT_VAULT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one live thin decision roundtrip proof.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    parser.add_argument("--vault-root", default=str(DEFAULT_VAULT))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    messages = decision_candidate_messages(
        profile=args.profile,
        session_id=args.session_id,
        mailbox_namespace=args.mailbox_namespace,
    )
    payload: dict[str, Any]
    if not messages:
        payload = {
            "status": "blocked",
            "reason": "no decision_candidate packets found",
            "mailbox_namespace": args.mailbox_namespace,
        }
    else:
        result = roundtrip_decision_candidate_message(
            messages[0],
            vault_root=Path(args.vault_root).resolve(),
            mailbox_namespace=args.mailbox_namespace,
        )
        payload = {
            "status": "cultivated",
            "mailbox_namespace": args.mailbox_namespace,
            "result": result,
        }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
