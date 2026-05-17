from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


SAFE_INDEX_CURSOR_SCHEMA_VERSION = "safe_index_cursor.v1"
SAFE_INDEX_CURSOR_RELATIVE_PATH = "_meta/safe_index_cursor.json"


def _normalize_vault_path(value: object, *, vault_root: Path) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    if text.startswith("oy-vault://"):
        return "vault/" + text.removeprefix("oy-vault://").strip("/")
    if text.startswith("vault/"):
        return text
    path = Path(text)
    if path.is_absolute():
        try:
            return "vault/" + path.resolve().relative_to(vault_root.resolve()).as_posix()
        except ValueError:
            return "vault/typed_unavailable/outside-vault"
    return "vault/" + text.lstrip("/")


def load_safe_index_cursor(vault_root: Path) -> dict[str, Any]:
    path = vault_root / SAFE_INDEX_CURSOR_RELATIVE_PATH
    if not path.exists():
        return {
            "schema_version": SAFE_INDEX_CURSOR_SCHEMA_VERSION,
            "status": "not_configured",
            "cursor_path": SAFE_INDEX_CURSOR_RELATIVE_PATH,
            "committed_paths": [],
            "hard_nonclaims": [
                "missing_cursor_does_not_prove_safe_index",
            ],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "schema_version": SAFE_INDEX_CURSOR_SCHEMA_VERSION,
            "status": "invalid",
            "cursor_path": SAFE_INDEX_CURSOR_RELATIVE_PATH,
            "committed_paths": [],
            "hard_nonclaims": [
                "invalid_cursor_does_not_prove_safe_index",
            ],
        }
    if not isinstance(payload, Mapping):
        return {
            "schema_version": SAFE_INDEX_CURSOR_SCHEMA_VERSION,
            "status": "invalid",
            "cursor_path": SAFE_INDEX_CURSOR_RELATIVE_PATH,
            "committed_paths": [],
            "hard_nonclaims": [
                "non_object_cursor_does_not_prove_safe_index",
            ],
        }
    committed = [
        _normalize_vault_path(item, vault_root=vault_root)
        for item in payload.get("committed_paths") or payload.get("safe_paths") or []
    ]
    return {
        **dict(payload),
        "schema_version": str(payload.get("schema_version") or SAFE_INDEX_CURSOR_SCHEMA_VERSION),
        "status": "configured",
        "cursor_path": SAFE_INDEX_CURSOR_RELATIVE_PATH,
        "committed_paths": sorted({item for item in committed if item}),
    }


def evaluate_safe_index_cursor(*, vault_root: Path, source_paths: list[object]) -> dict[str, Any]:
    cursor = load_safe_index_cursor(vault_root)
    checked = [
        _normalize_vault_path(item, vault_root=vault_root)
        for item in source_paths
        if str(item or "").strip()
    ]
    checked = [item for item in checked if item]
    if cursor["status"] != "configured":
        return {
            "schema_version": "safe_index_cursor_check.v1",
            "status": cursor["status"],
            "final_support_allowed": cursor["status"] == "not_configured",
            "cursor_path": cursor["cursor_path"],
            "checked_paths": checked,
            "rejected_paths": [],
            "hard_nonclaims": [
                "not_configured_is_backward_compatibility_not_safe_cursor_proof",
            ],
        }
    committed = set(cursor.get("committed_paths") or [])
    rejected = [path for path in checked if path not in committed]
    status = "inside" if checked and not rejected else "outside" if rejected else "empty"
    return {
        "schema_version": "safe_index_cursor_check.v1",
        "status": status,
        "final_support_allowed": status == "inside",
        "cursor_id": cursor.get("cursor_id"),
        "cursor_path": cursor["cursor_path"],
        "checked_paths": checked,
        "rejected_paths": rejected,
        "committed_path_count": len(committed),
        "hard_nonclaims": [
            "safe_cursor_check_is_not_semantic_alignment",
            "safe_cursor_check_is_not_provider_rejudgment",
        ],
    }


def write_safe_index_cursor(
    *,
    vault_root: Path,
    committed_paths: list[object],
    cursor_id: str,
    source: str,
) -> Path:
    path = vault_root / SAFE_INDEX_CURSOR_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [
        _normalize_vault_path(item, vault_root=vault_root)
        for item in committed_paths
        if str(item or "").strip()
    ]
    payload = {
        "schema_version": SAFE_INDEX_CURSOR_SCHEMA_VERSION,
        "cursor_id": cursor_id,
        "source": source,
        "committed_paths": sorted({item for item in normalized if item}),
        "hard_nonclaims": [
            "cursor_membership_is_not_semantic_truth",
            "cursor_membership_is_not_full_vault_consistency",
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


__all__ = [
    "SAFE_INDEX_CURSOR_RELATIVE_PATH",
    "SAFE_INDEX_CURSOR_SCHEMA_VERSION",
    "evaluate_safe_index_cursor",
    "load_safe_index_cursor",
    "write_safe_index_cursor",
]
