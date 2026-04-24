from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from attachments.provider_attachment import (  # noqa: E402
    build_session_uid,
    provider_inbox_path,
    validate_inbox_binding,
    validate_provider_descriptor,
    validate_session_attachment,
    validate_turn_delta,
)
from harness_common import utc_now_iso  # noqa: E402


DEFAULT_CAPABILITIES = {
    "attachment": True,
    "turn_delta": True,
    "reverse_inbox": True,
    "heartbeat": False,
}
DEFAULT_ATTACHMENT_CAPABILITIES = {
    "turn_delta": True,
    "reverse_inbox": True,
    "heartbeat": False,
}


def _read_json_if_valid(path: Path, validator) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator(payload)
        return payload
    except Exception:  # noqa: BLE001
        return None


def _repair_turn_delta_file(path: Path) -> tuple[bool, list[str]]:
    if not path.exists():
        return False, []

    valid_rows: list[dict[str, Any]] = []
    invalid_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            validate_turn_delta(payload)
            valid_rows.append(payload)
        except Exception:  # noqa: BLE001
            invalid_lines.append(raw_line)

    if not invalid_lines:
        return False, []

    backup_path = path.with_suffix(path.suffix + ".broken")
    shutil.copyfile(path, backup_path)
    with path.open("w", encoding="utf-8") as handle:
        for row in valid_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True, [str(backup_path)]


def _infer_metadata(
    *,
    attachment_root: Path,
    descriptor: dict[str, Any] | None,
    attachment: dict[str, Any] | None,
    inbox_binding: dict[str, Any] | None,
    workspace_root: Path,
) -> dict[str, Any]:
    provider_id = (
        (descriptor or {}).get("provider_id")
        or (attachment or {}).get("provider_id")
        or (inbox_binding or {}).get("provider_id")
        or attachment_root.parent.parent.name
    )
    provider_profile = (
        (descriptor or {}).get("provider_profile")
        or (attachment or {}).get("provider_profile")
        or (inbox_binding or {}).get("provider_profile")
        or attachment_root.parent.name
    )
    provider_session_id = (
        (descriptor or {}).get("provider_session_id")
        or (attachment or {}).get("provider_session_id")
        or (inbox_binding or {}).get("provider_session_id")
    )
    if not provider_session_id:
        raise ValueError(f"cannot repair {attachment_root}: missing provider_session_id in readable siblings")

    session_uid = (
        (descriptor or {}).get("session_uid")
        or (attachment or {}).get("session_uid")
        or (inbox_binding or {}).get("session_uid")
        or build_session_uid(
            provider_id=provider_id,
            provider_profile=provider_profile,
            provider_session_id=provider_session_id,
        )
    )
    return {
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "provider_session_id": provider_session_id,
        "session_uid": session_uid,
        "workspace_root": str(workspace_root.resolve()),
    }


