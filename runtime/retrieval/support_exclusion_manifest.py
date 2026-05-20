from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any, Mapping


SUPPORT_EXCLUSION_SCHEMA_VERSION = "support_exclusion_manifest.v1"
SUPPORT_EXCLUSION_RELATIVE_PATH = "_meta/support_exclusion_manifest.json"
BUILTIN_FINAL_SUPPORT_EXCLUSION_PATTERNS = (
    {
        "pattern": "vault/concepts/N-*.md",
        "exclusion_state": "machine_mirror",
        "final_support_allowed": False,
        "reason_codes": [
            "concept_hash_node_is_internal_machine_mirror",
            "reader_support_must_use_readable_wiki_page_or_source_cell",
        ],
    },
    {
        "pattern": "vault/concepts/PRN-*.md",
        "exclusion_state": "machine_mirror",
        "final_support_allowed": False,
        "reason_codes": [
            "provenance_ring_node_is_internal_machine_mirror",
            "reader_support_must_use_readable_wiki_page_or_source_cell",
        ],
    },
)


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


def load_support_exclusion_manifest(vault_root: Path) -> dict[str, Any]:
    path = vault_root / SUPPORT_EXCLUSION_RELATIVE_PATH
    if not path.exists():
        return {
            "schema_version": SUPPORT_EXCLUSION_SCHEMA_VERSION,
            "status": "not_configured",
            "manifest_path": SUPPORT_EXCLUSION_RELATIVE_PATH,
            "entries": [],
            "patterns": [],
            "hard_nonclaims": [
                "missing_support_exclusion_manifest_does_not_prove_support_safety",
            ],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "schema_version": SUPPORT_EXCLUSION_SCHEMA_VERSION,
            "status": "invalid",
            "manifest_path": SUPPORT_EXCLUSION_RELATIVE_PATH,
            "entries": [],
            "patterns": [],
            "hard_nonclaims": [
                "invalid_support_exclusion_manifest_blocks_no_paths_by_itself",
            ],
        }
    if not isinstance(payload, Mapping):
        return {
            "schema_version": SUPPORT_EXCLUSION_SCHEMA_VERSION,
            "status": "invalid",
            "manifest_path": SUPPORT_EXCLUSION_RELATIVE_PATH,
            "entries": [],
            "patterns": [],
            "hard_nonclaims": [
                "non_object_support_exclusion_manifest_blocks_no_paths_by_itself",
            ],
        }
    entries = [dict(item) for item in payload.get("entries") or [] if isinstance(item, Mapping)]
    patterns = [dict(item) for item in payload.get("patterns") or [] if isinstance(item, Mapping)]
    patterns = [*patterns, *[dict(item) for item in BUILTIN_FINAL_SUPPORT_EXCLUSION_PATTERNS]]
    return {
        **dict(payload),
        "schema_version": str(payload.get("schema_version") or SUPPORT_EXCLUSION_SCHEMA_VERSION),
        "status": "configured",
        "manifest_path": SUPPORT_EXCLUSION_RELATIVE_PATH,
        "entries": entries,
        "patterns": patterns,
    }


def support_exclusion_for_path(*, vault_root: Path, path_value: object) -> dict[str, Any]:
    manifest = load_support_exclusion_manifest(vault_root)
    normalized = _normalize_vault_path(path_value, vault_root=vault_root)
    if not normalized or manifest.get("status") != "configured":
        return {
            "schema_version": "support_exclusion_check.v1",
            "excluded": False,
            "path": normalized,
            "manifest_status": manifest.get("status"),
            "reason_codes": [],
        }

    for entry in manifest.get("entries") or []:
        entry_path = _normalize_vault_path(entry.get("path"), vault_root=vault_root)
        if entry_path == normalized and entry.get("final_support_allowed") is False:
            return {
                "schema_version": "support_exclusion_check.v1",
                "excluded": True,
                "path": normalized,
                "manifest_status": manifest.get("status"),
                "exclusion_state": str(entry.get("exclusion_state") or "excluded"),
                "final_support_allowed": False,
                "reason_codes": list(entry.get("reason_codes") or []),
                "entry": entry,
            }

    for pattern_entry in manifest.get("patterns") or []:
        pattern = str(pattern_entry.get("pattern") or "").strip().replace("\\", "/")
        if not pattern:
            continue
        if fnmatch.fnmatch(normalized, pattern) and pattern_entry.get("final_support_allowed") is False:
            return {
                "schema_version": "support_exclusion_check.v1",
                "excluded": True,
                "path": normalized,
                "manifest_status": manifest.get("status"),
                "exclusion_state": str(pattern_entry.get("exclusion_state") or "excluded_by_pattern"),
                "final_support_allowed": False,
                "reason_codes": list(pattern_entry.get("reason_codes") or []),
                "entry": pattern_entry,
            }

    return {
        "schema_version": "support_exclusion_check.v1",
        "excluded": False,
        "path": normalized,
        "manifest_status": manifest.get("status"),
        "reason_codes": [],
    }


def is_final_support_excluded(*, vault_root: Path, path_value: object) -> bool:
    return bool(support_exclusion_for_path(vault_root=vault_root, path_value=path_value).get("excluded"))


__all__ = [
    "SUPPORT_EXCLUSION_RELATIVE_PATH",
    "SUPPORT_EXCLUSION_SCHEMA_VERSION",
    "is_final_support_excluded",
    "load_support_exclusion_manifest",
    "support_exclusion_for_path",
]
