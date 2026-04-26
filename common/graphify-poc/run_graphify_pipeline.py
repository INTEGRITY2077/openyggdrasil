from __future__ import annotations

import argparse
import json
from pathlib import Path

from extract_graphify_semantic import extract_semantic
from stage_graphify_input import stage_input


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Hermes-friendly Graphify pipeline over a staged canonical corpus."
    )
    parser.add_argument("--vault", required=True, type=Path, help="Canonical vault root")
    parser.add_argument(
        "--sandbox-root",
        required=True,
        type=Path,
        help="Sandbox execution root that contains input corpus, intermediates, and graphify-out",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Override staged input directory (default: <sandbox-root>/input-wiki-small)",
    )
    parser.add_argument(
        "--latest-queries",
        type=int,
        default=3,
        help="How many latest query notes to stage from the canonical vault",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent / "graphify-corpus.manifest.json",
        help="Graphify corpus manifest JSON",
    )
    parser.add_argument(
        "--semantic-json",
        type=Path,
        default=None,
        help="Override semantic extraction JSON path (default: <sandbox-root>/.graphify_semantic.json)",
    )
    parser.add_argument(
        "--directed",
        action="store_true",
        help="Build a directed graph instead of the default undirected graph",
    )
    parser.add_argument(
        "--refresh-semantic",
        action="store_true",
        help="Force semantic regeneration instead of reusing Graphify cache",
    )
    parser.add_argument(
        "--semantic-retries",
        type=int,
        default=3,
        help="Retry count for Hermes semantic extraction when JSON parsing is transiently unstable",
    )
    parser.add_argument(
        "--semantic-retry-delay-seconds",
        type=float,
        default=2.0,
        help="Delay between semantic extraction retries",
    )
    return parser.parse_args()


def run_detect(input_dir: Path, detect_json: Path) -> dict:
    from graphify.detect import detect

    result = detect(input_dir)
    write_json(detect_json, result)
    return result


def run_ast(detect_result: dict, ast_json: Path) -> dict:
    from graphify.extract import collect_files, extract

    code_files: list[Path] = []
    for item in detect_result.get("files", {}).get("code", []):
        path = Path(item)
        if path.is_dir():
            code_files.extend(collect_files(path))
        else:
            code_files.append(path)

    if code_files:
        result = extract(code_files)
    else:
        result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

    write_json(ast_json, result)
    return result


def build_outputs(
    sandbox_root: Path,
    corpus_name: str,
    detect_result: dict,
    ast_result: dict,
    semantic_result: dict,
    *,
    directed: bool = False,
) -> dict:
    from graphify.analyze import god_nodes, suggest_questions, surprising_connections
    from graphify.build import build
    from graphify.cluster import cluster, score_all
    from graphify.export import to_html, to_json
    from graphify.report import generate

    out_dir = sandbox_root / "graphify-out"
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = build([ast_result, semantic_result], directed=directed)
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    questions = suggest_questions(graph, communities, labels)
    token_cost = {
        "input": ast_result.get("input_tokens", 0) + semantic_result.get("input_tokens", 0),
        "output": ast_result.get("output_tokens", 0) + semantic_result.get("output_tokens", 0),
    }

    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detect_result,
        token_cost,
        corpus_name,
        suggested_questions=questions,
    )
    (out_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(graph, communities, str(out_dir / "graph.json"))
    to_html(graph, communities, str(out_dir / "graph.html"), community_labels=labels)

    summary = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "communities": len(communities),
        "god_nodes": gods[:5],
        "surprising_connections": surprises[:5],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    args = parse_args()

    vault = args.vault.resolve()
    sandbox_root = args.sandbox_root.resolve()
    input_dir = (args.input_dir or (sandbox_root / "input-wiki-small")).resolve()

    detect_json = sandbox_root / ".graphify_detect.json"
    ast_json = sandbox_root / ".graphify_ast.json"
    semantic_json = (args.semantic_json or (sandbox_root / ".graphify_semantic.json")).resolve()

    stage_result = stage_input(
        vault,
        input_dir,
        args.latest_queries,
        manifest_path=args.manifest.resolve() if args.manifest else None,
    )
    detect_result = run_detect(input_dir, detect_json)
    ast_result = run_ast(detect_result, ast_json)
    extract_semantic(
        sandbox_root=sandbox_root,
        detect_json=detect_json,
        semantic_json=semantic_json,
        refresh=args.refresh_semantic,
        retries=args.semantic_retries,
        retry_delay_seconds=args.semantic_retry_delay_seconds,
    )
    semantic_result = load_json(semantic_json)
    summary = build_outputs(
        sandbox_root,
        corpus_name=input_dir.name,
        detect_result=detect_result,
        ast_result=ast_result,
        semantic_result=semantic_result,
        directed=args.directed,
    )

    result = {
        "vault": str(vault),
        "sandbox_root": str(sandbox_root),
        "input_dir": str(input_dir),
        "manifest": str(args.manifest.resolve()) if args.manifest else None,
        "staged_count": stage_result["staged_count"],
        "summary": summary,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
