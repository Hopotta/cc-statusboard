"""
generate_statusboard.py
=======================

CLI entrypoint. Runs all collectors and writes statusboard.json.

Usage:
    python collector/generate_statusboard.py                 # writes ./statusboard.json
    python collector/generate_statusboard.py --out path.json # writes to custom path
    python collector/generate_statusboard.py --watch         # regenerate on JSONL change
    python collector/generate_statusboard.py --reconcile     # refresh ccusage cache first

Data flow (A3, 2026-08-31):
    JSONL scans -> native totals/models/daily (native_usage.py) -> aggregate
    ccusage cache -> pricing (per-model unit prices) + cross-check totals

The rebuild critical path NEVER runs the ccusage CLI — it is an
O(all-data) external process (28–32 s per call at ~283 MB) that froze the
dashboard during active use.  ccusage is reconciled in the background
instead (see reconcile.py); its cached output of any age still supplies
pricing, and a missing cache simply prices everything at 0 with
`meta.pricingSource = "none"`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Allow `python collector/generate_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import aggregator, jsonl_parser, native_usage, reconcile  # noqa: E402
from collector.advanced import build as build_advanced  # noqa: E402
from collector.watcher import watch_loop  # noqa: E402

if TYPE_CHECKING:
    from collector.contracts import FilterStats, ModelUsageRow, PricingInfo

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "statusboard.json"
CCUSAGE_CACHE_PATH = Path(__file__).resolve().parent.parent / ".ccusage_cache.json"

# Sentinel (status report §5.4): the task definition filters system-injected
# user-shaped entries by prefix/regex heuristics against an unversioned,
# schema-less upstream format.  If the injected share among non-tool-result
# user entries jumps past this threshold, the format has probably shifted and
# the filter is silently over- or under-matching.  Warn loudly at build time;
# the distribution itself ships in the artifact as `tasks.filterStats`.
SENTINEL_INJECTED_SHARE = 0.55


def _warn_injection_share(filter_stats: Optional["FilterStats"]) -> None:
    if not filter_stats:
        return
    injected = filter_stats.get("isMeta", 0) + filter_stats.get("injected", 0)
    non_tool = injected + filter_stats.get("tasks", 0)
    if non_tool <= 0:
        return
    share = injected / non_tool
    if share > SENTINEL_INJECTED_SHARE:
        print(
            f"[sentinel] WARNING: injected share among non-tool-result user "
            f"entries is {share:.0%} ({injected}/{non_tool}) — above the "
            f"{SENTINEL_INJECTED_SHARE:.0%} baseline.  The upstream JSONL "
            f"format may have changed; inspect tasks.filterStats.",
            file=sys.stderr,
        )


def _build_meta(pricing_info: Optional["PricingInfo"],
                native_models: List["ModelUsageRow"]) -> Dict[str, Any]:
    """Provenance metadata (status report §5.3): what is fresh by
    construction (everything native) vs. what leans on ccusage (pricing),
    plus the signed native-vs-ccusage totals cross-check.

    The cross-check compares only models that exist natively: ccusage's
    daily rollup also covers other agents' session logs (~/.codex →
    gpt-*/codex-* models, ~5% of its volume here), which would otherwise
    mask the real gap.  The excluded volume is reported separately."""
    prices: Optional[Dict[str, float]] = (
        pricing_info.get("prices") if pricing_info else None)
    as_of = pricing_info.get("asOf") if pricing_info else None
    model_tokens: Dict[str, int] = (
        pricing_info.get("modelTokens") if pricing_info else None) or {}
    native_names = {m["modelName"] for m in native_models}
    cc_total = sum(v for k, v in model_tokens.items() if k in native_names) or None
    cc_other = sum(v for k, v in model_tokens.items()
                   if k not in native_names) or None
    native_total = sum(m["totalTokens"] for m in native_models)
    diff = None
    if prices and cc_total:
        diff = round((native_total - cc_total) / cc_total * 100, 2)
    return {
        "pricingSource": "ccusage" if prices else "none",
        "pricingAsOf": as_of,
        "ccusageReconciledAt": as_of,
        "ccusageTotalTokens": cc_total,
        "ccusageOtherAgentsTokens": cc_other,
        "totalTokensDiffPct": diff,
    }


def build_statusboard(jsonl_root: Optional[Path] = None,
                      cache_path: Optional[Path] = None) -> dict:
    """Run all collectors and return the merged dict (no I/O besides caches)."""
    t0 = time.monotonic()
    print("[1/4] jsonl: scanning projects ...", file=sys.stderr)
    scans = jsonl_parser.scan_all(jsonl_root)
    t1 = time.monotonic()

    print("[2/4] native usage rollups (pricing from ccusage cache) ...",
          file=sys.stderr)
    cache_path = cache_path or CCUSAGE_CACHE_PATH
    pricing_info = reconcile.load_pricing(cache_path)
    usage = native_usage.native_usage(
        scans, pricing=pricing_info.get("prices") if pricing_info else None)

    print("[3/4] advanced analytics ...", file=sys.stderr)
    jsonl = jsonl_parser.summarize(scans)
    _warn_injection_share(jsonl.get("filterStats"))
    advanced = build_advanced(scans, totals=usage["totals"], jsonl_summary=jsonl)

    print("[4/4] aggregating ...", file=sys.stderr)
    payload = aggregator.aggregate(
        usage["totals"], usage["models"], usage["daily"], jsonl,
        advanced=advanced,
    )
    payload["meta"] = _build_meta(pricing_info, usage["models"])
    t2 = time.monotonic()

    print(
        f"[timing] scan={t1 - t0:.2f}s aggregate={t2 - t1:.2f}s "
        f"total={t2 - t0:.2f}s pricing={payload['meta']['pricingSource']}",
        file=sys.stderr,
    )
    return payload


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
    meta = payload.get("meta", {})
    print(
        f"\n  -> wrote {out_path}\n"
        f"     totalTokens = {s.get('totalTokens'):,}"
        f" (vs ccusage {meta.get('totalTokensDiffPct')}%)\n"
        f"     totalTasks  = {s.get('totalTasks')}\n"
        f"     totalTime   = {s.get('totalTimeHuman')}\n"
        f"     avgTask     = {s.get('averageTaskHuman')}\n"
        f"     topModel    = {s.get('mostUsedModel', {}).get('modelName')}\n"
        f"     pricing     = {meta.get('pricingSource')}"
        f" as of {meta.get('pricingAsOf') or 'never'}"
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
    p.add_argument(
        "--reconcile",
        action="store_true",
        help="Refresh the ccusage cache (serial, up to 5 min) before building",
    )
    args = p.parse_args()

    if args.reconcile:
        reconcile.refresh(CCUSAGE_CACHE_PATH)

    payload = build_statusboard()
    write_statusboard(args.out, payload, pretty=args.pretty)

    if not args.watch:
        return 0

    # Shared polling watcher (see collector/watcher.py).  Rebuild failures
    # are swallowed inside the loop so one bad cycle can't kill it.
    print(f"[watch] watching {jsonl_parser.CLAUDE_PROJECTS_DIR} ...", file=sys.stderr)

    # Background ccusage reconciler (A3): pricing + cross-check only.
    reconcile.spawn_reconciler(CCUSAGE_CACHE_PATH)

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
