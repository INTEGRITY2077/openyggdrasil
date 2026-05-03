#!/usr/bin/env python3
"""
OpenYggdrasil Live Session — Foreground Provider ↔ Operator Demo.

실제 Provider(Hermes)가 Operator를 subprocess로 호출하는 것과
동일한 흐름을 포그라운드에서 실시간으로 보여준다.

Usage:
    python3 runtime/live_session.py --vault /path/to/vault

Commands:
    s <text>     Save to vault (fixed chain, Korean text with decision markers)
    p            Enter PTC code (multi-line, end with blank line)
    q <query>    Query vault (fixed chain)
    pq <query>   Query vault (PTC deep_search)
    v            View vault contents
    h            Help
    quit         Exit
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
OPERATOR_MODULE = "runtime.operator_entrypoint"


def run_operator(mode: str, mailbox: Path, vault: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", OPERATOR_MODULE, mode,
         "--mailbox", str(mailbox), "--vault", str(vault)],
        capture_output=True, text=True, timeout=120,
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )


def _read_receipts_raw(mailbox: Path, filename: str = "receipts.jsonl") -> list[dict]:
    f = mailbox / filename
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def _print_latest_receipt(mailbox: Path, shown_count: int) -> int:
    """마지막 receipt만 출력하고 총 개수를 반환."""
    receipts = _read_receipts_raw(mailbox)
    if len(receipts) <= shown_count:
        return shown_count
    r = receipts[-1]
    produced = r.get("produced_count", 0)
    nodes = r.get("nodes", [])
    ptc_mode = r.get("ptc_mode", False)
    intent = r.get("intent", "")
    stdout = r.get("stdout", "") or r.get("ptc_stdout", "")

    if intent == "sandbox-exec" or "sandbox" in str(r.get("in_reply_to", "")):
        # sandbox-exec receipt
        if stdout:
            try:
                parsed = json.loads(stdout.strip().split("\n")[-1])
                res = parsed.get("result", {})
                print(f"  [PTC result] {json.dumps(res, ensure_ascii=False)[:300]}")
            except Exception:
                print(f"  [PTC stdout] {stdout[:200]}")
        else:
            print(f"  [PTC] exit={r.get('exit_code')} sandbox={r.get('sandbox','?')}")
    elif ptc_mode:
        # PTC save path
        print(f"  [PTC save] produced={produced}")
        if stdout:
            try:
                parsed = json.loads(stdout.strip().split("\n")[-1])
                res = parsed.get("result", {})
                for k, v in res.items():
                    if isinstance(v, list):
                        print(f"    {k}: {len(v)} items")
                    elif isinstance(v, (str, int, float, bool)):
                        print(f"    {k}: {v}")
            except Exception:
                print(f"    stdout: {stdout[:200]}")
    else:
        # Fixed chain save
        print(f"  [save] produced={produced}")
        if nodes:
            for nid in nodes[:3]:
                print(f"    node_id={nid[:12]}...")

    return len(receipts)


def _print_latest_query(mailbox: Path, shown_count: int) -> int:
    """마지막 query receipt만 출력."""
    receipts = _read_receipts_raw(mailbox, "query_receipts.jsonl")
    if len(receipts) <= shown_count:
        if not receipts:
            print("  (no query results)")
        return shown_count
    r = receipts[-1]
    bundle = r.get("bundle", {})
    mode = bundle.get("mode", "fixed")

    if mode == "ptc":
        stdout = bundle.get("ptc_stdout", "")
        try:
            parsed = json.loads(stdout.strip().split("\n")[-1])
            res = parsed.get("result", {})
            print(f"  [PTC query] {json.dumps(res, ensure_ascii=False)[:300]}")
        except Exception:
            print(f"  [PTC query] {stdout[:200]}")
    else:
        results = bundle.get("results", [])
        print(f"  [query] {len(results)} matches")
        for m in results[:3]:
            subj = m.get("subject", m.get("node_id", "?"))
            score = m.get("_match_score", m.get("_bm25_score", 0))
            print(f"    {subj[:60]} (score={score:.2f})")
    return len(receipts)


def _list_vault(vault: Path):
    concepts = vault / "concepts"
    if not concepts.exists() or not list(concepts.glob("*.md")):
        print("  (empty vault)")
        return
    files = sorted(concepts.glob("*.md"))
    print(f"  {len(files)} nodes:")
    for f in files:
        try:
            text = f.read_text()[:200]
            m = re.search(r'title:\s*"?([^"\n]+)"?', text)
            if m:
                print(f"    - {m.group(1)[:60]}")
            else:
                first = text.strip().split("\n")[0][:60]
                print(f"    - {first}")
        except Exception:
            print(f"    - {f.name}")


def _read_multiline():
    """멀티라인 PTC 코드 입력. 빈 줄에서 종료."""
    lines = []
    while True:
        try:
            line = input("...   ")
        except (EOFError, KeyboardInterrupt):
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenYggdrasil Live Foreground Session")
    parser.add_argument("--vault", type=Path, default=REPO / "vault")
    args = parser.parse_args()

    vault = args.vault.resolve()
    (vault / "concepts").mkdir(parents=True, exist_ok=True)

    session_id = f"live-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    mailbox = vault.parent / ".yggdrasil" / "inbox" / "hermes" / "default" / session_id
    mailbox.mkdir(parents=True)

    print("=" * 60)
    print("  OpenYggdrasil Live Foreground Session")
    print(f"  Session: {session_id}")
    print(f"  Vault:   {vault}")
    print("=" * 60)
    print("  s <text> | p | q <query> | pq <query> | v | quit")
    print()

    turn = 0
    receipt_shown = 0
    query_shown = 0

    while True:
        try:
            cmd = input(f"[{turn}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue

        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        text = parts[1] if len(parts) > 1 else ""

        if action == "quit":
            break

        elif action == "v":
            _list_vault(vault)
            continue

        elif action == "h":
            print("  s <text> | p | q <query> | pq <query> | v | quit")
            continue

        elif action == "s" and text:
            intent = {
                "mail_id": f"t{turn}-{uuid.uuid4().hex[:6]}",
                "intent": "save",
                "payload": {"context_snapshot": text},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider_id": "hermes",
            }
            with open(mailbox / "intents.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(intent, ensure_ascii=False) + "\n")
            run_operator("produce", mailbox, vault)
            receipt_shown = _print_latest_receipt(mailbox, receipt_shown)
            turn += 1

        elif action == "p":
            # Multi-line PTC code input
            print("  (enter PTC code, empty line to execute):")
            code = _read_multiline()
            if not code.strip():
                print("  (empty code, skipped)")
                continue
            intent = {
                "mail_id": f"t{turn}-ptc-{uuid.uuid4().hex[:6]}",
                "intent": "sandbox-exec",
                "payload": {"code": code, "timeout": 60},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with open(mailbox / "intents.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(intent, ensure_ascii=False) + "\n")
            run_operator("produce", mailbox, vault)
            receipt_shown = _print_latest_receipt(mailbox, receipt_shown)
            turn += 1

        elif action == "q" and text:
            query = {
                "mail_id": f"t{turn}-q-{uuid.uuid4().hex[:6]}",
                "payload": {"query_text": text},
            }
            (mailbox / "queries.jsonl").write_text(json.dumps(query, ensure_ascii=False) + "\n")
            run_operator("consume", mailbox, vault)
            query_shown = _print_latest_query(mailbox, query_shown)
            turn += 1

        elif action == "pq" and text:
            query = {
                "mail_id": f"t{turn}-pq-{uuid.uuid4().hex[:6]}",
                "payload": {
                    "ptc": True,
                    "ptc_code": f'result(deep_search("{text}", max_depth=2, limit=10))',
                    "query_text": text,
                },
            }
            (mailbox / "queries.jsonl").write_text(json.dumps(query, ensure_ascii=False) + "\n")
            run_operator("consume", mailbox, vault)
            query_shown = _print_latest_query(mailbox, query_shown)
            turn += 1

        else:
            print(f"  ? {cmd}")

    # Final vault state
    print()
    _list_vault(vault)


if __name__ == "__main__":
    main()
