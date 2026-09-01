"""
aggregator.py
=============

Joins the native usage rollups (tokens/cost/models, see native_usage.py)
with the JSONL rollups (tasks/time/projects/sessions) into the unified
statusboard.json shape described in the plan:

    {
      "summary":  { totalTokens, totalTasks, totalTime, averageTask, mostUsedModel },
      "tokens":   { total, input, output, cacheCreation, cacheRead, cost },
      "models":   [ {modelName, totalTokens, sharePct, ...}, ... ],
      "tasks":    { totalTasks, totalActiveSeconds, averageSeconds, maxSeconds, busiestDay },
      "projects": [ {project, tasks, activeSeconds, tokens, cost, ...}, ... ],
      "sessions": [ {sessionId, project, tokens, cost, ...}, ... ],
      "dailyActivity": [ {date, tokens, tasks, activeSeconds, cost}, ... ],
      "advanced": { toolUsage, workflowTimeline, promptCategories, taskDurations, modelEfficiency },
      "generatedAt": "ISO timestamp"
    }

The aggregator is the "single source of truth" - it doesn't import ccusage,
native_usage or jsonl_parser, and never touches the filesystem.  Pass in
the already-parsed/normalized data instead.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

if TYPE_CHECKING:
    from .contracts import (
        DailyUsageSlot,
        JsonlSummary,
        ModelUsageRow,
        StatusboardArtifact,
        TokenUsage,
        UsageTotals,
    )


def _fmt_seconds(secs: int) -> str:
    """Render seconds as 'Xh Ym' or 'Ym' for compact display."""
    if secs <= 0:
        return "0m"
    h, rem = divmod(int(secs), 3600)
    m = rem // 60
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def most_used_model(models: List["ModelUsageRow"]) -> Optional[Dict[str, Any]]:
    """Pick the model with the largest totalTokens share."""
    if not models:
        return None
    total = sum(m["totalTokens"] for m in models) or 1
    top = models[0]
    return {
        "modelName": top["modelName"],
        "totalTokens": top["totalTokens"],
        "sharePct": round(100 * top["totalTokens"] / total, 1),
    }


def busiest_day(daily_activity: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not daily_activity:
        return None
    busiest = max(daily_activity, key=lambda d: d.get("tasks", 0))
    return busiest


def merge_daily(
    usage_daily: List["DailyUsageSlot"],
    jsonl_daily_tasks: List[Dict[str, Any]],
    jsonl_daily_active: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Left-joined per-day series keyed by date.  We iterate over the union of
    dates seen by both sources so days that only have token data (e.g. agent
    ran without user prompts) still appear.  Slots created for JSONL-only
    dates carry the full token shape so downstream consumers never see
    missing fields.
    """
    def empty_slot(date: str) -> Dict[str, Any]:
        return {
            "date": date,
            "tokens": 0,
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "cost": 0.0,
            "tasks": 0,
            "activeSeconds": 0,
        }

    by_date: Dict[str, Dict[str, Any]] = {}
    for d in usage_daily:
        slot = empty_slot(d["date"])
        slot.update({
            "tokens": d["totalTokens"],
            "inputTokens": d["inputTokens"],
            "outputTokens": d["outputTokens"],
            "cacheCreationTokens": d["cacheCreationTokens"],
            "cacheReadTokens": d["cacheReadTokens"],
            "cost": d["totalCost"],
        })
        by_date[d["date"]] = slot
    for t in jsonl_daily_tasks:
        slot = by_date.setdefault(t["date"], empty_slot(t["date"]))
        slot["tasks"] = t["tasks"]
    for a in jsonl_daily_active:
        slot = by_date.setdefault(a["date"], empty_slot(a["date"]))
        slot["activeSeconds"] = a["activeSeconds"]
    out = sorted(by_date.values(), key=lambda d: d["date"])
    return out


