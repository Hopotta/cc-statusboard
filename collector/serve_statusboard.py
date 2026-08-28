"""
serve_statusboard.py
====================

Single-file launcher for cc-statusboard:

  1. Generates statusboard.json (one-shot or --watch)
  2. Serves the frontend build output on http://localhost:<port>
  3. Optionally opens the browser

Usage:
    python collector/serve_statusboard.py                  # one-shot gen + serve
    python collector/serve_statusboard.py --watch          # regen on JSONL change
    python collector/serve_statusboard.py --port 3456
    python collector/serve_statusboard.py --no-open        # don't open browser
    python collector/serve_statusboard.py --source <dir>   # serve dist from a custom dir
"""

from __future__ import annotations

import argparse
import http.server
import os
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Allow `python collector/serve_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import generate_statusboard  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = PROJECT_ROOT / "frontend" / "dist"


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that:

    - logs to stderr at debug level only
    - falls back to index.html for SPA-style routes (paths without an extension)
    """

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Quiet default; we keep errors at least.
        if " 5" in format or " 4" in format:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self):  # noqa: N802
        # Translate / to serve index.html for app routes.
        # If the requested path maps to a file, serve it; else fall back to index.html.
        root = Path(self.directory) if self.directory else Path.cwd()
        url_path = self.path.split("?", 1)[0].split("#", 1)[0]
        target = (root / url_path.lstrip("/")).resolve()
        # Prevent path traversal.
        try:
            target.relative_to(root.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.exists() or target.is_dir():
            # SPA fallback for routes without a file extension.
            if "." not in url_path.rsplit("/", 1)[-1]:
                target = root / "index.html"
        if not target.exists():
            self.send_error(404, "not found")
            return
        # Delegate to SimpleHTTPRequestHandler's translation by temporarily
        # rewriting self.path to the relative file path.
        original = self.path
        self.path = str(target.relative_to(root)).replace("\\", "/")
        try:
            return super().do_GET()
        finally:
            self.path = original


class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _pick_free_port(preferred: int) -> int:
    """Try `preferred` first; fall back to any free port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def _ensure_dist(dist: Path) -> Path:
    """If frontend/dist doesn't exist, build it."""
    if dist.exists() and (dist / "index.html").exists():
        return dist
    print(f"[serve] {dist} missing; building frontend …", file=sys.stderr)
    import subprocess

    frontend_dir = dist.parent
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        shell=(sys.platform == "win32"),
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError("frontend build failed; run `npm run build` manually")
    return dist


def main() -> int:
    p = argparse.ArgumentParser(description="Serve the cc-statusboard frontend")
    p.add_argument("--port", type=int, default=3456)
    p.add_argument("--watch", action="store_true",
                   help="Regenerate statusboard.json on JSONL changes")
    p.add_argument("--no-open", action="store_true",
                   help="Don't open the browser automatically")
    p.add_argument("--source", type=Path, default=DEFAULT_DIST,
                   help="Static dir to serve (defaults to frontend/dist)")
    args = p.parse_args()

    # 1. Make sure statusboard.json is fresh before serving.
    payload = generate_statusboard.build_statusboard()
    out = PROJECT_ROOT / "statusboard.json"
    generate_statusboard.write_statusboard(out, payload)

    # 2. Ensure the frontend has been built at least once.
    dist = _ensure_dist(args.source)

    # 3. Optionally start a watcher that regenerates on JSONL change.
    if args.watch:
        from collector import jsonl_parser

        stop = threading.Event()

        def watcher() -> None:
            seen = set(str(p) for p in jsonl_parser.iter_jsonl_files())
            last_size = {}
            for path in seen:
                try:
                    last_size[path] = Path(path).stat().st_size
                except OSError:
                    last_size[path] = 0
            while not stop.wait(3):
                try:
                    current = set(str(p) for p in jsonl_parser.iter_jsonl_files())
                    changed = False
                    for path in current - seen:
                        print(f"[watch] new session: {path}", file=sys.stderr)
                        changed = True
                    for path in current & seen:
                        try:
                            size = Path(path).stat().st_size
                        except OSError:
                            continue
                        if last_size.get(path) != size:
                            last_size[path] = size
                            changed = True
                            print(f"[watch] changed: {path}", file=sys.stderr)
                    if changed:
                        payload = generate_statusboard.build_statusboard()
                        generate_statusboard.write_statusboard(out, payload)
                    seen = current
                except Exception as exc:  # noqa: BLE001
                    print(f"[watch] error: {exc}", file=sys.stderr)

        t = threading.Thread(target=watcher, name="jsonl-watcher", daemon=True)
        t.start()

    # 4. Bind a free port and serve the dist dir.
    port = _pick_free_port(args.port)
    handler = lambda *a, **kw: _SilentHandler(*a, directory=str(dist), **kw)
    httpd = _ThreadedServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}/"
    print(f"\n[serve] cc-statusboard ready at {url}", file=sys.stderr)
    print(f"        serving from: {dist}", file=sys.stderr)
    if args.watch:
        print("        watching ~/.claude/projects/ for changes", file=sys.stderr)

    if not args.no_open:
        # Defer a moment so the server has fully accepted connections.
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())