"""BM25 vault search used by recall workers.

The searchable vault surface is not limited to internal ``concepts/N-*.md``
mirrors. Production-facing category, community, and entity pages must also be
visible to recall, otherwise the wiki continent layer becomes decorative.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path


def _bootstrap_runtime_package_for_direct_script() -> None:
    if __package__:
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_dir = script_dir
    while os.path.basename(runtime_dir) != "runtime":
        parent = os.path.dirname(runtime_dir)
        if parent == runtime_dir:
            return
        runtime_dir = parent
    project_root = os.path.dirname(runtime_dir)
    normalized_runtime_dir = os.path.normcase(os.path.abspath(runtime_dir))
    normalized_project_root = os.path.normcase(os.path.abspath(project_root))
    sys.path[:] = [
        entry
        for entry in sys.path
        if os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_runtime_dir
    ]
    if all(
        os.path.normcase(os.path.abspath(entry or os.curdir)) != normalized_project_root
        for entry in sys.path
    ):
        sys.path[:0] = [project_root]


_bootstrap_runtime_package_for_direct_script()

from runtime.common.error_policy import record_recoverable
from runtime.common.exceptions import RECOVERABLE_RUNTIME_ERRORS

try:
    from rank_bm25 import BM25Okapi

    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


SEARCHABLE_PATTERNS = (
    "concepts/N-*.md",
    "categories/**/*.md",
    "communities/**/*.md",
    "entities/**/*.md",
)


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + len("\n---") :].strip()
    frontmatter: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        if value.startswith("["):
            continue
        frontmatter[key.strip()] = value
    return frontmatter, body


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _iter_searchable_pages(vault: Path) -> list[Path]:
    seen: set[Path] = set()
    pages: list[Path] = []
    for pattern in SEARCHABLE_PATTERNS:
        for page in sorted(vault.glob(pattern)):
            if page in seen or not page.is_file():
                continue
            seen.add(page)
            pages.append(page)
    return pages


def _load_vault_nodes(vault: Path) -> list[dict]:
    nodes: list[dict] = []
    for node_file in _iter_searchable_pages(vault):
        try:
            text = node_file.read_text(encoding="utf-8")
            fm, body = _extract_frontmatter(text)
            rel_path = node_file.relative_to(vault).as_posix()
            title = fm.get("title") or _title_from_body(body, node_file.stem)
            node_id = fm.get("id") or fm.get("node_id") or node_file.stem
            search_text = " ".join(
                item
                for item in (
                    title,
                    fm.get("root_claim", ""),
                    fm.get("semantic_category_path", ""),
                    fm.get("community", ""),
                    body,
                )
                if item
            )
            nodes.append(
                {
                    "node_id": node_id,
                    "title": title,
                    "content": fm.get("content", ""),
                    "metadata": {
                        "status": fm.get("status", "ACTIVE"),
                        "path": rel_path,
                        "page_kind": rel_path.split("/", 1)[0],
                    },
                    "_filename": node_file.stem,
                    "_path": rel_path,
                    "_search_text": search_text,
                }
            )
        except RECOVERABLE_RUNTIME_ERRORS as exc:
            record_recoverable(exc, component="bm25_search", operation="load_vault_node")
            continue
    return nodes


def _node_to_text(node: dict) -> str:
    parts = []
    search_text = node.get("_search_text")
    if search_text:
        parts.append(str(search_text))
    title = node.get("title", node.get("_filename", ""))
    if title:
        parts.append(str(title))
    content = node.get("content", {})
    if isinstance(content, dict):
        text = content.get("text", "")
    else:
        text = str(content) if content else ""
    if text:
        parts.append(text)
    return " ".join(parts)


def _tokenize(text: str) -> list[str]:
    try:
        tokens = text.lower().split()
    except RECOVERABLE_RUNTIME_ERRORS as exc:
        record_recoverable(exc, component="bm25_search", operation="basic_tokenize")
        tokens = []
    try:
        from kiwipiepy import Kiwi

        if not hasattr(_tokenize, "_kiwi"):
            _tokenize._kiwi = Kiwi()
        for token in _tokenize._kiwi.tokenize(text):
            if token.tag in ("NNG", "NNP", "SL", "XR"):
                tokens.append(token.form)
    except ImportError:
        korean = "".join(c for c in text if "\uac00" <= c <= "\ud7a3")
        for index in range(len(korean) - 1):
            tokens.append(korean[index : index + 2])
    try:
        from korean_text.query_expansion import query_expansion_tokens

        tokens.extend(query_expansion_tokens(text))
    except RECOVERABLE_RUNTIME_ERRORS as exc:
        record_recoverable(exc, component="bm25_search", operation="query_expansion")
    return tokens


def bm25_search(vault: Path, query: str, top_k: int = 20) -> list[dict]:
    nodes = _load_vault_nodes(vault)
    if not nodes:
        return []

    corpus = [_node_to_text(node) for node in nodes]
    query_tokens = _tokenize(query)
    tokenized_corpus = [_tokenize(str(text)) for text in corpus]
    if HAS_BM25:
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
    else:
        query_set = {token for token in query_tokens if token}
        scores = []
        for tokens in tokenized_corpus:
            if not tokens or not query_set:
                scores.append(0.0)
                continue
            token_counts: dict[str, int] = {}
            for token in tokens:
                if token in query_set:
                    token_counts[token] = token_counts.get(token, 0) + 1
            overlap = sum(1.0 + math.log(count) for count in token_counts.values())
            scores.append(overlap / math.sqrt(len(tokens)))

    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    results = []
    for idx, score in ranked[:top_k]:
        if score <= 0:
            continue
        node = nodes[idx]
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), dict) else {}
        results.append(
            {
                "node_id": node.get("node_id", node.get("_filename", "")),
                "text": _node_to_text(node)[:500],
                "score": float(score),
                "bm25_score": float(score),
                "score_source": "rank_bm25" if HAS_BM25 else "token_overlap_fallback",
                "metadata": {
                    "node_id": node.get("node_id", node.get("_filename", "")),
                    "title": node.get("title", ""),
                    "status": metadata.get("status", ""),
                    "path": metadata.get("path", ""),
                    "page_kind": metadata.get("page_kind", ""),
                },
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search OpenYggdrasil vault pages.")
    parser.add_argument("--vault", required=True, type=Path, help="Vault directory path.")
    parser.add_argument("--query", required=True, type=str, help="Search query.")
    parser.add_argument("--top-k", type=int, default=20, help="Maximum result count.")
    args = parser.parse_args()

    if not args.vault.exists():
        print(
            json.dumps(
                {
                    "status": "vault_not_found",
                    "error": f"Vault not found: {args.vault}",
                }
            )
        )
        sys.exit(1)

    try:
        results = bm25_search(args.vault, args.query, top_k=args.top_k)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "query": args.query,
                    "result_count": len(results),
                    "results": results,
                },
                ensure_ascii=False,
            )
        )
    except RECOVERABLE_RUNTIME_ERRORS as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
