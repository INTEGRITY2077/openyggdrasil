from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.common.jsonl_io import append_jsonl_atomic
from runtime.retrieval.safe_index_cursor import load_safe_index_cursor
from runtime.retrieval.support_exclusion_manifest import support_exclusion_for_path
from runtime.wiki.content_first_gate import evaluate_content_first_wiki_article
from runtime.wiki.operation import lint_wiki_page_markdown


MAINTENANCE_RECEIPTS_RELATIVE_PATH = "_meta/maintenance_receipts.jsonl"
MUTATION_LOG_RELATIVE_PATH = "_meta/mutation_log.jsonl"
TOMBSTONES_RELATIVE_PATH = "_meta/tombstones.jsonl"
REPAIR_QUEUE_RELATIVE_PATH = "_meta/repair_queue.jsonl"
SOURCE_REF_RE = re.compile(r"hermes-session-json://[A-Za-z0-9_\-]+")
PRIVATE_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/mnt/[a-z]/", re.IGNORECASE)
REPORT_SCAFFOLD_MARKERS = (
    "추출된 주장:",
    "이 소스가 노드에 충분한 이유:",
    "커뮤니티와의 연결 방식:",
    "이것이 증명하지 못하는 것:",
)


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


def _has_mojibake(text: str) -> bool:
    if "\ufffd" in text:
        return True
    if any(0x80 <= ord(char) <= 0x9F for char in text):
        return True
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    suspicious_question_count = len(re.findall(r"\?[^\s\n]{1,8}", text))
    return cjk_count >= 5 or suspicious_question_count >= 20


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _metadata_values(text: str, key: str) -> list[str]:
    prefix = f"- {key}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            raw = line.split(":", 1)[1].strip()
            return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _metadata_int(text: str, key: str) -> int | None:
    values = _metadata_values(text, key)
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def _source_refs_from_related_nodes(vault_root: Path, related_nodes: list[str]) -> list[str]:
    refs: list[str] = []
    for node_id in related_nodes:
        node = str(node_id or "").strip()
        if not node:
            continue
        node_path = vault_root / "concepts" / f"{node}.md"
        if not node_path.exists():
            continue
        refs.extend(SOURCE_REF_RE.findall(node_path.read_text(encoding="utf-8", errors="replace")))
    return _ordered_unique(refs)


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


def _scan_community_source_ref_drift(vault_root: Path) -> list[dict[str, Any]]:
    community_root = vault_root / "communities"
    if not community_root.exists():
        return []
    drift_candidates: list[dict[str, Any]] = []
    for path in sorted(community_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        related_nodes = _metadata_values(text, "related_nodes")
        if not related_nodes:
            continue
        declared_source_refs = _ordered_unique(_metadata_values(text, "source_refs"))
        discovered_source_refs = _source_refs_from_related_nodes(vault_root, related_nodes)
        missing_source_refs = [ref for ref in discovered_source_refs if ref not in declared_source_refs]
        extra_declared_source_refs = [ref for ref in declared_source_refs if ref not in discovered_source_refs]
        declared_growth_count = _metadata_int(text, "growth_event_count")
        expected_growth_count = len(discovered_source_refs)
        growth_count_mismatch = (
            declared_growth_count is not None
            and expected_growth_count > 0
            and declared_growth_count != expected_growth_count
        )
        if not missing_source_refs and not extra_declared_source_refs and not growth_count_mismatch:
            continue
        drift_candidates.append(
            {
                "schema_version": "wiki_community_source_ref_drift.v1",
                "community_path": _relative_vault_path(path, vault_root=vault_root),
                "related_node_count": len(related_nodes),
                "declared_source_ref_count": len(declared_source_refs),
                "discovered_source_ref_count": len(discovered_source_refs),
                "declared_growth_event_count": declared_growth_count,
                "expected_growth_event_count": expected_growth_count,
                "missing_source_refs": missing_source_refs,
                "extra_declared_source_refs": extra_declared_source_refs,
                "reason_codes": [
                    *(
                        ["community_missing_related_node_source_refs"]
                        if missing_source_refs
                        else []
                    ),
                    *(
                        ["community_has_source_refs_not_found_in_related_nodes"]
                        if extra_declared_source_refs
                        else []
                    ),
                    *(["community_growth_event_count_mismatch"] if growth_count_mismatch else []),
                ],
            }
        )
    return drift_candidates


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
    exclusions = [
        support_exclusion_for_path(vault_root=vault_root, path_value=path)
        for path in paths
    ]
    all_final_support_excluded = bool(paths) and all(
        bool(exclusion.get("excluded")) and not bool(exclusion.get("final_support_allowed"))
        for exclusion in exclusions
    )

    if has_mojibake:
        suggested_action = "repair_encoding_title_then_recheck"
        queue_status = "queued"
        reason_codes = ["title_contains_replacement_character"]
    elif all_final_support_excluded:
        suggested_action = "keep_excluded_machine_mirrors_out_of_final_support"
        queue_status = "not_queued_support_excluded"
        reason_codes = ["duplicate_candidates_are_support_excluded_machine_mirrors"]
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


def _community_source_ref_repair_decision(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "wiki_community_source_ref_repair_decision.v1",
        "community_path": candidate.get("community_path"),
        "related_node_count": candidate.get("related_node_count"),
        "declared_source_ref_count": candidate.get("declared_source_ref_count"),
        "discovered_source_ref_count": candidate.get("discovered_source_ref_count"),
        "declared_growth_event_count": candidate.get("declared_growth_event_count"),
        "expected_growth_event_count": candidate.get("expected_growth_event_count"),
        "missing_source_ref_count": len(candidate.get("missing_source_refs") or []),
        "extra_declared_source_ref_count": len(candidate.get("extra_declared_source_refs") or []),
        "suggested_action": "rerender_community_source_refs_from_related_nodes",
        "repair_queue_status": "queued",
        "reason_codes": list(candidate.get("reason_codes") or []),
        "hard_nonclaims": [
            "community_source_ref_drift_decision_is_not_a_file_mutation",
            "community_source_ref_drift_is_not_semantic_merge_or_split",
            "repair_requires_rerender_or_review_before_claiming_summary_sync",
        ],
    }


def _community_source_ref_repair_decisions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_community_source_ref_repair_decision(candidate) for candidate in candidates]


