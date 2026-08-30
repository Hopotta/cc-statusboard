"""
aggregator.py
=============

Joins ccusage (token/cost/model) with JSONL (tasks/time/projects) into the
unified statusboard.json shape described in the plan:

    {
      "summary":  { totalTokens, totalTasks, totalTime, averageTask, mostUsedModel },
      "tokens":   { total, input, output, cacheCreation, cacheRead, cost },
      "models":   [ {modelName, totalTokens, sharePct, ...}, ... ],
      "tasks":    { totalTasks, totalActiveSeconds, averageSeconds, maxSeconds, busiestDay },
      "projects": [ {project, tasks, activeSeconds, tokens, cost, ...}, ... ],
      "dailyActivity": [ {date, tokens, tasks, activeSeconds, cost}, ... ],
      "advanced": { toolUsage, workflowTimeline, promptCategories, modelEfficiency },
      "generatedAt": "ISO timestamp"
    }

The aggregator is the "single source of truth" - it doesn't import ccusage or
touch JSONL directly.  Pass in the already-parsed data instead.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING


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


def most_used_model(models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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


def longest_task(task_durations: List[int]) -> int:
    return max(task_durations) if task_durations else 0


def merge_daily(
    ccusage_daily: List[Dict[str, Any]],
    jsonl_daily_tasks: List[Dict[str, Any]],
    jsonl_daily_active: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Left-joined per-day series keyed by date.  We iterate over the union of
    dates seen by both sources so days that only have token data (e.g. agent
    ran without user prompts) still appear.
    """
    by_date: Dict[str, Dict[str, Any]] = {}
    for d in ccusage_daily:
        by_date[d["date"]] = {
            "date": d["date"],
            "tokens": d["totalTokens"],
            "inputTokens": d["inputTokens"],
            "outputTokens": d["outputTokens"],
            "cacheCreationTokens": d["cacheCreationTokens"],
            "cacheReadTokens": d["cacheReadTokens"],
            "cost": d["totalCost"],
            "tasks": 0,
            "activeSeconds": 0,
        }
    for t in jsonl_daily_tasks:
        slot = by_date.setdefault(t["date"], {"date": t["date"], "tokens": 0, "cost": 0.0})
        slot["tasks"] = t["tasks"]
    for a in jsonl_daily_active:
        slot = by_date.setdefault(a["date"], {"date": a["date"], "tokens": 0, "cost": 0.0})
        slot["activeSeconds"] = a["activeSeconds"]
    out = sorted(by_date.values(), key=lambda d: d["date"])
    return out


def aggregate(
    ccusage_session_raw: Dict[str, Any],
    ccusage_daily_raw: Dict[str, Any],
    jsonl_summary: Dict[str, Any],
    advanced: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the final statusboard.json payload.

    Arguments are the already-parsed outputs from ccusage_parser and jsonl_parser.
    `advanced` is the optional Phase-4 analytics payload (tool usage, timeline, etc).
    """
    from .ccusage_parser import (
        daily_series,
        model_breakdown_from_daily,
        normalize_totals,
    )

    totals = normalize_totals(ccusage_session_raw)
    models = model_breakdown_from_daily(ccusage_daily_raw)
    daily = merge_daily(
        daily_series(ccusage_daily_raw),
        jsonl_summary.get("dailyTasks", []),
        jsonl_summary.get("dailyActive", []),
    )

    total_tasks = jsonl_summary.get("totalTasks", 0)
    total_active = jsonl_summary.get("totalActiveSeconds", 0)
    avg_task = int(total_active / total_tasks) if total_tasks else 0

    # Per-project tokens are measured directly from the JSONL usage records
    # (see jsonl_parser.project_breakdown).  Cost is priced per model using
    # unit prices derived from ccusage's daily modelBreakdowns, with the
    # global average as fallback for models ccusage has no price data for.
    ccusage_session_totals = ccusage_session_raw.get("totals") or {}
    ccusage_total_tokens = int(ccusage_session_totals.get("totalTokens", 0)) or 1
    ccusage_total_cost = float(ccusage_session_totals.get("totalCost", 0.0))
    avg_price = ccusage_total_cost / ccusage_total_tokens
    price_by_model = {
        m["modelName"]: m["cost"] / m["totalTokens"]
        for m in models
        if m["totalTokens"] > 0
    }

    projects_out: List[Dict[str, Any]] = []
    for proj in jsonl_summary.get("projects", []):
        proj_tasks = max(1, proj["tasks"])
        proj_cost = 0.0
        for name, usage in (proj.get("modelUsage") or {}).items():
            model_tokens = (
                usage.get("inputTokens", 0)
                + usage.get("outputTokens", 0)
                + usage.get("cacheCreationTokens", 0)
                + usage.get("cacheReadTokens", 0)
            )
            proj_cost += model_tokens * price_by_model.get(name, avg_price)
        projects_out.append({
            "project": proj["project"],
            "projectPath": proj["projectPath"],
            "tasks": proj["tasks"],
            "activeSeconds": proj["activeSeconds"],
            "activeHuman": _fmt_seconds(proj["activeSeconds"]),
            "tokens": proj.get("tokens", 0),
            "cost": round(proj_cost, 4),
            "files": proj["files"],
            "averageSeconds": int(proj["activeSeconds"] / proj_tasks),
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

    return {
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
            # Real longest task from advanced analytics (falls back to project-mean).
            "longestSeconds": (advanced or {}).get("taskDurations", {}).get("longest", 0)
                or max(
                    (p["averageSeconds"] for p in projects_out if p.get("tasks")),
                    default=0,
                ),
            "longestAverageSeconds": max(
                (p.get("averageSeconds", 0) for p in projects_out if p.get("tasks")),
                default=0,
            ),
            "hourlyTasks": jsonl_summary.get("hourlyTasks", []),
            "busiestDay": busiest_day(daily),
        },
        "projects": projects_out,
        "dailyActivity": daily,
        "advanced": advanced or {},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }