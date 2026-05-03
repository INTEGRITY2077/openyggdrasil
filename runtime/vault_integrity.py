"""
Vault Integrity — 운영 메트릭 수집 + 무결성 해시 검증.

12차 P2: Vault (SOT) PARTIAL→LIVE 승급을 위한 검증 인프라.

Usage:
    python -m runtime.vault_integrity check --vault /path/to/vault
    python -m runtime.vault_integrity stats --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def collect_stats(vault: Path) -> dict:
    """Vault 운영 메트릭 수집 → .vault-meta/stats.json"""
    nodes_dir = vault / "nodes"
    edges_file = vault / "edges.jsonl"

    node_count = 0
    status_dist = {"ACTIVE": 0, "SUPERSEDED": 0, "DRAFT": 0, "ARCHIVED": 0, "UNKNOWN": 0}
    total_size = 0
    hash_map = {}

    if nodes_dir.exists():
        for node_file in sorted(nodes_dir.glob("*.json")):
            node_count += 1
            content = node_file.read_bytes()
            total_size += len(content)
            file_hash = hashlib.sha256(content).hexdigest()
            hash_map[node_file.name] = file_hash

            try:
                node = json.loads(content)
                status = node.get("metadata", {}).get("status", "").upper()
                if status in status_dist:
                    status_dist[status] += 1
                else:
                    status_dist["UNKNOWN"] += 1
            except (json.JSONDecodeError, ValueError):
                status_dist["UNKNOWN"] += 1

    edge_count = 0
    if edges_file.exists():
        edge_count = sum(1 for _ in edges_file.read_text(encoding="utf-8").splitlines() if _.strip())

    stats = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "node_count": node_count,
        "edge_count": edge_count,
        "status_distribution": status_dist,
        "total_size_bytes": total_size,
        "files_hash": hash_map,
    }

    # Write stats
    meta_dir = vault / ".vault-meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    return stats


def check_integrity(vault: Path) -> tuple[bool, list[str]]:
    """무결성 해시 검증 — stats.json과 현재 파일 해시 비교."""
    stats_file = vault / ".vault-meta" / "stats.json"
    if not stats_file.exists():
        # first run: collect stats
        collect_stats(vault)
        return True, ["first_run"]

    try:
        stored = json.loads(stats_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return False, ["stats.json 파싱 실패"]

    stored_hashes = stored.get("files_hash", {})
    issues = []
    nodes_dir = vault / "nodes"

    if nodes_dir.exists():
        for node_file in sorted(nodes_dir.glob("*.json")):
            current_hash = hashlib.sha256(node_file.read_bytes()).hexdigest()
            stored_hash = stored_hashes.get(node_file.name)
            if stored_hash is None:
                issues.append(f"신규 파일: {node_file.name}")
            elif current_hash != stored_hash:
                issues.append(f"해시 불일치: {node_file.name}")

    # Check for deleted files
    current_files = {f.name for f in nodes_dir.glob("*.json")} if nodes_dir.exists() else set()
    for stored_name in stored_hashes:
        if stored_name not in current_files:
            issues.append(f"삭제된 파일: {stored_name}")

    # Update stats after check
    collect_stats(vault)

    return len(issues) == 0, issues


def main():
    parser = argparse.ArgumentParser(description="Vault Integrity — stats + hash check")
    parser.add_argument("action", choices=["check", "stats"], help="check=무결성 검증, stats=메트릭 수집")
    parser.add_argument("--vault", required=True, type=Path, help="Vault 디렉터리 경로")
    args = parser.parse_args()

    if not args.vault.exists():
        print(json.dumps({"status": "error", "error": f"Vault not found: {args.vault}"}))
        sys.exit(1)

    if args.action == "stats":
        stats = collect_stats(args.vault)
        print(json.dumps({"status": "ok", "stats": stats}, ensure_ascii=False))

    elif args.action == "check":
        ok, issues = check_integrity(args.vault)
        print(json.dumps({
            "status": "ok",
            "integrity_ok": ok,
            "issues": issues,
            "issue_count": len(issues),
        }, ensure_ascii=False))
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
