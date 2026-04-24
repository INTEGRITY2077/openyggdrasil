from __future__ import annotations

import argparse
import json

from packet_scoring import select_inbox_packets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select the most relevant push-delivered mailbox packets for a Hermes preflight."
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packets = select_inbox_packets(
        profile=args.profile,
        session_id=args.session_id,
        parent_question_id=args.parent_question_id,
        query_text=args.query,
        top_k=args.top_k,
    )
    print(json.dumps(packets, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
