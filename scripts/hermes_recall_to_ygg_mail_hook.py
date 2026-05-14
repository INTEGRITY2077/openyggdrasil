#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def main() -> int:
    raw = sys.stdin.read()
    event: dict[str, Any] = {}
    if raw.strip():
        try:
            payload = json.loads(raw)
            if isinstance(payload, Mapping):
                event = dict(payload)
        except json.JSONDecodeError:
            event = {"decode_error": True}
    # The recall hook currently only prevents a missing-command failure. Product
    # recall still belongs to Provider-triggered Find Request or explicit ygg recall.
    _append_jsonl(
        Path.home() / ".yggdrasil" / "sessions" / "postman" / "provider_recall_hook_log.jsonl",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ignored",
            "reason_code": "recall_hook_noop_until_find_request_contract",
            "session_id": event.get("session_id"),
            "tool_name": event.get("tool_name"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
