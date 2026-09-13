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

from typing import Any, Dict, List, Mapping, Optional, Union, cast

from .jsonl_parser import FileScan
from .contracts import UsageRollups

_TOKEN_FIELDS = ("inputTokens", "outputTokens",
                 "cacheCreationTokens", "cacheReadTokens")
Price = Union[float, Mapping[str, float]]


def _empty_bucket() -> Dict[str, int]:
    return {f: 0 for f in _TOKEN_FIELDS}


def _cost_bucket(bucket: Mapping[str, int], price: Price) -> float:
    """Price one usage bucket with a blended or token-type-specific rate."""
    if isinstance(price, (int, float)):
        return sum(bucket.get(field, 0) for field in _TOKEN_FIELDS) * price
    return (
        bucket.get("inputTokens", 0) * price.get("input", 0.0)
        + bucket.get("outputTokens", 0) * price.get("output", 0.0)
        + bucket.get("cacheCreationTokens", 0) * price.get("cacheCreation", 0.0)
        + bucket.get("cacheReadTokens", 0) * price.get("cacheRead", 0.0)
    )


def native_usage(scans: List[FileScan],
                 pricing: Optional[Mapping[str, Price]] = None,
                 fallback_missing: bool = True) -> UsageRollups:
    """Roll scans up into {totals, models, daily}.

    `pricing` maps model name -> blended unit price (cost per token),
    derived offline from ccusage's daily modelBreakdowns.  A price of 0.0
    present in the table is an explicit price (free model / missing from
    ccusage's LiteLLM table) and is honored as-is.  Models with NO table
    entry fall back to the blended unit price of the priced universe:
    `priced_cost / priced_tokens` — the standard weighted average, not
    diluted by unpriced volume.  Without pricing every cost is 0.0 and the
    artifact's `meta.pricingSource` flags the gap.
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

    # Two-pass pricing: priced models first, then the blended average of
    # the priced universe for models the table doesn't cover at all.
    costs: Dict[str, float] = {}
    priced_cost = 0.0
    priced_tokens = 0
    if pricing:
        for name, bucket in models_acc.items():
            price = pricing.get(name)
            if price is not None:
                tokens = sum(bucket[f] for f in _TOKEN_FIELDS)
                c = round(_cost_bucket(bucket, price), 6)
                costs[name] = c
                priced_cost += c
                priced_tokens += tokens
    avg_price = (priced_cost / priced_tokens) if priced_cost and priced_tokens else 0.0
    for name, bucket in models_acc.items():
        if name not in costs and fallback_missing:
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
            price = (pricing or {}).get(name)
            if price is not None:
                slot_cost += round(_cost_bucket(bucket, price), 6)
            elif fallback_missing:
                slot_cost += round(day_tokens * avg_price, 6)
        slot["totalCost"] = round(slot_cost, 6)
        slot["totalTokens"] = sum(slot[f] for f in _TOKEN_FIELDS)
        daily.append(slot)

    return cast(UsageRollups, {
        "totals": {**totals, "totalCost": total_cost},
        "models": models,
        "daily": daily,
    })


def merge_usage_rollups(rollups: List[UsageRollups]) -> UsageRollups:
    """Combine already-priced agent rollups without leaking one price table
    into another agent's models.

    Claude's ccusage-derived prices must never be used as a fallback for
    Codex rows.  Merge after each adapter has independently computed usage
    and cost instead.
    """
    models_acc: Dict[str, Dict[str, Any]] = {}
    daily_acc: Dict[str, Dict[str, Any]] = {}

    for rollup in rollups:
        for model in rollup["models"]:
            acc = models_acc.setdefault(model["modelName"], {
                "modelName": model["modelName"],
                "totalTokens": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheCreationTokens": 0,
                "cacheReadTokens": 0,
                "cost": 0.0,
            })
            for key in (*_TOKEN_FIELDS, "totalTokens"):
                acc[key] += model.get(key, 0)
            acc["cost"] += model.get("cost", 0.0)
        for day in rollup["daily"]:
            acc = daily_acc.setdefault(day["date"], {
                "date": day["date"], "totalTokens": 0, "totalCost": 0.0,
                **_empty_bucket(),
            })
            for key in (*_TOKEN_FIELDS, "totalTokens"):
                acc[key] += day.get(key, 0)
            acc["totalCost"] += day.get("totalCost", 0.0)

    models: List[Dict[str, Any]] = sorted(
        models_acc.values(), key=lambda row: row["totalTokens"], reverse=True)
    daily: List[Dict[str, Any]] = [daily_acc[day] for day in sorted(daily_acc)]
    totals: Dict[str, Any] = _empty_bucket()
    for merged_model in models:
        for key in _TOKEN_FIELDS:
            totals[key] += merged_model[key]
    totals["totalTokens"] = sum(totals.values())
    totals["totalCost"] = round(sum(float(model["cost"]) for model in models), 6)
    return cast(UsageRollups, {"totals": totals, "models": models, "daily": daily})
