from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hermes_attachment_reliability import prove_attachment_reliability, write_reliability_report
from hermes_foreground_probe import DEFAULT_BASE_PROFILE, DEFAULT_PROBE_PROFILE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--probe-profile", default=DEFAULT_PROBE_PROFILE)
    parser.add_argument("--clone-from", default=DEFAULT_BASE_PROFILE)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    report = prove_attachment_reliability(
        iterations=args.iterations,
        probe_profile=args.probe_profile,
        clone_from=args.clone_from,
    )
    report_path = Path(__file__).resolve().parents[1] / "_tmp" / "hermes-attachment-reliability-report.json"
    write_reliability_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
