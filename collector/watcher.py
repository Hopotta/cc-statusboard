"""
watcher.py
==========

Single JSONL change watcher shared by both CLI entrypoints
(`generate_statusboard --watch` and `serve_statusboard --watch`).

Polls the projects dir every `interval` seconds; when any session file
appears or grows, calls `on_change` (a full rebuild), keeping at least
`cooldown` seconds between rebuilds so bursty writes don't cause
back-to-back full regeneration.  A failing rebuild is printed and
swallowed — a long-running watcher must never die from one bad cycle.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Dict, Optional, Set

from .jsonl_parser import iter_jsonl_files


def _snapshot() -> tuple[Set[str], Dict[str, int]]:
    seen: Set[str] = set()
    sizes: Dict[str, int] = {}
    for p in iter_jsonl_files():
        path_str = str(p)
        seen.add(path_str)
        try:
            sizes[path_str] = p.stat().st_size
        except OSError:
            sizes[path_str] = 0
    return seen, sizes


def watch_loop(
    on_change: Callable[[], None],
    interval: float = 3.0,
    cooldown: float = 10.0,
    stop: Optional[threading.Event] = None,
) -> None:
    """Block and rebuild on JSONL changes until `stop` is set (or forever)."""
    seen, last_size = _snapshot()
    last_build = 0.0
    pending = False

    while stop is None or not stop.wait(interval):
        try:
            current, current_sizes = _snapshot()
            changed = False
            for path in current - seen:
                print(f"[watch] new session: {path}", file=sys.stderr)
                changed = True
            for path in current & seen:
                if last_size.get(path) != current_sizes.get(path):
                    print(f"[watch] changed: {path}", file=sys.stderr)
                    changed = True
            seen = current
            last_size = current_sizes
            if changed:
                pending = True
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            continue
        if pending and time.monotonic() - last_build >= cooldown:
            pending = False
            last_build = time.monotonic()
            try:
                on_change()
            except Exception:  # noqa: BLE001
                traceback.print_exc()


def start_watcher(
    on_change: Callable[[], None],
    interval: float = 3.0,
    cooldown: float = 10.0,
) -> threading.Thread:
    t = threading.Thread(
        target=watch_loop,
        args=(on_change,),
        kwargs={"interval": interval, "cooldown": cooldown},
        name="jsonl-watcher",
        daemon=True,
    )
    t.start()
    return t
