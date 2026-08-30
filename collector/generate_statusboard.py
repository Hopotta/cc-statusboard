"""
generate_statusboard.py
=======================

CLI entrypoint. Runs all collectors and writes statusboard.json.

Usage:
    python collector/generate_statusboard.py                 # writes ./statusboard.json
    python collector/generate_statusboard.py --out path.json # writes to custom path
    python collector/generate_statusboard.py --watch         # regenerate on JSONL change
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Tuple

# Allow `python collector/generate_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import aggregator, ccusage_parser, jsonl_parser  # noqa: E402
from collector.advanced import build as build_advanced  # noqa: E402
from collector.watcher import watch_loop  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "statusboard.json"
CCUSAGE_CACHE_PATH = Path(__file__).resolve().parent.parent / ".ccusage_cache.json"


def ccusage_fingerprint(files) -> str:
    """Hash of the JSONL input set (path + size) — keys the ccusage cache.

    ccusage recomputes purely from these files, so an unchanged fingerprint
    means unchanged output (and also pins the pricing it used).
    """
    h = hashlib.sha1()
    for p in sorted(files, key=str):
        try:
            h.update(f"{p}\0{p.stat().st_size}\0".encode("utf-8", "surrogatepass"))
        except OSError:
            continue
    return h.hexdigest()


def _read_ccusage_cache(cache_path: Path,
                        fingerprint: Optional[str] = None
                        ) -> Optional[Tuple[dict, dict]]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if fingerprint is not None and data.get("fingerprint") != fingerprint:
        return None
    sess, daily = data.get("session"), data.get("daily")
    if not isinstance(sess, dict) or not isinstance(daily, dict):
        return None
    return sess, daily


def _write_ccusage_cache(cache_path: Path, fingerprint: str,
                         sess: dict, daily_raw: dict) -> None:
    import os
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"fingerprint": fingerprint, "session": sess,
                    "daily": daily_raw}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, cache_path)


def _run_ccusage_parallel() -> Tuple[dict, dict]:
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_sess = ex.submit(ccusage_parser.parse_session)
        fut_daily = ex.submit(ccusage_parser.parse_daily)
        return fut_sess.result(), fut_daily.result()


def build_statusboard(jsonl_root: Optional[Path] = None,
                      cache_path: Optional[Path] = None) -> dict:
    """Run all collectors and return the merged dict (no I/O besides caches)."""
    print("[1/4] jsonl: scanning projects ...", file=sys.stderr)
    scans = jsonl_parser.scan_all(jsonl_root)
    fingerprint = ccusage_fingerprint(jsonl_parser.iter_jsonl_files(jsonl_root))

    print("[2/4] ccusage: session + daily ...", file=sys.stderr)
    cache_path = cache_path or CCUSAGE_CACHE_PATH
    cached = _read_ccusage_cache(cache_path, fingerprint)
    if cached is not None:
        sess, daily_raw = cached
        print("       inputs unchanged — using cached ccusage output", file=sys.stderr)
    else:
        try:
            sess, daily_raw = _run_ccusage_parallel()
            _write_ccusage_cache(cache_path, fingerprint, sess, daily_raw)
        except Exception as exc:  # noqa: BLE001
            stale = _read_ccusage_cache(cache_path)
            if stale is None:
                raise
            print(
                f"[ccusage] WARNING: refresh failed ({exc});\n"
                f"[ccusage] using the stale ccusage cache",
                file=sys.stderr,
            )
            sess, daily_raw = stale

    print("[3/4] advanced analytics ...", file=sys.stderr)
    jsonl = jsonl_parser.summarize(scans)
    advanced = build_advanced(scans, ccusage_daily_raw=daily_raw, jsonl_summary=jsonl)

    print("[4/4] aggregating ...", file=sys.stderr)
    totals = ccusage_parser.normalize_totals(sess)
    models = ccusage_parser.model_breakdown_from_daily(daily_raw)
    daily = ccusage_parser.daily_series(daily_raw)
    return aggregator.aggregate(totals, models, daily, jsonl, advanced=advanced)


def write_statusboard(out_path: Path, payload: dict, pretty: bool = False) -> None:
    """Atomically write statusboard.json.

    Writes go through a `*.tmp` sibling and are renamed with os.replace so
    concurrent readers (the dashboard polling every 5 s) never see a partial
    file.  The artifact is a machine product — compact by default, `--pretty`
    for human inspection.
    """
    import os
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    # Atomic write: tmp file in the same directory, then os.replace.
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, out_path)

    s = payload.get("summary", {})
    print(
        f"\n  -> wrote {out_path}\n"
        f"     totalTokens = {s.get('totalTokens'):,}\n"
        f"     totalTasks  = {s.get('totalTasks')}\n"
        f"     totalTime   = {s.get('totalTimeHuman')}\n"
        f"     avgTask     = {s.get('averageTaskHuman')}\n"
        f"     topModel    = {s.get('mostUsedModel', {}).get('modelName')}\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Build Claude Code statusboard.json")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output path")
    p.add_argument(
        "--watch",
        action="store_true",
        help="Re-run on JSONL changes under ~/.claude/projects/",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default if --watch not given)",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Write statusboard.json indented (for human inspection)",
    )
    args = p.parse_args()

    payload = build_statusboard()
    write_statusboard(args.out, payload, pretty=args.pretty)

    if not args.watch:
        return 0

    # Shared polling watcher (see collector/watcher.py).  Rebuild failures
    # are swallowed inside the loop so one bad ccusage run can't kill it.
    print(f"[watch] watching {jsonl_parser.CLAUDE_PROJECTS_DIR} ...", file=sys.stderr)

    def rebuild() -> None:
        payload = build_statusboard()
        write_statusboard(args.out, payload, pretty=args.pretty)

    try:
        watch_loop(rebuild, interval=3.0, cooldown=10.0)
    except KeyboardInterrupt:
        print("\n[watch] stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())