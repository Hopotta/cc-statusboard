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
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, cast

# Allow `python collector/generate_statusboard.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import (  # noqa: E402
    aggregator,
    codex_parser,
    codex_pricing,
    jsonl_parser,
    native_usage,
    reconcile,
)
from collector.advanced import build as build_advanced  # noqa: E402
from collector.watcher import watch_loop  # noqa: E402

if TYPE_CHECKING:
    from collector.contracts import (
        FilterStats,
        AgentDescriptor,
        ModelUsageRow,
        PricingInfo,
        StatusboardArtifact,
        StatusboardMeta,
    )

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
                native_models: List["ModelUsageRow"]) -> "StatusboardMeta":
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
    # Share of the native token volume covered by a model-level price.
    # A 0.0 price in the table counts as covered (explicit free/unknown
    # pricing per ccusage); models absent from the table are the gap.
    coverage = None
    if prices and native_total:
        priced = sum(m["totalTokens"] for m in native_models
                     if m["modelName"] in prices)
        coverage = round(priced / native_total, 4)
    return cast("StatusboardMeta", {
        "pricingSource": "ccusage" if prices else "none",
        "pricingAsOf": as_of,
        "pricingCoverage": coverage,
        "ccusageReconciledAt": as_of,
        "ccusageTotalTokens": cc_total,
        "ccusageOtherAgentsTokens": cc_other,
        "totalTokensDiffPct": diff,
    })


def _build_codex_meta(native_models: List["ModelUsageRow"]) -> "StatusboardMeta":
    """Describe the local Codex API-equivalent pricing estimate."""
    coverage = codex_pricing.pricing_coverage(native_models)
    return cast("StatusboardMeta", {
        "pricingSource": "openai-api" if coverage else "none",
        "pricingAsOf": codex_pricing.PRICING_AS_OF if coverage else None,
        "pricingCoverage": coverage,
        "ccusageReconciledAt": None,
        "ccusageTotalTokens": None,
        "ccusageOtherAgentsTokens": None,
        "totalTokensDiffPct": None,
    })


def _build_combined_meta(claude_meta: "StatusboardMeta",
                         codex_meta: "StatusboardMeta",
                         claude_tokens: int, codex_tokens: int) -> "StatusboardMeta":
    """Keep the distinct pricing provenance visible in the default view."""
    total_tokens = claude_tokens + codex_tokens
    priced_tokens = (
        claude_tokens * float(claude_meta.get("pricingCoverage") or 0)
        + codex_tokens * float(codex_meta.get("pricingCoverage") or 0)
    )
    sources = {claude_meta["pricingSource"], codex_meta["pricingSource"]} - {"none"}
    source = "mixed" if len(sources) > 1 else (next(iter(sources)) if sources else "none")
    return cast("StatusboardMeta", {
        "pricingSource": source,
        "pricingAsOf": codex_pricing.PRICING_AS_OF if codex_meta["pricingSource"] != "none"
        else claude_meta.get("pricingAsOf"),
        # `None` distinguishes no available price source from a known 0%
        # model coverage figure.
        "pricingCoverage": round(priced_tokens / total_tokens, 4) if total_tokens and sources else None,
        "ccusageReconciledAt": claude_meta.get("ccusageReconciledAt"),
        "ccusageTotalTokens": claude_meta.get("ccusageTotalTokens"),
        "ccusageOtherAgentsTokens": claude_meta.get("ccusageOtherAgentsTokens"),
        "totalTokensDiffPct": claude_meta.get("totalTokensDiffPct"),
    })


def _build_payload(scans: List[jsonl_parser.FileScan],
                   usage: "Any") -> "StatusboardArtifact":
    """Build one artifact body from a single adapter's scans and rollups."""
    jsonl = jsonl_parser.summarize(scans)
    _warn_injection_share(jsonl.get("filterStats"))
    advanced = build_advanced(scans, totals=usage["totals"], jsonl_summary=jsonl)
    return aggregator.aggregate(
        usage["totals"], usage["models"], usage["daily"], jsonl,
        advanced=advanced,
    )


