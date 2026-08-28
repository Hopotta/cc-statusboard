"""Tests for collector/serve_statusboard.py."""

import json
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.serve_statusboard import _SilentHandler, _ThreadedServer


def _start_server(dist: Path, fresh_json: Path) -> _ThreadedServer:
    httpd = _ThreadedServer(
        ("127.0.0.1", 0),
        lambda *a, **kw: _SilentHandler(*a, directory=str(dist), **kw),
    )
    httpd.fresh_json = fresh_json
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_serves_fresh_statusboard_json_over_stale_dist_copy(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "statusboard.json").write_text(json.dumps({"stale": True}), encoding="utf-8")
    fresh = tmp_path / "statusboard.json"
    fresh.write_text(json.dumps({"fresh": True}), encoding="utf-8")

    httpd = _start_server(dist, fresh)
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/statusboard.json?ts=123"
        ) as resp:
            assert json.loads(resp.read()) == {"fresh": True}
    finally:
        httpd.shutdown()


def test_spa_fallback_still_works(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    fresh = tmp_path / "statusboard.json"
    fresh.write_text("{}", encoding="utf-8")

    httpd = _start_server(dist, fresh)
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/some/route") as resp:
            assert b"app" in resp.read()
    finally:
        httpd.shutdown()