def aggregate(
    totals: "UsageTotals",
    models: List["ModelUsageRow"],
    ccusage_daily: List["DailyUsageSlot"],
    jsonl_summary: "JsonlSummary",
    advanced: Optional[Dict[str, Any]] = None,
) -> "StatusboardArtifact":
    """
    Build the final statusboard.json payload.

    `totals` is the native usage totals dict, `models` the per-model
    breakdown and `ccusage_daily` the per-day usage series — all prepared
    by the caller (build_statusboard) from native_usage's rollups.
    `jsonl_summary` is jsonl_parser.summarize()'s output.
    `advanced` is the optional Phase-4 analytics payload.
    """
    daily = merge_daily(
        ccusage_daily,
        list(jsonl_summary.get("dailyTasks", [])),
        list(jsonl_summary.get("dailyActive", [])),
    )

    total_tasks = jsonl_summary.get("totalTasks", 0)
    total_active = jsonl_summary.get("totalActiveSeconds", 0)
    avg_task = int(total_active / total_tasks) if total_tasks else 0

    # Project/session tokens are measured directly from the JSONL usage
    # records (see jsonl_parser).  Cost is priced per model using unit prices
    # derived from ccusage's daily modelBreakdowns, with the global average
    # as fallback for models ccusage has no price data for.
    ccusage_total_tokens = totals["totalTokens"] or 1
    ccusage_total_cost = totals["totalCost"]
    avg_price = ccusage_total_cost / ccusage_total_tokens
    price_by_model = {
        m["modelName"]: m["cost"] / m["totalTokens"]
        for m in models
        if m["totalTokens"] > 0
    }

    def price(model_usage: Optional[Dict[str, "TokenUsage"]]) -> float:
        cost = 0.0
        for name, usage in (model_usage or {}).items():
            model_tokens = (
                usage.get("inputTokens", 0)
                + usage.get("outputTokens", 0)
                + usage.get("cacheCreationTokens", 0)
                + usage.get("cacheReadTokens", 0)
            )
            cost += model_tokens * price_by_model.get(name, avg_price)
        return cost

    projects_out: List[Dict[str, Any]] = []
    for proj in jsonl_summary.get("projects", []):
        projects_out.append({
            "project": proj["project"],
            "projectPath": proj["projectPath"],
            "tasks": proj["tasks"],
            "activeSeconds": proj["activeSeconds"],
            "activeHuman": _fmt_seconds(proj["activeSeconds"]),
            "tokens": proj.get("tokens", 0),
            "cost": round(price(proj.get("modelUsage")), 4),
            "files": proj["files"],
            # A zero-task project has no average (its active time is 0 by
            # construction — this guards adversarial input, not division).
            "averageSeconds": int(proj["activeSeconds"] / proj["tasks"]) if proj["tasks"] else 0,
        })

    sessions_out: List[Dict[str, Any]] = []
    for sess in jsonl_summary.get("sessions", []):
        sessions_out.append({
            "sessionId": sess["sessionId"],
            "project": sess["project"],
            "projectPath": sess.get("projectPath"),
            "files": sess["files"],
            "tasks": sess["tasks"],
            "activeSeconds": sess["activeSeconds"],
            "activeHuman": _fmt_seconds(sess["activeSeconds"]),
            "tokens": sess.get("tokens", 0),
            "cost": round(price(sess.get("modelUsage")), 4),
            "averageSeconds": int(sess["activeSeconds"] / sess["tasks"]) if sess["tasks"] else 0,
            "firstTs": sess.get("firstTs"),
            "lastTs": sess.get("lastTs"),
        })

    summary = {
        "totalTokens": totals["totalTokens"],
        "totalTasks": total_tasks,
        "totalTime": total_active,                # seconds (raw)
        "totalTimeHuman": _fmt_seconds(total_active),
        "averageTask": avg_task,                  # seconds per task (raw)
        "averageTaskHuman": _fmt_seconds(avg_task),
        "mostUsedModel": most_used_model(models),
        "totalCost": totals["totalCost"],
    }

    return cast("StatusboardArtifact", {
        "summary": summary,
        "tokens": {
            "total": totals["totalTokens"],
            "input": totals["inputTokens"],
            "output": totals["outputTokens"],
            "cacheCreation": totals["cacheCreationTokens"],
            "cacheRead": totals["cacheReadTokens"],
            "cost": totals["totalCost"],
        },
        "models": [
            {
                "modelName": m["modelName"],
                "totalTokens": m["totalTokens"],
                "inputTokens": m["inputTokens"],
                "outputTokens": m["outputTokens"],
                "cacheCreationTokens": m.get("cacheCreationTokens", 0),
                "cacheReadTokens": m.get("cacheReadTokens", 0),
                "cost": m["cost"],
                "sharePct": round(100 * m["totalTokens"] / ccusage_total_tokens, 1),
            }
            for m in models
        ],
        "tasks": {
            "total": total_tasks,
            "activeSeconds": total_active,
            "activeHuman": _fmt_seconds(total_active),
            "averageSeconds": avg_task,
            "averageHuman": _fmt_seconds(avg_task),
            # Real longest inter-task interval from advanced analytics.
            # Deliberately NO fallback: when no intervals were observed this
            # stays 0 ("unknown") rather than borrowing a project average.
            "longestSeconds": (advanced or {}).get("taskDurations", {}).get("longest", 0),
            "longestAverageSeconds": max(
                (p.get("averageSeconds", 0) for p in projects_out if p.get("tasks")),
                default=0,
            ),
            "hourlyTasks": jsonl_summary.get("hourlyTasks", []),
            # Task-population sentinel: how user-shaped entries were
            # classified (see jsonl_parser.summarize).  An upstream JSONL
            # format change shows up here before anything breaks.
            "filterStats": jsonl_summary.get("filterStats"),
            "busiestDay": busiest_day(daily),
        },
        "projects": projects_out,
        "sessions": sessions_out,
        "dailyActivity": daily,
        "advanced": advanced or {},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    })
