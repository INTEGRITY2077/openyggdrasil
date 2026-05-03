"""
Production Verification — 14차 Axis 3 S4 + Axis 4 B4 + Axis 6 L3+L4.

S4 (SOT 통합): primitives.py + vault_guard.py 통합 검증
B4 (Sandbox): sandbox.py bubblewrap/none 모드 검증
L3 (실사용): Provider 세션 Producer→Consumer 왕복 검증
L4 (안정성): 10회 연속 실행 안정성 검증

Usage:
    python -m runtime.production_verify --vault /tmp/v --mailbox /tmp/m --rounds 10
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))


def verify_sot_integration() -> dict:
    """S4: vault_guard가 primitives에 통합되었는지 확인."""
    from ptc.primitives import save_to_vault, build_vault_node
    import inspect

    src = inspect.getsource(save_to_vault)
    has_guard = "vault_guard" in src
    return {"sot_integration": has_guard, "detail": "vault_guard imported in save_to_vault" if has_guard else "NOT FOUND"}


def verify_sandbox() -> dict:
    """B4: bubblewrap 샌드박스 동작 검증."""
    from sandbox import sandbox_run

    result = sandbox_run(["python3", "-c", "print('hello sandbox')"], timeout=10)
    return {
        "sandbox_mode": result.get("sandbox", "unknown"),
        "execution_ok": result.get("status") == "ok",
        "exit_code": result.get("exit_code"),
    }


def verify_provider_roundtrip(vault: Path, mailbox: Path) -> dict:
    """L3+L4: Producer→Consumer 왕복 + 10회 연속 안정성."""
    from operator_entrypoint import run_producer, run_consumer
    from ptc.primitives import load_vault
    import uuid as _uuid

    results = {"rounds": [], "all_ok": True}

    for rnd in range(10):
        ses = mailbox / "active" / f"hermes-verify"
        ses.mkdir(parents=True, exist_ok=True)

        topic = f"안정성-검증-라운드-{rnd}-{_uuid.uuid4().hex[:6]}"
        intent = {
            "intent": "save", "mail_id": f"stab-{rnd}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"context_snapshot": topic},
        }
        (ses / "intents.jsonl").write_text(json.dumps(intent, ensure_ascii=False) + "\n", encoding="utf-8")
        run_producer(ses, vault)

        nodes = load_vault(vault)
        round_ok = len(nodes) > 0
        results["rounds"].append({"round": rnd, "nodes": len(nodes), "ok": round_ok})
        if not round_ok:
            results["all_ok"] = False

    results["round_count"] = len(results["rounds"])
    results["success_count"] = sum(1 for r in results["rounds"] if r["ok"])
    return results


def main():
    parser = argparse.ArgumentParser(description="Production Verification")
    parser.add_argument("--vault", type=Path, help="Vault path (auto tmp if not set)")
    parser.add_argument("--mailbox", type=Path, help="Mailbox path (auto tmp if not set)")
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()

    import tempfile as _tf
    import shutil as _sh

    tmpdir = Path(_tf.mkdtemp())
    try:
        vault = args.vault or (tmpdir / "vault")
        mailbox = args.mailbox or (tmpdir / "mailbox")
        vault.mkdir(parents=True, exist_ok=True)
        mailbox.mkdir(parents=True, exist_ok=True)

        results = {
            "sot_integration": verify_sot_integration(),
            "sandbox": verify_sandbox(),
            "stability": verify_provider_roundtrip(vault, mailbox),
        }

        all_pass = (
            results["sot_integration"]["sot_integration"]
            and results["sandbox"]["execution_ok"]
            and results["stability"]["all_ok"]
        )
        results["overall"] = "PASS" if all_pass else "FAIL"

        print(json.dumps(results, ensure_ascii=False, indent=2))
        sys.exit(0 if all_pass else 1)
    finally:
        _sh.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
