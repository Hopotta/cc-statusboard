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
import json
import sys
from pathlib import Path

# Allow `python collector/generate_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import aggregator, ccusage_parser, jsonl_parser  # noqa: E402
from collector.advanced import build as build_advanced  # noqa: E402
from collector.watcher import watch_loop  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "statusboard.json"


def build_statusboard() -> dict:
    """Run all collectors and return the merged dict (no I/O)."""
    print("[1/4] ccusage: session ...", file=sys.stderr)
    sess = ccusage_parser.parse_session()
    print("[1/4] ccusage: daily ...", file=sys.stderr)
    daily_raw = ccusage_parser.parse_daily()

    print("[2/4] jsonl: scanning projects ...", file=sys.stderr)
    scans = jsonl_parser.scan_all()
    jsonl = jsonl_parser.summarize(scans)

    print("[3/4] advanced analytics ...", file=sys.stderr)
    advanced = build_advanced(scans, ccusage_daily_raw=daily_raw, jsonl_summary=jsonl)

    print("[4/4] aggregating ...", file=sys.stderr)
    totals = ccusage_parser.normalize_totals(sess)
    models = ccusage_parser.model_breakdown_from_daily(daily_raw)
    daily = ccusage_parser.daily_series(daily_raw)
    return aggregator.aggregate(totals, models, daily, jsonl, advanced=advanced)


def write_statusboard(out_path: Path, payload: dict) -> None:
    """Atomically write statusboard.json.

    Writes go through a `*.tmp` sibling and are renamed with os.replace so
    concurrent readers (the dashboard polling every 5 s) never see a partial file.
    """
    import os
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)

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
    args = p.parse_args()

    payload = build_statusboard()
    write_statusboard(args.out, payload)

    if not args.watch:
        return 0

    # Shared polling watcher (see collector/watcher.py).  Rebuild failures
    # are swallowed inside the loop so one bad ccusage run can't kill it.
    print(f"[watch] watching {jsonl_parser.CLAUDE_PROJECTS_DIR} ...", file=sys.stderr)

    def rebuild() -> None:
        payload = build_statusboard()
        write_statusboard(args.out, payload)

    try:
        watch_loop(rebuild, interval=3.0, cooldown=10.0)
    except KeyboardInterrupt:
        print("\n[watch] stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())