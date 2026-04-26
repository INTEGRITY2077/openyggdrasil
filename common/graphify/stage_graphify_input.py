from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


CORE_FILES = ("SCHEMA.md", "index.md", "log.md")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def collect_latest_queries(queries_dir: Path, limit: int) -> list[Path]:
    if limit <= 0 or not queries_dir.exists():
        return []
    files = [p for p in queries_dir.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def should_exclude(relative_path: Path, patterns: list[str]) -> bool:
    return any(relative_path.match(pattern) for pattern in patterns)


def collect_manifest_files(vault: Path, manifest: dict) -> tuple[list[Path], list[str]]:
    staged: list[Path] = []
    missing: list[str] = []

    for name in manifest.get("core_files", []):
        src = vault / name
        if src.exists() and src.is_file():
            staged.append(src)
        else:
            missing.append(str(src))

    include_globs = manifest.get("include_globs", [])
    exclude_globs = manifest.get("exclude_globs", [])
    for pattern in include_globs:
        for src in sorted(vault.glob(pattern)):
            if not src.is_file():
                continue
            relative = src.relative_to(vault)
            if should_exclude(relative, exclude_globs):
                continue
            staged.append(src)

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in staged:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped, missing


def stage_input(
    vault: Path,
    output: Path,
    latest_queries: int,
    *,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    staged: list[str] = []
    missing: list[str] = []

    if output.exists():
        shutil.rmtree(output)
    ensure_dir(output)

    if manifest_path:
        manifest = load_manifest(manifest_path)
        manifest_files, missing = collect_manifest_files(vault, manifest)
        for src in manifest_files:
            relative = src.relative_to(vault)
            dst = output / relative
            copy_file(src, dst)
            staged.append(str(dst))
    else:
        for name in CORE_FILES:
            src = vault / name
            dst = output / name
            if src.exists():
                copy_file(src, dst)
                staged.append(str(dst))
            else:
                missing.append(str(src))

        queries_dir = vault / "queries"
        for src in collect_latest_queries(queries_dir, latest_queries):
            dst = output / src.name
            copy_file(src, dst)
            staged.append(str(dst))

    return {
        "vault": str(vault),
        "output": str(output),
        "latest_queries": latest_queries,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "staged_count": len(staged),
        "staged_files": staged,
        "missing_files": missing,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage a small Graphify input corpus from the canonical vault."
    )
    parser.add_argument("--vault", required=True, type=Path, help="Canonical vault root")
    parser.add_argument("--output", required=True, type=Path, help="Output folder")
    parser.add_argument(
        "--latest-queries",
        type=int,
        default=1,
        help="How many latest query notes to include",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional Graphify corpus manifest JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = stage_input(
        args.vault.resolve(),
        args.output.resolve(),
        args.latest_queries,
        manifest_path=args.manifest.resolve() if args.manifest else None,
    )
    print("Graphify input staging complete")
    print(f"vault: {result['vault']}")
    print(f"output: {result['output']}")
    if result["manifest_path"]:
        print(f"manifest_path: {result['manifest_path']}")
    print(f"staged_count: {result['staged_count']}")
    if result["missing_files"]:
        print("missing_files:")
        for item in result["missing_files"]:
            print(f"  - {item}")
    print("staged_files:")
    for item in result["staged_files"]:
        print(f"  - {item}")


if __name__ == "__main__":
    main()
