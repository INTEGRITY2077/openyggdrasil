from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hermes-friendly wrapper for Graphify graph queries."
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("graphify-out/graph.json"),
        help="Path to graph.json (default: ./graphify-out/graph.json)",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Run graphify query")
    query_parser.add_argument("question", help="Query string")
    query_parser.add_argument("--dfs", action="store_true", help="Use DFS traversal")
    query_parser.add_argument("--budget", type=int, default=None, help="Optional token budget")

    path_parser = subparsers.add_parser("path", help="Run graphify shortest-path query")
    path_parser.add_argument("source", help="Source node label")
    path_parser.add_argument("target", help="Target node label")

    explain_parser = subparsers.add_parser("explain", help="Explain one graph node")
    explain_parser.add_argument("node", help="Node label")

    return parser


def run_command(args: list[str]) -> int:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    graph = args.graph.resolve()
    if not graph.exists():
        raise SystemExit(f"Missing graph file: {graph}")

    command = [sys.executable, "-m", "graphify", args.command]

    if args.command == "query":
        command.append(args.question)
        if args.dfs:
            command.append("--dfs")
        if args.budget is not None:
            command.extend(["--budget", str(args.budget)])
    elif args.command == "path":
        command.extend([args.source, args.target])
    elif args.command == "explain":
        command.append(args.node)
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    command.extend(["--graph", str(graph)])
    return run_command(command)


if __name__ == "__main__":
    raise SystemExit(main())
