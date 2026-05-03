"""
Cross-Provider Verification — 14차 Axis 6.

두 Provider 세션(hermes-A, hermes-B)이 동일 Vault를 공유하여
교차 메모리 접근이 가능함을 검증.

Usage:
    python -m runtime.cross_provider_verify --vault /tmp/vault --mailbox /tmp/mailbox
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from operator_entrypoint import run_producer, run_consumer
from ptc.primitives import load_vault


def verify(vault: Path, mailbox: Path) -> dict:
    """교차 메모리 실증 실행 → 결과 dict."""
    ses_a = mailbox / "active" / "hermes-A"
    ses_b = mailbox / "active" / "hermes-B"
    ses_a.mkdir(parents=True, exist_ok=True)
    ses_b.mkdir(parents=True, exist_ok=True)

    results = {}

    # Provider A: save
    topic_id = uuid.uuid4().hex[:8]
    intent_a = {
        "intent": "save", "mail_id": f"xa-{topic_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"context_snapshot": f"크로스프로바이더 교차 메모리 실증 토픽 {topic_id}"},
        "provider_id": "hermes-A",
    }
    (ses_a / "intents.jsonl").write_text(json.dumps(intent_a, ensure_ascii=False) + "\n", encoding="utf-8")
    run_producer(ses_a, vault)

    # Provider A 노드 확인
    nodes_after_save = load_vault(vault)
    results["provider_a_nodes"] = len(nodes_after_save)

    # Provider B: query 동일 Vault
    intent_b = {
        "intent": "query", "mail_id": f"xb-{topic_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"query_text": f"크로스프로바이더 교차 메모리 {topic_id}"},
        "provider_id": "hermes-B",
    }
    (ses_b / "queries.jsonl").write_text(json.dumps(intent_b, ensure_ascii=False) + "\n", encoding="utf-8")
    run_consumer(ses_b, vault)

    # Provider B 검색 결과 확인
    qr = ses_b / "query_receipts.jsonl"
    query_receipts = [json.loads(l) for l in qr.read_text().splitlines() if l.strip()] if qr.exists() else []
    results["provider_b_query_receipts"] = len(query_receipts)
    results["cross_memory_ok"] = len(query_receipts) > 0 and len(nodes_after_save) > 0

    results["status"] = "verified" if results["cross_memory_ok"] else "failed"
    return results


def main():
    parser = argparse.ArgumentParser(description="Cross-Provider Verification")
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--mailbox", required=True, type=Path)
    args = parser.parse_args()

    result = verify(args.vault, args.mailbox)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("status") == "verified" else 1)


if __name__ == "__main__":
    main()
