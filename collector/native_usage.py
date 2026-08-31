"""
native_usage.py
===============

JSONL-native global usage rollups: totals, per-model breakdown and daily
series, computed from the already-parsed `FileScan` objects (usage deduped
per `message.id` at scan time).

This is the A3 flip (2026-08-31 status report §5.1–5.3): the global
aggregation no longer runs through the ccusage CLI.  ccusage is an
O(all-data) external process (28–32 s at ~283 MB, fatal in parallel), so
running it on the rebuild path meant the dashboard's token/model/daily
numbers froze during active use.  The JSONL scan already carries every
usage record, so the rollups below cost ~nothing and are always fresh.
ccusage is demoted to an offline reconciler / pricing source (see
reconcile.py): its daily modelBreakdowns still provide the per-model unit
prices passed in here as `pricing`.

Daily dates are UTC (`timestamp[:10]`), matching the task daily buckets
and ccusage's own day boundaries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from .jsonl_parser import FileScan
from .contracts import UsageRollups

_TOKEN_FIELDS = ("inputTokens", "outputTokens",
                 "cacheCreationTokens", "cacheReadTokens")


def _empty_bucket() -> Dict[str, int]:
    return {f: 0 for f in _TOKEN_FIELDS}


def native_usage(scans: List[FileScan],
                 pricing: Optional[Dict[str, float]] = None) -> UsageRollups:
    """Roll scans up into {totals, models, daily}.

    `pricing` maps model name -> blended unit price (cost per token),
    derived offline from ccusage's daily modelBreakdowns.  Models without
    a price fall back to the global average unit price (priced cost /
    all tokens) — the same fallback the project/session pricing uses.
    Without pricing every cost is 0.0 and the artifact's `meta.pricing`
    flags the gap.
    """
    models_acc: Dict[str, Dict[str, int]] = {}
    daily_acc: Dict[str, Dict[str, Dict[str, int]]] = {}

    for s in scans:
        for name, bucket in s.model_usage.items():
            acc = models_acc.setdefault(name, _empty_bucket())
            for f in _TOKEN_FIELDS:
                acc[f] += bucket.get(f, 0)
        for day, per_model in s.usage_daily.items():
            day_models = daily_acc.setdefault(day, {})
            for name, bucket in per_model.items():
                acc = day_models.setdefault(name, _empty_bucket())
                for f in _TOKEN_FIELDS:
                    acc[f] += bucket.get(f, 0)

    totals: Dict[str, int] = _empty_bucket()
    for bucket in models_acc.values():
        for f in _TOKEN_FIELDS:
            totals[f] += bucket[f]
    totals["totalTokens"] = sum(totals.values())
    all_tokens = totals["totalTokens"]

    # Two-pass pricing: priced models first, then the blended average for
    # the rest (avg = priced cost / ALL tokens, mirroring the aggregator).
    costs: Dict[str, float] = {}
    priced_cost = 0.0
    if pricing:
        for name, bucket in models_acc.items():
            price = pricing.get(name)
            if price is not None:
                c = round(sum(bucket[f] for f in _TOKEN_FIELDS) * price, 6)
                costs[name] = c
                priced_cost += c
    avg_price = (priced_cost / all_tokens) if priced_cost and all_tokens else 0.0
    for name, bucket in models_acc.items():
        if name not in costs:
            costs[name] = round(sum(bucket[f] for f in _TOKEN_FIELDS) * avg_price, 6)
    total_cost = round(sum(costs.values()), 6)

    models: List[Dict[str, Any]] = []
    for name, bucket in models_acc.items():
        total = sum(bucket[f] for f in _TOKEN_FIELDS)
        models.append({
            "modelName": name,
            "totalTokens": total,
            "inputTokens": bucket["inputTokens"],
            "outputTokens": bucket["outputTokens"],
            "cacheCreationTokens": bucket["cacheCreationTokens"],
            "cacheReadTokens": bucket["cacheReadTokens"],
            "cost": costs.get(name, 0.0),
        })
    models.sort(key=lambda m: m["totalTokens"], reverse=True)

    daily: List[Dict[str, Any]] = []
    for day in sorted(daily_acc):
        slot_models = daily_acc[day]
        slot: Dict[str, Any] = {"date": day, "totalCost": 0.0}
        for f in _TOKEN_FIELDS:
            slot[f] = 0
        slot_cost = 0.0
        for name, bucket in slot_models.items():
            for f in _TOKEN_FIELDS:
                slot[f] += bucket[f]
            day_tokens = sum(bucket[f] for f in _TOKEN_FIELDS)
            price = (pricing or {}).get(name, avg_price)
            slot_cost += round(day_tokens * price, 6)
        slot["totalCost"] = round(slot_cost, 6)
        slot["totalTokens"] = sum(slot[f] for f in _TOKEN_FIELDS)
        daily.append(slot)

    return cast(UsageRollups, {
        "totals": {**totals, "totalCost": total_cost},
        "models": models,
        "daily": daily,
    })
