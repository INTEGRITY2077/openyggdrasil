"""
Operator Entrypoint — SKILL이 호출하는 런타임 진입점.

engine.py를 터치하지 않는다. POC에서 검증된 primitive를
runtime/ptc/primitives.py에서 import하여 SKILL 어포던스 아래에서
조합한다.

Usage (Provider SKILL → subprocess):
    python -m runtime.operator_entrypoint produce --mailbox /path/to/mailbox --vault /path/to/vault
    python -m runtime.operator_entrypoint consume --mailbox /path/to/mailbox --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# primitives는 같은 runtime/ptc/ 패키지에서 import
sys.path.insert(0, str(Path(__file__).parent))
from ptc.primitives import (
    extract_decisions,
    build_spo_triples,
    build_vault_node,
    save_to_vault,
    search_vault_by_keyword,
    format_consumer_result,
    load_vault,
)


def run_producer(mailbox: Path, vault: Path):
    """Mailbox에서 save-intent를 폴링하여 Vault에 적재."""
    messages_file = mailbox / "messages.jsonl"
    receipts_file = mailbox / "receipts.jsonl"

    if not messages_file.exists():
        print(json.dumps({"status": "no_messages"}))
        return

    # Load completed
    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line).get("in_reply_to"))

    # Process pending
    for line in messages_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg.get("intent") != "save" or msg["mail_id"] in completed:
            continue

        snapshot = msg["payload"]["context_snapshot"]
        candidates = extract_decisions(snapshot)
        nodes = []
        for c in candidates:
            triples = build_spo_triples(c["sentence"], c["marker"], c["category"])
            for spo in triples:
                node = build_vault_node(spo, provider_id=msg.get("provider_id", "unknown"))
                path = save_to_vault(vault, node)
                nodes.append(node["node_id"])

        receipt = {
            "receipt_id": str(uuid.uuid4())[:8],
            "in_reply_to": msg["mail_id"],
            "status": "acknowledged",
            "produced_count": len(nodes),
            "nodes": nodes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "producer_pid": os.getpid(),
        }
        with open(receipts_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

    print(json.dumps({"status": "producer_done", "pid": os.getpid()}))


def run_consumer(mailbox: Path, vault: Path):
    """Mailbox에서 query-intent를 폴링하여 Vault 검색 결과 반환."""
    queries_file = mailbox / "queries.jsonl"
    receipts_file = mailbox / "query_receipts.jsonl"

    if not queries_file.exists():
        print(json.dumps({"status": "no_queries"}))
        return

    # Load vault index
    vault_nodes = load_vault(vault)

    completed = set()
    if receipts_file.exists():
        for line in receipts_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(json.loads(line).get("in_reply_to"))

    for line in queries_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["mail_id"] in completed:
            continue

        query_text = msg["payload"]["query_text"]
        matches = search_vault_by_keyword(query_text, vault_nodes)
        bundle = format_consumer_result(query_text, matches)

        receipt = {
            "receipt_id": str(uuid.uuid4())[:8],
            "in_reply_to": msg["mail_id"],
            "status": "completed",
            "bundle": bundle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consumer_pid": os.getpid(),
        }
        with open(receipts_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

    print(json.dumps({"status": "consumer_done", "pid": os.getpid()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="openyggdrasil Operator Entrypoint")
    parser.add_argument("mode", choices=["produce", "consume"])
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    args = parser.parse_args()

    if args.mode == "produce":
        run_producer(args.mailbox, args.vault)
    else:
        run_consumer(args.mailbox, args.vault)