def repair_workspace(workspace_root: Path) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    attachments_root = workspace_root / ".yggdrasil" / "providers"
    rows: list[dict[str, Any]] = []
    if not attachments_root.exists():
        return {
            "workspace_root": str(workspace_root),
            "repaired_count": 0,
            "error_count": 0,
            "attachments": [],
        }

    for attachment_path in sorted(attachments_root.rglob("session_attachment.v1.json")):
        attachment_root = attachment_path.parent
        descriptor_path = attachment_root / "provider_descriptor.v1.json"
        inbox_binding_path = attachment_root / "inbox_binding.v1.json"
        turn_delta_path = attachment_root / "turn_delta.v1.jsonl"

        descriptor = _read_json_if_valid(descriptor_path, validate_provider_descriptor)
        attachment = _read_json_if_valid(attachment_path, validate_session_attachment)
        inbox_binding = _read_json_if_valid(inbox_binding_path, validate_inbox_binding)

        row = {
            "attachment_root": str(attachment_root),
            "repaired": False,
            "errors": [],
            "backups": [],
        }

        try:
            meta = _infer_metadata(
                attachment_root=attachment_root,
                descriptor=descriptor,
                attachment=attachment,
                inbox_binding=inbox_binding,
                workspace_root=workspace_root,
            )
            now = utc_now_iso()
            inbox_path = (
                (inbox_binding or {}).get("inbox_path")
                or str(
                    provider_inbox_path(
                        workspace_root=workspace_root,
                        provider_id=meta["provider_id"],
                        provider_profile=meta["provider_profile"],
                        provider_session_id=meta["provider_session_id"],
                    )
                )
            )

            repaired_descriptor = {
                "schema_version": "provider_descriptor.v1",
                "provider_id": meta["provider_id"],
                "provider_profile": meta["provider_profile"],
                "provider_session_id": meta["provider_session_id"],
                "session_uid": meta["session_uid"],
                "adapter_mode": (descriptor or {}).get("adapter_mode") or "skill_generated",
                "generated_at": (descriptor or {}).get("generated_at") or now,
                "generated_by": (descriptor or {}).get("generated_by") or "yggdrasil-skill-bootstrap",
                "workspace_root": meta["workspace_root"],
                "capabilities": (descriptor or {}).get("capabilities") or DEFAULT_CAPABILITIES,
                "provider_extras": (descriptor or {}).get("provider_extras") or {},
            }
            validate_provider_descriptor(repaired_descriptor)

            repaired_attachment = {
                "schema_version": "session_attachment.v1",
                "provider_id": meta["provider_id"],
                "provider_profile": meta["provider_profile"],
                "provider_session_id": meta["provider_session_id"],
                "session_uid": meta["session_uid"],
                "origin_kind": (attachment or {}).get("origin_kind") or "provider-thread",
                "origin_locator": (attachment or {}).get("origin_locator") or {"provider_session_id": meta["provider_session_id"]},
                "update_mode": (attachment or {}).get("update_mode") or "push-delta",
                "created_at": (attachment or {}).get("created_at") or now,
                "attachment_root": str(attachment_root),
                "workspace_root": meta["workspace_root"],
                "capabilities": (attachment or {}).get("capabilities") or DEFAULT_ATTACHMENT_CAPABILITIES,
                "expires_at": (attachment or {}).get("expires_at"),
            }
            validate_session_attachment(repaired_attachment)

            repaired_inbox_binding = {
                "schema_version": "inbox_binding.v1",
                "provider_id": meta["provider_id"],
                "provider_profile": meta["provider_profile"],
                "provider_session_id": meta["provider_session_id"],
                "session_uid": meta["session_uid"],
                "inbox_mode": (inbox_binding or {}).get("inbox_mode") or "jsonl_file",
                "target_kind": (inbox_binding or {}).get("target_kind") or "session_bound",
                "inbox_path": inbox_path,
                "workspace_root": meta["workspace_root"],
                "created_at": (inbox_binding or {}).get("created_at") or now,
            }
            validate_inbox_binding(repaired_inbox_binding)

            if descriptor != repaired_descriptor:
                descriptor_path.write_text(
                    json.dumps(repaired_descriptor, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                row["repaired"] = True
            if attachment != repaired_attachment:
                attachment_path.write_text(
                    json.dumps(repaired_attachment, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                row["repaired"] = True
            if inbox_binding != repaired_inbox_binding:
                inbox_binding_path.write_text(
                    json.dumps(repaired_inbox_binding, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                row["repaired"] = True

            turn_delta_repaired, backups = _repair_turn_delta_file(turn_delta_path)
            row["repaired"] = row["repaired"] or turn_delta_repaired
            row["backups"].extend(backups)
        except Exception as exc:  # noqa: BLE001
            row["errors"].append(str(exc))

        rows.append(row)

    return {
        "workspace_root": str(workspace_root),
        "repaired_count": sum(1 for row in rows if row["repaired"]),
        "error_count": sum(1 for row in rows if row["errors"]),
        "attachments": rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair OpenYggdrasil attachment artifacts conservatively.")
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
    report = repair_workspace(args.workspace_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"repaired={report['repaired_count']} "
            f"errors={report['error_count']}"
        )
        for row in report["attachments"]:
            status = "repaired" if row["repaired"] else "ok"
            if row["errors"]:
                status = "error"
            print(f"{status}: {row['attachment_root']}")
            for error in row["errors"]:
                print(f"  - {error}")
            for backup in row["backups"]:
                print(f"  - backup: {backup}")
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
