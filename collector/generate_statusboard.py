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
import os
import sys
import time
from pathlib import Path

# Allow `python collector/generate_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import aggregator, ccusage_parser, jsonl_parser  # noqa: E402
from collector.advanced import parse_all as parse_advanced  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "statusboard.json"
# Mirror copy for the Vite dev server. Vite only serves files inside its
# project root, so we duplicate statusboard.json into frontend/public/.
PUBLIC_OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "statusboard.json"


def build_statusboard() -> dict:
    """Run all collectors and return the merged dict (no I/O)."""
    print("[1/4] ccusage: session ...", file=sys.stderr)
    sess = ccusage_parser.parse_session()
    print("[1/4] ccusage: daily ...", file=sys.stderr)
    daily = ccusage_parser.parse_daily()

    print("[2/4] jsonl: scanning projects ...", file=sys.stderr)
    jsonl = jsonl_parser.parse_all()

    print("[3/4] advanced analytics ...", file=sys.stderr)
    advanced = parse_advanced(ccusage_daily_raw=daily, jsonl_summary=jsonl)

    print("[4/4] aggregating ...", file=sys.stderr)
    return aggregator.aggregate(sess, daily, jsonl, advanced=advanced)


def write_statusboard(out_path: Path, payload: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")

    # Mirror to frontend/public/statusboard.json so the Vite dev server can serve it.
    try:
        PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_OUT.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"[warn] could not write {PUBLIC_OUT}: {exc}", file=sys.stderr)

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

    # Simple polling watcher (avoids extra deps).  Detects new sessions quickly.
    print(f"[watch] watching {jsonl_parser.CLAUDE_PROJECTS_DIR} ...", file=sys.stderr)
    seen = set(str(p) for p in jsonl_parser.iter_jsonl_files())
    last_size = {p: jsonl_parser.CLAUDE_PROJECTS_DIR.joinpath(p).stat().st_size
                 for p in seen}

    try:
        while True:
            time.sleep(3)
            current = set(str(p) for p in jsonl_parser.iter_jsonl_files())
            changed = False
            for p in current - seen:
                changed = True
                print(f"[watch] new session: {p}", file=sys.stderr)
            for p in current & seen:
                try:
                    size = jsonl_parser.CLAUDE_PROJECTS_DIR.joinpath(p).stat().st_size
                except OSError:
                    continue
                if last_size.get(p) != size:
                    changed = True
                    last_size[p] = size
                    print(f"[watch] changed: {p}", file=sys.stderr)
            if changed:
                payload = build_statusboard()
                write_statusboard(args.out, payload)
            seen = current
    except KeyboardInterrupt:
        print("\n[watch] stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())