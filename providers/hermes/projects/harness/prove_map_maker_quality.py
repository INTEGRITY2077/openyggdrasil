from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_common import OPS_ROOT
from map_maker_quality import build_replay_cases, run_replay_case, summarize_case_results


OUTPUT_PATH = OPS_ROOT / "map-maker-quality-proof.json"


def main() -> None:
    case_outputs: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="map-maker-quality-") as tmpdir:
        root = Path(tmpdir)
        for case in build_replay_cases():
            case_outputs.append(run_replay_case(root=root, case=case))

    result_rows = [item["result"] for item in case_outputs]
    summary = summarize_case_results(result_rows)
    payload = {
        "status": "ok" if summary["failed_cases"] == 0 else "degraded",
        "summary": summary,
        "cases": case_outputs,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
