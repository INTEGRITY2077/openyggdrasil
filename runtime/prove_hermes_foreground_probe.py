from __future__ import annotations

import json
import sys
from pathlib import Path

from hermes_foreground_probe import run_hermes_foreground_probe


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    proof = run_hermes_foreground_probe()
    proof_path = Path(__file__).resolve().parents[1] / "_tmp" / "hermes-foreground-probe-proof.json"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    print(proof_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
