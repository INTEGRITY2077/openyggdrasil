#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_SUFFIX = ".schema.json"
BACKTICK_CONTRACT_RE = re.compile(r"`([^`]+\.v\d+)`")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _iter_scan_files(root: Path, names: list[str]) -> list[Path]:
    files: list[Path] = []
    for name in names:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and ".git" not in item.parts
                and "__pycache__" not in item.parts
            )
    return sorted(files)


def _hits(files: list[Path], needle: str, root: Path) -> list[str]:
    results: list[str] = []
    for path in files:
        text = _read_text(path)
        if needle in text:
            results.append(path.relative_to(root).as_posix())
    return results


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_owner_and_stage(schema_name: str, hit_paths: list[str]) -> tuple[str, str]:
    text = " ".join([schema_name, *hit_paths]).lower()
    if "postman" in text or "mailbox" in text or "delivery" in text or "inbox" in text:
        return "Postman", "postman_delivery"
    if "memory_ticket" in text or "provenance" in text or "promotion" in text or "producer" in text:
        return "MS1", "memory_saver_storage"
    if "retrieval" in text or "support_bundle" in text or "pathfinder" in text or "recall" in text:
        return "MF1", "memory_finder_retrieval"
    if "janitor" in text or "gardener" in text or "lifecycle" in text or "tombstone" in text:
        return "Janitor", "janitor_maintenance"
    if "ptc" in text or "reasoning" in text or "sandbox" in text or "tool" in text:
        return "TST/PTC", "reasoning_or_ptc"
    if "amundsen" in text or "category" in text or "map_" in text or "topography" in text:
        return "Amundsen", "wiki_vault"
    if "provider" in text or "session" in text or "turn_delta" in text:
        return "Provider", "provider_intake"
    if "wiki" in text or "vault" in text or "community" in text:
        return "Runtime", "wiki_vault"
    return "Runtime", "compatibility"


def build_audit(repo_root: Path) -> dict[str, Any]:
    contracts_root = repo_root / "contracts"
    manifest_path = contracts_root / "refinery_manifest.v1.json"
    manifest = _load_json(manifest_path) if manifest_path.exists() else {}
    allowlist = set((manifest.get("declared_interface_allowlist") or {}).keys())
    runtime_files = _iter_scan_files(repo_root, ["runtime", "scripts"])
    doc_files = _iter_scan_files(
        repo_root,
        ["README.md", "README.ko.md", "contracts/README.md", "runtime/README.md"],
    )
    schemas = sorted(contracts_root.glob(f"*{SCHEMA_SUFFIX}"))
    schema_names = {path.name for path in schemas}

    rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    unclassified_orphans: list[str] = []
    declared_without_validation: list[str] = []
    active_flowing = 0

    for path in schemas:
        schema_name = path.name
        stem = schema_name[: -len(SCHEMA_SUFFIX)]
        try:
            schema = _load_json(path)
        except Exception as exc:  # noqa: BLE001 - audit should report all parse failures.
            parse_errors.append({"schema": schema_name, "error": str(exc)})
            schema = {}
        runtime_file_hits = _hits(runtime_files, schema_name, repo_root)
        runtime_stem_hits = _hits(runtime_files, stem, repo_root)
        doc_hits = _hits(doc_files, schema_name, repo_root) + _hits(doc_files, stem, repo_root)
        owner, stage = _infer_owner_and_stage(schema_name, runtime_file_hits + runtime_stem_hits + doc_hits)

        if runtime_file_hits:
            circulation_state = "active_flowing"
            public_status = "active"
            active_flowing += 1
        elif runtime_stem_hits and schema_name in allowlist:
            circulation_state = "declared_interface_not_pressure_tested"
            public_status = "compatibility"
            declared_without_validation.append(schema_name)
        elif runtime_stem_hits:
            circulation_state = "declared_interface_without_manifest_reason"
            public_status = "unclassified"
            unclassified_orphans.append(schema_name)
        elif doc_hits:
            circulation_state = "docs_only_not_active"
            public_status = "legacy_or_docs"
        else:
            circulation_state = "orphan_no_flow"
            public_status = "orphan"
            unclassified_orphans.append(schema_name)

        rows.append(
            {
                "schema": schema_name,
                "schema_id": schema.get("$id", ""),
                "public_status": public_status,
                "circulation_state": circulation_state,
                "owner": owner,
                "pipeline_stage": stage,
                "runtime_schema_file_hits": runtime_file_hits,
                "runtime_schema_version_hits": runtime_stem_hits,
                "doc_hits": sorted(set(doc_hits)),
                "validation_evidence": (
                    "runtime_loads_schema_file"
                    if runtime_file_hits
                    else "manifest_declared_not_active" if schema_name in allowlist else "missing"
                ),
            }
        )

    missing_schema_refs: list[str] = []
    doc_text = "\n".join(_read_text(path) for path in doc_files)
    for contract_name in sorted(set(match.group(1) for match in BACKTICK_CONTRACT_RE.finditer(doc_text))):
        expected = f"{contract_name}.schema.json"
        if expected not in schema_names:
            missing_schema_refs.append(contract_name)

    status = "pass"
    if parse_errors or unclassified_orphans or missing_schema_refs:
        status = "fail"

    return {
        "schema_version": "contract_refinery_audit.v1",
        "status": status,
        "repo_root": str(repo_root),
        "contracts_root": str(contracts_root),
        "schema_count": len(rows),
        "active_flowing_count": active_flowing,
        "declared_not_pressure_tested_count": len(declared_without_validation),
        "parse_errors": parse_errors,
        "unclassified_orphans": sorted(unclassified_orphans),
        "missing_schema_refs_from_docs": missing_schema_refs,
        "contracts": rows,
        "hard_nonclaims": [
            "active_flowing_means_schema_file_is_loaded_by_runtime_not_that_every_live_path_was_executed",
            "declared_interface_not_pressure_tested_is_not_a_public_active_contract",
            "this_audit_does_not_replace_domain_semantic_review",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit public contracts as refinery pipeline pipes.")
    parser.add_argument("--repo-root", default=".", help="OpenYggdrasil public repository root.")
    parser.add_argument("--out", help="Optional JSON output path.")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    audit = build_audit(repo_root)
    output = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = repo_root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if audit["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