def _agent_catalog() -> List["AgentDescriptor"]:
    """The UI rail's source-of-truth, including intentionally inert cards."""
    return [
        {
            "id": "claude-code", "label": "Claude Code",
            "state": "connected", "source": "Claude session JSONL",
        },
        {
            "id": "codex", "label": "Codex",
            "state": "connected", "source": "Codex session JSONL",
        },
        {
            "id": "gemini-cli", "label": "Gemini CLI",
            "state": "placeholder", "source": "Adapter not connected",
        },
        {
            "id": "aider", "label": "Aider",
            "state": "placeholder", "source": "Adapter not connected",
        },
    ]


def build_statusboard(jsonl_root: Optional[Path] = None,
                      cache_path: Optional[Path] = None) -> "StatusboardArtifact":
    """Run Claude Code and Codex collectors and return their unified artifact.

    ``jsonl_root`` remains the Claude test/CLI override.  Supplying it makes
    the build deliberately hermetic (no unrelated local Codex history leaks
    into a fixture/custom-root build); the normal launcher passes no override
    and reads both well-known directories.
    """
    t0 = time.monotonic()
    print("[1/4] jsonl: scanning Claude Code + Codex sessions ...", file=sys.stderr)
    claude_scans = jsonl_parser.scan_all(jsonl_root)
    codex_scans = [] if jsonl_root is not None else codex_parser.scan_all()
    t1 = time.monotonic()

    print("[2/4] native usage rollups (pricing from ccusage cache) ...",
          file=sys.stderr)
    cache_path = cache_path or CCUSAGE_CACHE_PATH
    pricing_info = reconcile.load_pricing(cache_path)
    claude_usage = native_usage.native_usage(
        claude_scans, pricing=pricing_info.get("prices") if pricing_info else None)
    # Codex sessions do not include invoices.  Use published OpenAI API rates
    # by token type as an explicitly labelled API-equivalent estimate; unknown
    # internal aliases remain unpriced rather than inheriting Claude rates.
    codex_usage = native_usage.native_usage(
        codex_scans, pricing=codex_pricing.CODEX_PRICES, fallback_missing=False)
    usage = native_usage.merge_usage_rollups([claude_usage, codex_usage])

    print("[3/4] advanced analytics ...", file=sys.stderr)
    print("[4/4] aggregating ...", file=sys.stderr)
    payload = _build_payload(claude_scans + codex_scans, usage)
    claude_payload = _build_payload(claude_scans, claude_usage)
    claude_payload["meta"] = _build_meta(pricing_info, claude_usage["models"])
    codex_payload = _build_payload(codex_scans, codex_usage)
    codex_payload["meta"] = _build_codex_meta(codex_usage["models"])
    payload["meta"] = _build_combined_meta(
        claude_payload["meta"], codex_payload["meta"],
        claude_usage["totals"]["totalTokens"], codex_usage["totals"]["totalTokens"],
    )
    payload["agents"] = _agent_catalog()
    payload["agentData"] = {
        "claude-code": claude_payload,
        "codex": codex_payload,
    }
    t2 = time.monotonic()

    print(
        f"[timing] scan={t1 - t0:.2f}s aggregate={t2 - t1:.2f}s "
        f"total={t2 - t0:.2f}s pricing={payload['meta']['pricingSource']}",
        file=sys.stderr,
    )
    return payload


def write_statusboard(out_path: Path, payload: Mapping[str, Any],
                      pretty: bool = False) -> None:
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
    top = s.get("mostUsedModel") or {}
    print(
        f"\n  -> wrote {out_path}\n"
        f"     totalTokens = {s.get('totalTokens'):,}"
        f" (vs ccusage {meta.get('totalTokensDiffPct')}%)\n"
        f"     totalTasks  = {s.get('totalTasks')}\n"
        f"     totalTime   = {s.get('totalTimeHuman')}\n"
        f"     avgTask     = {s.get('averageTaskHuman')}\n"
        f"     topModel    = {top.get('modelName')}\n"
        f"     pricing     = {meta.get('pricingSource')}"
        f" as of {meta.get('pricingAsOf') or 'never'}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Build coding-agent statusboard.json")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output path")
    p.add_argument(
        "--watch",
        action="store_true",
        help="Re-run on Claude Code or Codex JSONL changes",
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
    print("[watch] watching Claude Code + Codex session logs ...", file=sys.stderr)

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
