from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from attachments.provider_attachment import (  # noqa: E402
    validate_inbox_binding,
    validate_provider_descriptor,
    validate_session_attachment,
    validate_turn_delta,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def validate_workspace(workspace_root: Path) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    attachments_root = workspace_root / ".yggdrasil" / "providers"
    results: list[dict[str, Any]] = []
    if not attachments_root.exists():
        return {
            "workspace_root": str(workspace_root),
            "attachment_count": 0,
            "ok_count": 0,
            "error_count": 0,
            "attachments": [],
        }

    for attachment_path in sorted(attachments_root.rglob("session_attachment.v1.json")):
        attachment_root = attachment_path.parent
        result = {
            "attachment_root": str(attachment_root),
            "ok": True,
            "errors": [],
        }
        try:
            descriptor = _read_json(attachment_root / "provider_descriptor.v1.json")
            validate_provider_descriptor(descriptor)
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append(f"provider_descriptor: {exc}")

        try:
            attachment = _read_json(attachment_root / "session_attachment.v1.json")
            validate_session_attachment(attachment)
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append(f"session_attachment: {exc}")

        try:
            inbox_binding = _read_json(attachment_root / "inbox_binding.v1.json")
            validate_inbox_binding(inbox_binding)
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append(f"inbox_binding: {exc}")

        try:
            for row in _iter_jsonl(attachment_root / "turn_delta.v1.jsonl"):
                validate_turn_delta(row)
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append(f"turn_delta: {exc}")

        results.append(result)

    ok_count = sum(1 for row in results if row["ok"])
    return {
        "workspace_root": str(workspace_root),
        "attachment_count": len(results),
        "ok_count": ok_count,
        "error_count": len(results) - ok_count,
        "attachments": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate OpenYggdrasil attachment artifacts.")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Workspace root that owns the .yggdrasil attachment tree.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = validate_workspace(args.workspace_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"attachments={report['attachment_count']} ok={report['ok_count']} "
            f"errors={report['error_count']}"
        )
        for row in report["attachments"]:
            status = "ok" if row["ok"] else "error"
            print(f"{status}: {row['attachment_root']}")
            for error in row["errors"]:
                print(f"  - {error}")
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