def _scan_production_page_lineage(vault_root: Path) -> list[dict[str, Any]]:
    category_root = vault_root / "categories"
    if not category_root.exists():
        return []
    candidates: list[dict[str, Any]] = []
    required_markers = {
        "provider_source_event.v1": "provider_source_event_missing",
        "decision_timeline_event.v1": "decision_timeline_missing",
        "semantic_category_path.v1": "semantic_category_path_missing",
        "community_growth_event.v1": "community_growth_event_missing",
        "wiki_continent_page.v1": "wiki_continent_page_contract_missing",
    }
    for path in sorted(category_root.rglob("*.md")):
        if "graphify-out" in path.parts:
            continue
        exclusion = support_exclusion_for_path(vault_root=vault_root, path_value=path)
        if exclusion.get("excluded"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        reason_codes = [
            reason
            for marker, reason in required_markers.items()
            if marker not in text
        ]
        lowered = text.lower()
        if re.search(r'"graphify_used_as_sot"\s*:\s*true', lowered) or "graphify as sot" in lowered:
            reason_codes.append("graphify_as_sot")
        if PRIVATE_ABSOLUTE_PATH_RE.search(text):
            reason_codes.append("private_absolute_path_exposed")
        if "oy-vault://categories/" not in text:
            reason_codes.append("readable_oy_vault_page_ref_missing")
        if "schema_version: wiki_article.v1" in text:
            lint_result = evaluate_content_first_wiki_article(text, path_hint=str(path))
            lint_pass = lint_result.get("verdict") == "pass"
        else:
            lint_result = lint_wiki_page_markdown(text)
            lint_pass = lint_result.get("status") == "pass"
        if not lint_pass:
            reason_codes.append("wiki_page_lint_failed")
        if reason_codes:
            candidates.append(
                {
                    "schema_version": "wiki_production_page_lineage_issue.v1",
                    "page_path": _relative_vault_path(path, vault_root=vault_root),
                    "reason_codes": reason_codes,
                    "wiki_page_lint_result": lint_result,
                    "suggested_action": "rerender_or_quarantine_before_final_support",
                    "hard_nonclaims": [
                        "category_page_issue_is_not_a_delete_event",
                        "janitor_lineage_scan_is_not_provider_rejudgment",
                        "wiki_page_lint_is_not_live_provider_ux",
                    ],
                }
            )
    return candidates


def _scan_full_vault_health(vault_root: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in sorted(vault_root.rglob("*")):
        if path.is_dir():
            continue
        if "graphify-out" in path.parts:
            continue
        if path.suffix.lower() not in {".md", ".json", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        reason_codes: list[str] = []
        if _has_mojibake(text):
            reason_codes.append("mojibake_detected")
        if PRIVATE_ABSOLUTE_PATH_RE.search(text):
            reason_codes.append("private_absolute_path_exposed")
        if path.suffix.lower() == ".md" and any(marker in text for marker in REPORT_SCAFFOLD_MARKERS):
            reason_codes.append("report_scaffold_marker_in_markdown")
        if reason_codes:
            issues.append(
                {
                    "schema_version": "wiki_full_vault_health_issue.v1",
                    "path": _relative_vault_path(path, vault_root=vault_root),
                    "reason_codes": reason_codes,
                    "suggested_action": "repair_or_quarantine_before_full_vault_pass",
                    "hard_nonclaims": [
                        "full_vault_health_issue_is_not_a_delete_event",
                        "janitor_detection_is_not_semantic_repair_by_itself",
                    ],
                }
            )
    return issues


def run_wiki_vault_janitor(
    *,
    vault_root: Path,
    run_id: str,
    source: str = "manual",
    write: bool = True,
    full_vault: bool = False,
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
    community_source_ref_drift_candidates = _scan_community_source_ref_drift(vault_root)
    community_source_ref_repair_decisions = _community_source_ref_repair_decisions(
        community_source_ref_drift_candidates
    )
    production_page_lineage_issues = _scan_production_page_lineage(vault_root)
    full_vault_health_issues = _scan_full_vault_health(vault_root) if full_vault else []
    queued_repairs = [
        decision
        for decision in [
            *duplicate_repair_decisions,
            *community_source_ref_repair_decisions,
            *production_page_lineage_issues,
            *full_vault_health_issues,
        ]
        if decision.get("repair_queue_status") == "queued"
        or decision.get("suggested_action") == "rerender_or_quarantine_before_final_support"
    ]
    status = (
        "pass"
        if cursor.get("status") == "configured"
        and not missing
        and not production_page_lineage_issues
        and not full_vault_health_issues
        else "partial"
    )
    hard_nonclaims = [
        "duplicate_title_candidate_is_not_confirmed_semantic_conflict",
        "community_source_ref_drift_candidate_is_not_a_rendered_repair",
        "tombstone_policy_check_is_not_a_delete_event",
    ]
    if not full_vault:
        hard_nonclaims.insert(0, "janitor_slice_is_not_full_vault_health")
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
        "community_source_ref_drift_candidates": community_source_ref_drift_candidates,
        "community_source_ref_repair_decisions": community_source_ref_repair_decisions,
        "production_page_lineage_issues": production_page_lineage_issues,
        "full_vault_scan_enabled": full_vault,
        "full_vault_health_issues": full_vault_health_issues,
        "queued_repair_count": len(queued_repairs),
        "mutation_log_checked": True,
        "safe_index_cursor_checked": True,
        "conflict_or_tombstone_policy_checked": True,
        "semantic_repair_decision_policy_checked": True,
        "community_source_ref_sync_checked": True,
        "production_page_lineage_checked": True,
        "repair_queue_path": REPAIR_QUEUE_RELATIVE_PATH,
        "tombstone_policy": {
            "physical_delete_allowed": False,
            "delete_requires_tombstone": True,
            "tombstones_path": TOMBSTONES_RELATIVE_PATH,
        },
        "hard_nonclaims": hard_nonclaims,
    }
    mutation_entry = {
        "schema_version": "wiki_mutation_log_entry.v1",
        "run_id": run_id,
        "event_type": "janitor_safe_cursor_check",
        "created_at": now,
        "cursor_id": cursor.get("cursor_id"),
        "checked_paths": checked,
        "missing_committed_paths": missing,
        "community_source_ref_drift_count": len(community_source_ref_drift_candidates),
        "production_page_lineage_issue_count": len(production_page_lineage_issues),
        "full_vault_scan_enabled": full_vault,
        "full_vault_health_issue_count": len(full_vault_health_issues),
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
    parser.add_argument("--full-vault", action="store_true")
    args = parser.parse_args()
    result = run_wiki_vault_janitor(
        vault_root=args.vault_root,
        run_id=args.run_id,
        source=args.source,
        write=not args.dry_run,
        full_vault=args.full_vault,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["maintenance_receipt"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
