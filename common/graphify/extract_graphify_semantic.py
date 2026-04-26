from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


DEFAULT_HERMES_BIN = Path(os.getenv("HERMES_BIN", "hermes"))
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 2.0


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def graphify_files(detect_result: dict) -> list[str]:
    files = detect_result.get("files", {})
    supported = []
    for key in ("document", "paper"):
        supported.extend(files.get(key, []))
    return supported


def build_prompt(relative_path: str, content: str) -> str:
    return f"""Read the file at {relative_path} and extract a small knowledge graph.

Return ONLY a single JSON object with this exact top-level shape:
{{"nodes":[],"edges":[],"hyperedges":[],"input_tokens":0,"output_tokens":0}}

Rules:
- file_type must be document.
- source_file must be exactly {relative_path}
- Keep the extraction concise and useful for Graphify.
- Prefer 3-12 nodes maximum for one file.
- Node ids must be stable snake_case strings.
- Every node must include:
  id, label, file_type, source_file, source_location, source_url, captured_at, author, contributor
- Every edge must include:
  source, target, relation, confidence, confidence_score, source_file, source_location, weight
- confidence must be one of: EXTRACTED, INFERRED, AMBIGUOUS
- Use EXTRACTED only for relationships explicit in the file.
- Use INFERRED sparingly for reasonable implied links.
- Keep hyperedges optional. Use them only if 3+ nodes clearly participate in one shared concept.
- Do not output markdown fences.
- Output valid JSON only.

File content:
```markdown
{content}
```"""


def extract_json_object(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in Hermes output")
    return json.loads(text[start : end + 1])


def normalize_node(node: dict, *, relative_path: str) -> dict:
    return {
        "id": str(node.get("id", "")).strip(),
        "label": str(node.get("label", "")).strip(),
        "file_type": node.get("file_type") or "document",
        "source_file": relative_path,
        "source_location": node.get("source_location"),
        "source_url": node.get("source_url"),
        "captured_at": node.get("captured_at"),
        "author": node.get("author"),
        "contributor": node.get("contributor"),
    }


def normalize_edge(edge: dict, *, relative_path: str) -> dict:
    confidence = str(edge.get("confidence", "INFERRED")).upper()
    if confidence not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
        confidence = "INFERRED"
    try:
        confidence_score = float(edge.get("confidence_score", 0.7))
    except Exception:
        confidence_score = 0.7
    try:
        weight = float(edge.get("weight", 1.0))
    except Exception:
        weight = 1.0
    return {
        "source": str(edge.get("source", "")).strip(),
        "target": str(edge.get("target", "")).strip(),
        "relation": str(edge.get("relation", "")).strip(),
        "confidence": confidence,
        "confidence_score": confidence_score,
        "source_file": relative_path,
        "source_location": edge.get("source_location"),
        "weight": weight,
    }


def normalize_hyperedge(hyperedge: dict, *, relative_path: str) -> dict:
    confidence = str(hyperedge.get("confidence", "INFERRED")).upper()
    if confidence not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}:
        confidence = "INFERRED"
    try:
        confidence_score = float(hyperedge.get("confidence_score", 0.7))
    except Exception:
        confidence_score = 0.7
    return {
        "id": str(hyperedge.get("id", "")).strip(),
        "label": str(hyperedge.get("label", "")).strip(),
        "nodes": list(hyperedge.get("nodes", [])),
        "relation": str(hyperedge.get("relation", "")).strip(),
        "confidence": confidence,
        "confidence_score": confidence_score,
        "source_file": relative_path,
    }


def normalize_semantic_payload(payload: dict, *, relative_path: str) -> dict:
    nodes = [
        normalize_node(node, relative_path=relative_path)
        for node in payload.get("nodes", [])
        if node.get("id") and node.get("label")
    ]
    edges = [
        normalize_edge(edge, relative_path=relative_path)
        for edge in payload.get("edges", [])
        if edge.get("source") and edge.get("target") and edge.get("relation")
    ]
    hyperedges = [
        normalize_hyperedge(hyperedge, relative_path=relative_path)
        for hyperedge in payload.get("hyperedges", [])
        if hyperedge.get("id") and hyperedge.get("label") and hyperedge.get("nodes")
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
        "input_tokens": int(payload.get("input_tokens", 0) or 0),
        "output_tokens": int(payload.get("output_tokens", 0) or 0),
    }


