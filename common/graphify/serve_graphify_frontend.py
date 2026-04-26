from __future__ import annotations

import argparse
import mimetypes
import os
import posixpath
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_SANDBOX_ROOT = Path(
    os.getenv("GRAPHIFY_SANDBOX_ROOT", str(Path(__file__).resolve().parent / ".runtime"))
)


class GraphifyNativeHandler(SimpleHTTPRequestHandler):
    graph_dir: Path

    def translate_path(self, path: str) -> str:
        normalized = posixpath.normpath(path.split("?", 1)[0].split("#", 1)[0])
        if normalized in ("/", "/index.html"):
            target = self.graph_dir / "graph.html"
        else:
            relative = normalized.lstrip("/")
            target = (self.graph_dir / relative).resolve()
        graph_root = self.graph_dir.resolve()
        if not str(target).startswith(str(graph_root)):
            return str(graph_root / "graph.html")
        return str(target)

    def guess_type(self, path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        return mime or "application/octet-stream"

    def log_message(self, fmt: str, *args) -> None:
        print("[graphify-native] " + (fmt % args))

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        if code == HTTPStatus.NOT_FOUND:
            self.path = "/"
            return self.do_GET()
        return super().send_error(code, message, explain)


def build_handler(graph_dir: Path):
    class Handler(GraphifyNativeHandler):
        pass

    Handler.graph_dir = graph_dir
    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Graphify native graph.html as the local root frontend.")
    parser.add_argument("--sandbox-root", type=Path, default=DEFAULT_SANDBOX_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_dir = args.sandbox_root / "graphify-out"
    if not (graph_dir / "graph.html").exists():
        raise SystemExit(f"Graphify native frontend not found: {graph_dir / 'graph.html'}")
    handler = build_handler(graph_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Graphify native frontend on http://{args.host}:{args.port}")
    print(f"Graph directory: {graph_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
