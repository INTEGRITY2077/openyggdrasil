from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from harness_common import utc_now_iso
from mailbox_status import write_mailbox_status
from mailbox_store import (
    MAILBOX_ARCHIVE_ROOT,
    archive_namespace,
    delivery_target_for,
    legacy_global_inbox_paths,
    mailbox_paths,
    namespace_exists,
    read_claims,
    read_messages,
)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    path.write_bytes(payload)


def build_namespace_status(namespace: str) -> Dict[str, Any]:
    paths = mailbox_paths(namespace=namespace)
    status = write_mailbox_status(namespace=namespace)
    return {
        "namespace": namespace,
        "exists": namespace_exists(namespace),
        "root": str(paths["root"]),
        "messages_path": str(paths["messages_path"]),
        "claims_path": str(paths["claims_path"]),
        "inbox_root": str(paths["inbox_root"]),
        "operator_root": str(paths["operator_root"]),
        "status": status,
    }


def archive_namespace_once(namespace: str, reason: str | None = None) -> Dict[str, Any]:
    destination = archive_namespace(namespace=namespace, reason=reason)
    return {
        "archived": True,
        "namespace": namespace,
        "destination": str(destination),
    }


def archive_records(
    *,
    namespace: str,
    record_type: str,
    rows: List[Dict[str, Any]],
) -> Path | None:
    if not rows:
        return None
    MAILBOX_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    archive_path = MAILBOX_ARCHIVE_ROOT / (
        f"{utc_now_iso().replace(':', '').replace('+00:00', 'Z')}-{namespace}-{record_type}.jsonl"
    )
    write_jsonl(archive_path, rows)
    return archive_path


def merge_rows_by_message_id(
    path: Path,
    rows: List[Dict[str, Any]],
) -> int:
    existing_rows = read_messages(path=path)
    merged_by_id: Dict[str, Dict[str, Any]] = {
        str(row.get("message_id") or uuid): row
        for uuid, row in enumerate(existing_rows)
    }
    added = 0
    for row in rows:
        message_id = str(row.get("message_id") or "")
        if message_id and message_id in merged_by_id:
            continue
        key = message_id or f"anonymous::{len(merged_by_id)}"
        merged_by_id[key] = row
        added += 1
    write_jsonl(path, list(merged_by_id.values()))
    return added


def migrate_legacy_global_inbox_once(namespace: str) -> Dict[str, Any]:
    paths = mailbox_paths(namespace=namespace)
    if not paths["root"].exists():
        return {
            "namespace": namespace,
            "migrated": False,
            "reason": "namespace_missing",
        }

    legacy_paths = legacy_global_inbox_paths(namespace=namespace)
    migrated_rows_by_destination: Dict[Path, List[Dict[str, Any]]] = {}
    archived_rows: List[Dict[str, Any]] = []
    lane_counts = {
        "hermes_inbox": 0,
        "operator_lane": 0,
    }

    for legacy_path in legacy_paths:
        rows = read_messages(path=legacy_path)
        if not rows:
            legacy_path.unlink(missing_ok=True)
            continue
        archived_rows.extend(rows)
        for row in rows:
            lane, destination = delivery_target_for(row, namespace=namespace)
            lane_counts[lane] += 1
            migrated_rows_by_destination.setdefault(destination, []).append(row)
        legacy_path.unlink(missing_ok=True)

    moved_rows = 0
    for destination, rows in migrated_rows_by_destination.items():
        moved_rows += merge_rows_by_message_id(destination, rows)

    archive_path = archive_records(
        namespace=namespace,
        record_type="legacy-global-inbox",
        rows=archived_rows,
    )
    status = write_mailbox_status(namespace=namespace)

    return {
        "namespace": namespace,
        "migrated": True,
        "legacy_files_found": len(legacy_paths),
        "legacy_rows_found": len(archived_rows),
        "rows_written": moved_rows,
        "hermes_inbox_rows": lane_counts["hermes_inbox"],
        "operator_lane_rows": lane_counts["operator_lane"],
        "archive_path": str(archive_path) if archive_path else None,
        "status": status,
    }


def compact_claims_once(namespace: str) -> Dict[str, Any]:
    paths = mailbox_paths(namespace=namespace)
    if not paths["root"].exists():
        return {
            "namespace": namespace,
            "compacted": False,
            "reason": "namespace_missing",
        }

    messages = read_messages(namespace=namespace)
    claims = read_claims(namespace=namespace)
    live_message_ids = {message.get("message_id") for message in messages}

    dedup_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    orphan_claims: List[Dict[str, Any]] = []
    duplicate_claims: List[Dict[str, Any]] = []

    for claim in claims:
        message_id = str(claim.get("message_id") or "")
        if message_id not in live_message_ids:
            orphan_claims.append(claim)
            continue
        key = (
            message_id,
            str(claim.get("consumer") or ""),
            str(claim.get("claim_type") or ""),
        )
        previous = dedup_index.get(key)
        if previous is not None:
            duplicate_claims.append(previous)
        dedup_index[key] = claim

    compacted_claims = list(dedup_index.values())
    write_jsonl(paths["claims_path"], compacted_claims)

    orphan_archive = archive_records(namespace=namespace, record_type="orphan-claims", rows=orphan_claims)
    duplicate_archive = archive_records(namespace=namespace, record_type="duplicate-claims", rows=duplicate_claims)
    status = write_mailbox_status(namespace=namespace)

    return {
        "namespace": namespace,
        "compacted": True,
        "before_claims": len(claims),
        "after_claims": len(compacted_claims),
        "orphan_claims_removed": len(orphan_claims),
        "duplicate_claims_removed": len(duplicate_claims),
        "orphan_archive": str(orphan_archive) if orphan_archive else None,
        "duplicate_archive": str(duplicate_archive) if duplicate_archive else None,
        "status": status,
    }


