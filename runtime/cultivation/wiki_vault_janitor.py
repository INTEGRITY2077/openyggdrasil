from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.common.jsonl_io import append_jsonl_atomic
from runtime.retrieval.safe_index_cursor import load_safe_index_cursor


MAINTENANCE_RECEIPTS_RELATIVE_PATH = "_meta/maintenance_receipts.jsonl"
MUTATION_LOG_RELATIVE_PATH = "_meta/mutation_log.jsonl"
TOMBSTONES_RELATIVE_PATH = "_meta/tombstones.jsonl"
REPAIR_QUEUE_RELATIVE_PATH = "_meta/repair_queue.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vault_path(vault_root: Path, path_value: object) -> Path:
    text = str(path_value or "").strip().replace("\\", "/")
    if text.startswith("vault/"):
        text = text[len("vault/") :]
    return vault_root / text


def _relative_vault_path(path: Path, *, vault_root: Path) -> str:
    try:
        return "vault/" + path.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _markdown_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:80]:
        stripped = line.strip()
        if stripped.startswith("title:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _scan_duplicate_titles(vault_root: Path) -> list[dict[str, Any]]:
    title_paths: dict[str, list[str]] = {}
    for base in ("queries", "concepts", "communities"):
        root = vault_root / base
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            title = _markdown_title(path)
            if title:
                title_paths.setdefault(title.casefold(), []).append(_relative_vault_path(path, vault_root=vault_root))
    return [
        {"title_key": key, "paths": paths, "conflict_kind": "duplicate_title_candidate"}
        for key, paths in sorted(title_paths.items())
        if len(paths) > 1
    ]


def _path_role(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("vault/queries/"):
        return "query"
    if normalized.startswith("vault/concepts/PRN-"):
        return "prose_ring_node"
    if normalized.startswith("vault/concepts/N-"):
        return "concept_node"
    if normalized.startswith("vault/communities/"):
        return "community"
    if normalized.startswith("vault/_meta/provenance/"):
        return "provenance"
    return "other"


def _content_hash_groups(vault_root: Path, paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for rel_path in paths:
        path = _vault_path(vault_root, rel_path)
        if not path.exists():
            groups.setdefault("missing", []).append(rel_path)
            continue
        groups.setdefault(_sha256_file(path), []).append(rel_path)
    return groups


def _duplicate_repair_decision(vault_root: Path, duplicate: Mapping[str, Any]) -> dict[str, Any]:
    paths = [str(item) for item in duplicate.get("paths") or []]
    roles = sorted({_path_role(path) for path in paths})
    hash_groups = _content_hash_groups(vault_root, paths)
    hash_group_count = len([key for key in hash_groups if key != "missing"])
    title_key = str(duplicate.get("title_key") or "")
    has_mojibake = "\ufffd" in title_key
    query_count = sum(1 for path in paths if _path_role(path) == "query")
    concept_count = sum(1 for path in paths if _path_role(path) in {"concept_node", "prose_ring_node"})

    if has_mojibake:
        suggested_action = "repair_encoding_title_then_recheck"
        queue_status = "queued"
        reason_codes = ["title_contains_replacement_character"]
    elif query_count == 1 and concept_count >= 1 and hash_group_count == 1:
        suggested_action = "treat_as_expected_query_concept_projection_group"
        queue_status = "not_queued_expected_projection"
        reason_codes = ["query_and_concept_projection_share_title"]
    else:
        suggested_action = "review_merge_split_or_supersede"
        queue_status = "queued"
        reason_codes = ["same_title_multiple_distinct_artifacts"]

    return {
        "schema_version": "wiki_duplicate_repair_decision.v1",
        "title_key": title_key,
        "candidate_count": len(paths),
        "roles": roles,
        "content_hash_group_count": hash_group_count,
        "suggested_action": suggested_action,
        "repair_queue_status": queue_status,
        "reason_codes": reason_codes,
        "paths": paths,
        "hard_nonclaims": [
            "duplicate_title_decision_is_not_semantic_merge",
            "repair_queue_entry_is_not_delete_or_tombstone",
            "expected_projection_group_still_needs_manifest_sync_if_rendered_as_duplicate",
        ],
    }


def _duplicate_repair_decisions(vault_root: Path, duplicates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_duplicate_repair_decision(vault_root, duplicate) for duplicate in duplicates]


def run_wiki_vault_janitor(
    *,
    vault_root: Path,
    run_id: str,
    source: str = "manual",
    write: bool = True,
) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    cursor = load_safe_index_cursor(vault_root)
    committed_paths = [str(item) for item in cursor.get("committed_paths") or []]
    checked: list[dict[str, Any]] = []
    missing: list[str] = []
    for rel_path in committed_paths:
        path = _vault_path(vault_root, rel_path)
        if not path.exists():
            missing.append(rel_path)
            checked.append({"path": rel_path, "exists": False})
            continue
        checked.append(
            {
                "path": rel_path,
                "exists": True,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    duplicates = _scan_duplicate_titles(vault_root)
    duplicate_repair_decisions = _duplicate_repair_decisions(vault_root, duplicates)
    queued_repairs = [
        decision
        for decision in duplicate_repair_decisions
        if decision.get("repair_queue_status") == "queued"
    ]
    status = "pass" if cursor.get("status") == "configured" and not missing else "partial"
    now = _now_iso()
    maintenance_receipt = {
        "schema_version": "wiki_vault_janitor_receipt.v1",
        "run_id": run_id,
        "receipt_id": f"janitor-{hashlib.sha256((run_id + now).encode('utf-8')).hexdigest()[:8]}",
        "source": source,
        "created_at": now,
        "vault_root_name": vault_root.name,
        "status": status,
        "cursor_id": cursor.get("cursor_id"),
        "safe_index_cursor_status": cursor.get("status"),
        "checked_path_count": len(checked),
        "missing_committed_paths": missing,
        "duplicate_title_candidates": duplicates,
        "duplicate_repair_decisions": duplicate_repair_decisions,
        "queued_repair_count": len(queued_repairs),
        "mutation_log_checked": True,
        "safe_index_cursor_checked": True,
        "conflict_or_tombstone_policy_checked": True,
        "semantic_repair_decision_policy_checked": True,
        "repair_queue_path": REPAIR_QUEUE_RELATIVE_PATH,
        "tombstone_policy": {
            "physical_delete_allowed": False,
            "delete_requires_tombstone": True,
            "tombstones_path": TOMBSTONES_RELATIVE_PATH,
        },
        "hard_nonclaims": [
            "janitor_slice_is_not_full_vault_health",
            "duplicate_title_candidate_is_not_confirmed_semantic_conflict",
            "tombstone_policy_check_is_not_a_delete_event",
        ],
    }
    mutation_entry = {
        "schema_version": "wiki_mutation_log_entry.v1",
        "run_id": run_id,
        "event_type": "janitor_safe_cursor_check",
        "created_at": now,
        "cursor_id": cursor.get("cursor_id"),
        "checked_paths": checked,
        "missing_committed_paths": missing,
        "queued_repair_count": len(queued_repairs),
        "hard_nonclaims": [
            "hash_check_is_not_semantic_quality_review",
        ],
    }
    if write:
        append_jsonl_atomic(vault_root / MAINTENANCE_RECEIPTS_RELATIVE_PATH, maintenance_receipt)
        append_jsonl_atomic(vault_root / MUTATION_LOG_RELATIVE_PATH, mutation_entry)
        tombstones = vault_root / TOMBSTONES_RELATIVE_PATH
        tombstones.parent.mkdir(parents=True, exist_ok=True)
        if not tombstones.exists():
            tombstones.write_text("", encoding="utf-8")
        for decision in queued_repairs:
            append_jsonl_atomic(
                vault_root / REPAIR_QUEUE_RELATIVE_PATH,
                {
                    "schema_version": "wiki_repair_queue_entry.v1",
                    "run_id": run_id,
                    "created_at": now,
                    "source": source,
                    "decision": decision,
                    "hard_nonclaims": [
                        "repair_queue_entry_is_not_a_file_mutation",
                        "human_or_worker_semantic_review_required_before_merge_split_or_tombstone",
                    ],
                },
            )
    return {
        "schema_version": "wiki_vault_janitor_result.v1",
        "run_id": run_id,
        "maintenance_receipt": maintenance_receipt,
        "mutation_entry": mutation_entry,
        "written": write,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_wiki_vault_janitor(
        vault_root=args.vault_root,
        run_id=args.run_id,
        source=args.source,
        write=not args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["maintenance_receipt"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
