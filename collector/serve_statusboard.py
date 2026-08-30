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
from typing import Dict

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
        # The freshly generated statusboard.json lives in the project root;
        # the served dist dir may hold a stale copy from a previous build.
        url_path = self.path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        fresh_json = getattr(self.server, "fresh_json", None)
        if url_path == "statusboard.json" and fresh_json is not None and fresh_json.exists():
            body = fresh_json.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        # Translate / to serve index.html for app routes.
        # If the requested path maps to a file, serve it; else fall back to index.html.
        root = Path(self.directory) if self.directory else Path.cwd()
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
    fresh_json: Path | None = None


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


def _dist_is_stale(dist: Path) -> bool:
    """True when the dist bundle is missing or older than any frontend source."""
    index = dist / "index.html"
    if not index.exists():
        return True
    frontend = dist.parent
    candidates: list[float] = []
    for sub in ("src", "public"):
        d = frontend / sub
        if d.exists():
            candidates.extend(
                p.stat().st_mtime for p in d.rglob("*") if p.is_file()
            )
    for name in ("index.html", "vite.config.ts", "tailwind.config.js",
                 "postcss.config.js", "package.json"):
        f = frontend / name
        if f.exists():
            candidates.append(f.stat().st_mtime)
    if not candidates:
        return False
    return max(candidates) > index.stat().st_mtime


def _ensure_dist(dist: Path) -> Path:
    """Build the frontend when dist is missing or older than the sources."""
    if dist.exists() and (dist / "index.html").exists() and not _dist_is_stale(dist):
        return dist
    reason = "missing" if not (dist / "index.html").exists() else "older than sources"
    print(f"[serve] frontend {reason}; building …", file=sys.stderr)
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


def _ensure_fresh_json(out: Path) -> None:
    """Regenerate statusboard.json, falling back to the last known-good file.

    A ccusage failure (binary missing, offline, upstream hiccup) must not take
    the whole dashboard down — if a previous statusboard.json exists, keep
    serving it.  Only a first-ever run with no artifact at all re-raises.
    """
    try:
        payload = generate_statusboard.build_statusboard()
        generate_statusboard.write_statusboard(out, payload)
    except Exception as exc:  # noqa: BLE001
        if out.exists():
            print(
                f"[serve] WARNING: data build failed ({exc});\n"
                f"[serve] serving the last known-good {out.name}",
                file=sys.stderr,
            )
            return
        raise


def main() -> int:
    p = argparse.ArgumentParser(description="Serve the cc-statusboard frontend")
    p.add_argument("--port", type=int, default=3456)
    p.add_argument("--watch", action="store_true",
                   help="Regenerate statusboard.json on JSONL changes")
    p.add_argument("--no-open", action="store_true",
                   help="Don't open the browser automatically")
    p.add_argument("--no-build", action="store_true",
                   help="Serve dist as-is, skip the stale-frontend rebuild")
    p.add_argument("--source", type=Path, default=DEFAULT_DIST,
                   help="Static dir to serve (defaults to frontend/dist)")
    args = p.parse_args()

    # 1. Make sure statusboard.json is fresh before serving.
    out = PROJECT_ROOT / "statusboard.json"
    _ensure_fresh_json(out)

    # 2. Ensure the frontend is up to date with its sources.
    dist = args.source if args.no_build else _ensure_dist(args.source)

    # 3. Optionally start a watcher that regenerates on JSONL change.
    if args.watch:
        from collector.watcher import start_watcher

        def watcher() -> None:
            payload = generate_statusboard.build_statusboard()
            generate_statusboard.write_statusboard(out, payload)

        start_watcher(watcher, interval=3.0, cooldown=10.0)

    # 4. Bind a free port and serve the dist dir.
    port = _pick_free_port(args.port)
    handler = lambda *a, **kw: _SilentHandler(*a, directory=str(dist), **kw)
    httpd = _ThreadedServer(("127.0.0.1", port), handler)
    httpd.fresh_json = out

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