def packet_is_stale(
    message: Dict[str, Any],
    *,
    delivered_ids: set[str],
    now: datetime,
    max_packet_age: timedelta,
) -> bool:
    if message.get("kind") != "packet":
        return False
    message_id = str(message.get("message_id") or "")
    if message_id not in delivered_ids:
        return False
    created_at = parse_timestamp(message.get("created_at"))
    if created_at is None:
        return False

    ttl_seconds = message.get("ttl_seconds")
    if isinstance(ttl_seconds, int) and ttl_seconds >= 0:
        return now >= created_at + timedelta(seconds=ttl_seconds)

    return now - created_at >= max_packet_age


def rewrite_lane_without_message_ids(root: Path, stale_ids: set[str]) -> int:
    removed_rows = 0
    if not root.exists():
        return removed_rows
    for inbox_path in root.rglob("*.jsonl"):
        rows = read_messages(path=inbox_path)
        kept = [row for row in rows if row.get("message_id") not in stale_ids]
        removed_rows += len(rows) - len(kept)
        write_jsonl(inbox_path, kept)
    return removed_rows


def gc_packets_once(
    namespace: str,
    *,
    max_packet_age_hours: float,
    now: datetime | None = None,
) -> Dict[str, Any]:
    paths = mailbox_paths(namespace=namespace)
    if not paths["root"].exists():
        return {
            "namespace": namespace,
            "gc_ran": False,
            "reason": "namespace_missing",
        }

    messages = read_messages(namespace=namespace)
    claims = read_claims(namespace=namespace)
    delivered_ids = {
        str(claim.get("message_id"))
        for claim in claims
        if claim.get("consumer") == "postman" and claim.get("claim_type") == "push_delivered"
    }
    if now is None:
        now = datetime.now(timezone.utc)
    max_packet_age = timedelta(hours=max_packet_age_hours)

    stale_packets = [
        message
        for message in messages
        if packet_is_stale(message, delivered_ids=delivered_ids, now=now, max_packet_age=max_packet_age)
    ]
    stale_ids = {str(message.get("message_id")) for message in stale_packets}
    kept_messages = [message for message in messages if str(message.get("message_id")) not in stale_ids]
    kept_claims = [claim for claim in claims if str(claim.get("message_id")) not in stale_ids]

    removed_inbox_rows = rewrite_lane_without_message_ids(paths["inbox_root"], stale_ids)
    removed_operator_rows = rewrite_lane_without_message_ids(paths["operator_root"], stale_ids)
    write_jsonl(paths["messages_path"], kept_messages)
    write_jsonl(paths["claims_path"], kept_claims)

    packet_archive = archive_records(namespace=namespace, record_type="stale-packets", rows=stale_packets)
    claim_archive = archive_records(
        namespace=namespace,
        record_type="stale-packet-claims",
        rows=[claim for claim in claims if str(claim.get("message_id")) in stale_ids],
    )
    status = write_mailbox_status(namespace=namespace)

    return {
        "namespace": namespace,
        "gc_ran": True,
        "max_packet_age_hours": max_packet_age_hours,
        "before_messages": len(messages),
        "after_messages": len(kept_messages),
        "before_claims": len(claims),
        "after_claims": len(kept_claims),
        "stale_packets_removed": len(stale_packets),
        "inbox_rows_removed": removed_inbox_rows,
        "operator_rows_removed": removed_operator_rows,
        "packet_archive": str(packet_archive) if packet_archive else None,
        "claim_archive": str(claim_archive) if claim_archive else None,
        "status": status,
    }


def gc_namespace_once(
    namespace: str,
    *,
    max_packet_age_hours: float,
    now: datetime | None = None,
) -> Dict[str, Any]:
    migration_summary = migrate_legacy_global_inbox_once(namespace)
    claim_summary = compact_claims_once(namespace)
    packet_summary = gc_packets_once(namespace, max_packet_age_hours=max_packet_age_hours, now=now)
    return {
        "namespace": namespace,
        "legacy_global_migration": migration_summary,
        "claim_compaction": claim_summary,
        "packet_gc": packet_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mailbox namespace hygiene and archival utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("namespace-status")
    status_parser.add_argument("--namespace", required=True)

    archive_parser = subparsers.add_parser("archive-namespace")
    archive_parser.add_argument("--namespace", required=True)
    archive_parser.add_argument("--reason", default=None)

    compact_parser = subparsers.add_parser("compact-claims")
    compact_parser.add_argument("--namespace", required=True)

    packet_gc_parser = subparsers.add_parser("gc-packets")
    packet_gc_parser.add_argument("--namespace", required=True)
    packet_gc_parser.add_argument("--max-packet-age-hours", type=float, default=24.0)

    namespace_gc_parser = subparsers.add_parser("gc-namespace")
    namespace_gc_parser.add_argument("--namespace", required=True)
    namespace_gc_parser.add_argument("--max-packet-age-hours", type=float, default=24.0)

    migrate_global_parser = subparsers.add_parser("migrate-legacy-global")
    migrate_global_parser.add_argument("--namespace", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "namespace-status":
        payload = build_namespace_status(args.namespace)
    elif args.command == "archive-namespace":
        payload = archive_namespace_once(args.namespace, args.reason)
    elif args.command == "compact-claims":
        payload = compact_claims_once(args.namespace)
    elif args.command == "gc-packets":
        payload = gc_packets_once(args.namespace, max_packet_age_hours=args.max_packet_age_hours)
    elif args.command == "gc-namespace":
        payload = gc_namespace_once(args.namespace, max_packet_age_hours=args.max_packet_age_hours)
    elif args.command == "migrate-legacy-global":
        payload = migrate_legacy_global_inbox_once(args.namespace)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
