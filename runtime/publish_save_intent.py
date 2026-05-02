#!/usr/bin/env python3
"""
OpenYggdrasil Save-Intent Publisher — 헤르메스 스킬/훅에서 호출하는 경량 유틸리티.

Usage:
    python3 runtime/publish_save_intent.py <mailbox_path> <provider_id> "<context_snapshot>"

Example:
    python3 runtime/publish_save_intent.py \\
        /mnt/d/0_PROJECT/openyggdrasil-private-dev/testbed/mailbox/hermes/ \\
        deepseek \\
        "게이트웨이 패턴을 도입하기로 결정했습니다."
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def publish_save_intent(mailbox: Path, provider_id: str, context_snapshot: str) -> dict:
    """메일박스에 save-intent 메시지를 발행한다."""
    mailbox.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    mail_id = f"hermes-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    message = {
        "intent": "save",
        "mail_id": mail_id,
        "provider_id": provider_id,
        "timestamp": now.isoformat(),
        "payload": {
            "context_snapshot": context_snapshot.strip(),
        },
    }

    messages_file = mailbox / "messages.jsonl"
    with open(messages_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")

    return {"status": "published", "mail_id": mail_id, "mailbox": str(mailbox)}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 runtime/publish_save_intent.py <mailbox> <provider_id> <context_snapshot>")
        sys.exit(1)

    mailbox_path = Path(sys.argv[1])
    provider_id = sys.argv[2]
    context_snapshot = sys.argv[3]

    result = publish_save_intent(mailbox_path, provider_id, context_snapshot)
    print(json.dumps(result, ensure_ascii=False))