def run_hermes_extract(
    file_path: Path,
    *,
    sandbox_root: Path,
    hermes_bin: Path,
    max_turns: int,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict:
    relative_path = file_path.resolve().relative_to(sandbox_root.resolve()).as_posix()
    prompt = build_prompt(relative_path, file_path.read_text(encoding="utf-8"))
    encoded = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    python_code = f"""
import base64, subprocess, sys
prompt = base64.b64decode('{encoded}').decode('utf-8')
cp = subprocess.run(
    ['{hermes_bin.as_posix()}','chat','-q',prompt,'-Q','--max-turns','{max_turns}'],
    cwd='{sandbox_root.as_posix()}',
    text=True,
    capture_output=True,
)
sys.stdout.write(cp.stdout)
sys.stderr.write(cp.stderr)
raise SystemExit(cp.returncode)
""".strip()
    last_error: Exception | None = None
    last_stdout = ""
    last_stderr = ""

    for attempt in range(1, max(1, retries) + 1):
        if shutil.which("wsl"):
            completed = subprocess.run(
                ["wsl", "-d", "ubuntu-agent", "--", "python3", "-c", python_code],
                text=True,
                capture_output=True,
                cwd=str(sandbox_root),
            )
        else:
            completed = subprocess.run(
                ["python3", "-c", python_code],
                text=True,
                capture_output=True,
                cwd=str(sandbox_root),
            )

        last_stdout = completed.stdout
        last_stderr = completed.stderr

        try:
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Hermes extraction failed for {relative_path}\n"
                    f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
                )
            payload = extract_json_object(completed.stdout)
            return normalize_semantic_payload(payload, relative_path=relative_path)
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, retries):
                break
            time.sleep(max(0.0, retry_delay_seconds))

    stdout_preview = last_stdout[:800]
    stderr_preview = last_stderr[:800]
    raise RuntimeError(
        f"Hermes semantic extraction failed after {max(1, retries)} attempts for {relative_path}\n"
        f"last_error={last_error!r}\n"
        f"stdout_preview:\n{stdout_preview}\n\nstderr_preview:\n{stderr_preview}"
    )


def merge_unique(nodes_a: list[dict], nodes_b: list[dict]) -> list[dict]:
    seen = set()
    merged = []
    for node in nodes_a + nodes_b:
        node_id = node.get("id")
        if node_id and node_id not in seen:
            seen.add(node_id)
            merged.append(node)
    return merged


def extract_semantic(
    *,
    sandbox_root: Path,
    detect_json: Path,
    semantic_json: Path,
    refresh: bool = False,
    hermes_bin: Path = DEFAULT_HERMES_BIN,
    max_turns: int = 1,
    retries: int = DEFAULT_RETRIES,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict:
    sandbox_root = sandbox_root.resolve()
    detect_json = detect_json.resolve()
    semantic_json = semantic_json.resolve()

    detect_result = load_json(detect_json)
    supported_files = graphify_files(detect_result)

    cached_json = sandbox_root / ".graphify_cached.json"
    uncached_txt = sandbox_root / ".graphify_uncached.txt"
    semantic_new_json = sandbox_root / ".graphify_semantic_new.json"

    if not supported_files:
        empty = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
        write_json(semantic_json, empty)
        return {"cached_files": 0, "uncached_files": 0, "generated_nodes": 0, "generated_edges": 0}

    from graphify.cache import check_semantic_cache, save_semantic_cache

    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    cached_hyperedges: list[dict] = []
    uncached_files: list[str] = supported_files

    if not refresh:
        cached_nodes, cached_edges, cached_hyperedges, uncached_files = check_semantic_cache(
            supported_files, root=sandbox_root
        )

    write_json(
        cached_json,
        {"nodes": cached_nodes, "edges": cached_edges, "hyperedges": cached_hyperedges},
    )
    uncached_txt.write_text("\n".join(uncached_files), encoding="utf-8")

    new_nodes: list[dict] = []
    new_edges: list[dict] = []
    new_hyperedges: list[dict] = []

    for file_name in uncached_files:
        file_path = Path(file_name)
        if not file_path.is_absolute():
            file_path = sandbox_root / file_name
        result = run_hermes_extract(
            file_path.resolve(),
            sandbox_root=sandbox_root,
            hermes_bin=hermes_bin,
            max_turns=max_turns,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        new_nodes.extend(result["nodes"])
        new_edges.extend(result["edges"])
        new_hyperedges.extend(result["hyperedges"])

    new_result = {
        "nodes": new_nodes,
        "edges": new_edges,
        "hyperedges": new_hyperedges,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    write_json(semantic_new_json, new_result)

    if new_nodes or new_edges or new_hyperedges:
        save_semantic_cache(new_nodes, new_edges, new_hyperedges, root=sandbox_root)

    merged = {
        "nodes": merge_unique(cached_nodes, new_nodes),
        "edges": cached_edges + new_edges,
        "hyperedges": cached_hyperedges + new_hyperedges,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    write_json(semantic_json, merged)

    return {
        "cached_files": len(supported_files) - len(uncached_files),
        "uncached_files": len(uncached_files),
        "generated_nodes": len(new_nodes),
        "generated_edges": len(new_edges),
        "generated_hyperedges": len(new_hyperedges),
        "semantic_json": str(semantic_json),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Graphify semantic extraction JSON via Hermes headless calls."
    )
    parser.add_argument("--sandbox-root", required=True, type=Path)
    parser.add_argument("--detect-json", type=Path, required=True)
    parser.add_argument("--semantic-json", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--hermes-bin", type=Path, default=DEFAULT_HERMES_BIN)
    parser.add_argument("--max-turns", type=int, default=1)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--retry-delay-seconds", type=float, default=DEFAULT_RETRY_DELAY_SECONDS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = extract_semantic(
        sandbox_root=args.sandbox_root,
        detect_json=args.detect_json,
        semantic_json=args.semantic_json,
        refresh=args.refresh,
        hermes_bin=args.hermes_bin,
        max_turns=args.max_turns,
        retries=args.retries,
        retry_delay_seconds=args.retry_delay_seconds,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
