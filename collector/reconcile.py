"""
reconcile.py
============

Background ccusage reconciler (A3 architecture).

The rebuild critical path never touches ccusage anymore — global totals,
model breakdown and daily series are computed natively from the JSONL
scans (see native_usage.py).  ccusage's remaining roles:

  1. pricing: its daily `modelBreakdowns` provide per-model blended unit
     prices (model cost / model tokens) used to price native tokens;
  2. reconciliation: its totals are the external cross-check for the
     native numbers (the known ~5% gap is expected and logged).

`refresh` runs `ccusage daily --json` SERIALLY with a generous timeout
(300 s: the CLI takes ~30 s per call at ~283 MB and chokes when run in
parallel).  It is meant to be called from a daemon thread at server
startup and every RECONCILE_INTERVAL seconds — never from the rebuild
path.  Output is cached in `.ccusage_cache.json`
(`{fingerprint, ranAt, daily}`; legacy caches with a `session` block are
still readable).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, Optional

from . import ccusage_parser
from .jsonl_parser import iter_jsonl_files

if TYPE_CHECKING:
    from .contracts import PricingInfo

DEFAULT_TIMEOUT = 300  # seconds; 60 was set when the corpus was 10× smaller


def ccusage_fingerprint(files: Iterable[Path]) -> str:
    """Hash of the JSONL input set (path + size) — keys the ccusage cache.

    Invariant: Claude Code session JSONL is treated as append-only, so
    path + size is a sufficient change signal and the corpus is never
    re-read just to hash it.  A same-size in-place rewrite would be missed
    by design; that trade is what keeps the fingerprint O(files) stat-only.
    """
    h = hashlib.sha1()
    for p in sorted(files, key=str):
        try:
            h.update(f"{p}\0{p.stat().st_size}\0".encode("utf-8", "surrogatepass"))
        except OSError:
            continue
    return h.hexdigest()


def read_cache(cache_path: Path,
               fingerprint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Read the cached ccusage daily output.

    Returns {"daily": <raw>, "ranAt": <iso|None>} or None.  With
    `fingerprint`, mismatches return None; pass None to accept any age
    (pricing derivation tolerates staleness).  Legacy caches that still
    carry a `session` block are accepted.
    """
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if fingerprint is not None and data.get("fingerprint") != fingerprint:
        return None
    daily = data.get("daily")
    if not isinstance(daily, dict):
        return None
    ran_at = data.get("ranAt")
    if ran_at is None:
        try:
            ran_at = datetime.fromtimestamp(
                cache_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            ran_at = None
    return {"daily": daily, "ranAt": ran_at}


def write_cache(cache_path: Path, fingerprint: str, daily_raw: dict,
                ran_at: str) -> None:
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"fingerprint": fingerprint, "ranAt": ran_at,
                    "daily": daily_raw}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, cache_path)


def refresh(cache_path: Path,
            timeout: int = DEFAULT_TIMEOUT,
            jsonl_root: Optional[Path] = None,
            log=None) -> Optional[Dict[str, Any]]:
    """Refresh the ccusage daily cache; returns the raw daily output on a
    successful refresh, None when skipped or failed (cache untouched).

    Serial by design: two parallel ccusage processes contend for I/O and
    the session call blows past any sane timeout (status report §5.1).
    """
    log = log or (lambda msg: print(msg, file=sys.stderr))
    files = list(iter_jsonl_files(jsonl_root))
    fingerprint = ccusage_fingerprint(files)

    cached = read_cache(cache_path, fingerprint)
    if cached is not None:
        log("[ccusage] inputs unchanged - reconcile skipped (fingerprint hit)")
        return None

    start = time.monotonic()
    try:
        daily_raw = ccusage_parser.parse_daily(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        log(f"[ccusage] daily FAILED after {elapsed:.1f}s: {exc}")
        return None
    elapsed = time.monotonic() - start
    ran_at = datetime.now(timezone.utc).isoformat()
    write_cache(cache_path, fingerprint, daily_raw, ran_at)
    log(f"[ccusage] daily refreshed in {elapsed:.1f}s "
        f"({len(daily_raw.get('daily', []))} days)")
    return daily_raw


def derive_pricing(daily_raw: Dict[str, Any]) -> Dict[str, float]:
    """Per-model blended unit price (cost per token) from ccusage's daily
    modelBreakdowns — the pricing table the native aggregation bills with."""
    prices: Dict[str, float] = {}
    for m in ccusage_parser.model_breakdown_from_daily(daily_raw):
        if m["totalTokens"] > 0:
            prices[m["modelName"]] = m["cost"] / m["totalTokens"]
    return prices


def load_pricing(cache_path: Path) -> Optional["PricingInfo"]:
    """Last known pricing, of any age.  Returns
    {"prices": {model: unit_price}, "asOf": iso|None,
     "modelTokens": {model: int}} or None.

    `modelTokens` is ccusage's per-model token totals (from the daily
    modelBreakdowns).  Note ccusage's scope is broader than this
    dashboard's: its daily rollup also covers other agents' session logs
    (e.g. ~/.codex, the gpt-*/codex-* models), so callers must restrict
    the cross-check to models that exist natively."""
    cached = read_cache(cache_path)
    if cached is None:
        return None
    model_tokens: Dict[str, int] = {}
    for m in ccusage_parser.model_breakdown_from_daily(cached["daily"]):
        model_tokens[m["modelName"]] = m["totalTokens"]
    return {
        "prices": derive_pricing(cached["daily"]),
        "asOf": cached["ranAt"],
        "modelTokens": model_tokens,
    }


RECONCILE_INTERVAL_SECONDS = 6 * 60 * 60  # a few times a day is plenty


def reconciler_loop(cache_path: Path,
                    interval: float = RECONCILE_INTERVAL_SECONDS,
                    jsonl_root: Optional[Path] = None,
                    stop: Optional[threading.Event] = None) -> None:
    """Refresh the ccusage cache now, then every `interval` seconds, until
    `stop` is set.  Built to run inside a daemon thread; a failing cycle
    never ends the loop."""
    while True:
        try:
            refresh(cache_path, jsonl_root=jsonl_root)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if stop is not None and stop.wait(interval):
            break


def spawn_reconciler(cache_path: Path,
                     interval: float = RECONCILE_INTERVAL_SECONDS,
                     jsonl_root: Optional[Path] = None,
                     ) -> tuple[threading.Thread, threading.Event]:
    """Start the background reconciler; returns (thread, stop_event)."""
    stop = threading.Event()
    t = threading.Thread(
        target=reconciler_loop,
        args=(cache_path,),
        kwargs={"interval": interval, "jsonl_root": jsonl_root, "stop": stop},
        name="ccusage-reconciler",
        daemon=True,
    )
    t.start()
    return t, stop
