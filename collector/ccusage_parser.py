"""
ccusage_parser.py
=================

Wraps the `ccusage` CLI and parses its JSON output into a normalized
shape that the aggregator can consume.

Output of ccusage session --json (top-level):
    {
        "session": [ {session...}, ... ],
        "totals":  { total tokens, cost, ... }
    }

Output of ccusage daily --json (top-level):
    {
        "daily":   [ {day...}, ... ],
        "totals":  { total tokens, cost, ... }
    }

Output of ccusage monthly --json (top-level):
    {
        "monthly": [ {month...}, ... ],
        "totals":  { total tokens, cost, ... }
    }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


def _find_ccusage() -> Optional[str]:
    """Locate a runnable ccusage binary.

    Order of search:
      1. shutil.which("ccusage")
      2. npm prefix bin directory (npm i -g ccusage)
      3. local node_modules/.bin (project-local install)
      4. fall through to None -> we will use `npx`.
    """
    found = shutil.which("ccusage")
    if found:
        return found

    # Try the npm global prefix.
    try:
        npm_prefix = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10, check=False
        )
        if npm_prefix.returncode == 0 and npm_prefix.stdout.strip():
            cand = os.path.join(npm_prefix.stdout.strip(), ".bin", "ccusage")
            if os.path.isfile(cand):
                return cand
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try local node_modules.
    local = os.path.join(os.getcwd(), "node_modules", ".bin", "ccusage")
    if os.path.isfile(local):
        return local

    return None


def _find_npx() -> Optional[str]:
    """Find npx on the system (works around PATH issues when running via Python)."""
    npx = shutil.which("npx")
    if npx:
        return npx
    # Common install paths on Windows.
    candidates = [
        os.path.expandvars(r"%APPDATA%\npm\npx.cmd"),
        os.path.expandvars(r"%APPDATA%\npm\npx"),
        r"C:\Program Files\nodejs\npx.cmd",
        "/usr/local/bin/npx",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _run_ccusage(args: List[str], timeout: int = 60) -> Dict[str, Any]:
    """Run ccusage with the given args, return parsed JSON dict."""
    ccusage_bin = _find_ccusage()
    if ccusage_bin:
        cmd = [ccusage_bin, *args, "--json"]
        use_shell = False
    else:
        npx = _find_npx()
        if not npx:
            raise RuntimeError(
                "ccusage not found and no npx available. Install with `npm i -g ccusage`."
            )
        cmd = [npx, "--yes", "ccusage", *args, "--json"]
        # On Windows .cmd shims need shell=True.
        use_shell = sys.platform == "win32"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=use_shell,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ccusage not found - install with `npm i -g ccusage`") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"ccusage {args} failed: rc={proc.returncode} stderr={proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"ccusage {args} returned non-JSON output: {proc.stdout[:300]}"
        ) from exc


def parse_session() -> Dict[str, Any]:
    """Return ccusage session --json output (raw)."""
    return _run_ccusage(["session"])


def parse_daily(timeout: int = 60) -> Dict[str, Any]:
    """Return ccusage daily --json output (raw).

    The reconciler passes a generous timeout (~300 s): the CLI needs
    ~30 s per call at ~283 MB of JSONL, and more as the corpus grows.
    """
    return _run_ccusage(["daily"], timeout=timeout)


def parse_monthly() -> Dict[str, Any]:
    """Return ccusage monthly --json output (raw)."""
    return _run_ccusage(["monthly"])


def _to_int(value: Any) -> int:
    """Tolerant int conversion: ccusage may emit nulls or numeric strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_totals(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce ccusage's `totals` block to the shape we use everywhere:

        {
            "totalTokens": int,
            "inputTokens": int,
            "outputTokens": int,
            "cacheCreationTokens": int,
            "cacheReadTokens": int,
            "totalCost": float
        }
    """
    t = raw.get("totals") or {}
    return {
        "totalTokens": _to_int(t.get("totalTokens")),
        "inputTokens": _to_int(t.get("inputTokens")),
        "outputTokens": _to_int(t.get("outputTokens")),
        "cacheCreationTokens": _to_int(t.get("cacheCreationTokens")),
        "cacheReadTokens": _to_int(t.get("cacheReadTokens")),
        "totalCost": _to_float(t.get("totalCost")),
    }


def model_breakdown_from_daily(daily_raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Aggregate per-model totals across all daily entries.

    ccusage's `modelBreakdowns` entries do NOT include `totalTokens` directly
    - we have to sum input/output/cache tokens ourselves.

    Returns list sorted by totalTokens desc:
        [{"modelName": str, "totalTokens": int, "inputTokens": int,
          "outputTokens": int, "cost": float}, ...]
    """
    bucket: Dict[str, Dict[str, Any]] = {}
    for day in daily_raw.get("daily", []):
        for mb in day.get("modelBreakdowns", []) or []:
            name = mb.get("modelName") or "unknown"
            entry = bucket.setdefault(name, {
                "modelName": name,
                "totalTokens": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheCreationTokens": 0,
                "cacheReadTokens": 0,
                "cost": 0.0,
            })
            inp = int(mb.get("inputTokens", 0))
            out = int(mb.get("outputTokens", 0))
            cc = int(mb.get("cacheCreationTokens", 0))
            cr = int(mb.get("cacheReadTokens", 0))
            entry["inputTokens"] += inp
            entry["outputTokens"] += out
            entry["cacheCreationTokens"] += cc
            entry["cacheReadTokens"] += cr
            entry["totalTokens"] += inp + out + cc + cr
            entry["cost"] += float(mb.get("cost", 0.0))
    return sorted(bucket.values(), key=lambda x: x["totalTokens"], reverse=True)


def daily_series(daily_raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-day rollup list sorted by date asc."""
    out = []
    for day in daily_raw.get("daily", []):
        out.append({
            "date": day.get("period"),
            "totalTokens": int(day.get("totalTokens", 0)),
            "inputTokens": int(day.get("inputTokens", 0)),
            "outputTokens": int(day.get("outputTokens", 0)),
            "cacheCreationTokens": int(day.get("cacheCreationTokens", 0)),
            "cacheReadTokens": int(day.get("cacheReadTokens", 0)),
            "totalCost": float(day.get("totalCost", 0.0)),
        })
    out.sort(key=lambda d: d["date"] or "")
    return out


if __name__ == "__main__":
    # Smoke test
    sess = parse_session()
    daily = parse_daily()
    print("session entries:", len(sess.get("session", [])))
    print("daily entries:", len(daily.get("daily", [])))
    print("totals:", normalize_totals(sess))
    print("models:", model_breakdown_from_daily(daily)[:3])