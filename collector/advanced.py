"""
advanced.py
===========

Higher-order analytics derived from JSONL session scans (`jsonl_parser.scan_all`).

Provides:
    - tool usage stats:      how often each tool was invoked, per project
    - agent workflow timeline: user→assistant→tool sequence per recent session
    - prompt categories:      simple heuristic buckets for user prompts
    - model efficiency:       tokens / task, cost / task, cache share
    - task duration stats:    longest / p50 / p90 (no raw array in the payload)

The heuristics here are intentionally simple — they're meant to be
    suggestive, not authoritative.  See PROMPT_CATEGORIES for the keyword map.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .jsonl_parser import (
    FileScan,
    MAX_TASK_DURATION_SECONDS,
    project_groups,
    scan_all,
)

# Heuristic prompt categories — best-effort, regex based.
PROMPT_CATEGORIES: List[Tuple[str, str, List[str]]] = [
    ("debug", "Debug / fix", [
        r"\bbug\b", r"\bfix\b", r"\berror\b", r"\bcrash\b", r"\bbroken\b",
        r"why is .* not", r"doesn't work", r"fails to", r"报错", r"崩溃",
        r"修复", r"问题", r"失败",
    ]),
    ("refactor", "Refactor", [
        r"\brefactor\b", r"\brestructur", r"\breorganiz", r"\bcleanup\b",
        r"重构", r"整理", r"清理",
    ]),
    ("feature", "New feature", [
        r"\badd\b.*\bfeature\b", r"\bimplement\b", r"\bcreate\b", r"\bbuild\b",
        r"加.*功能", r"实现", r"创建", r"添加",
    ]),
    ("explain", "Explain / docs", [
        r"\bexplain\b", r"\bwhat does\b", r"\bhow does\b", r"\bdocs?\b",
        r"说明", r"解释", r"文档",
    ]),
    ("plan", "Plan / design", [
        r"\bplan\b", r"\bdesign\b", r"\barchitect", r"\bschema\b",
        r"规划", r"设计", r"架构",
    ]),
    ("review", "Review / test", [
        r"\breview\b", r"\btest\b", r"\bcheck\b", r"\bverify\b",
        r"审查", r"测试", r"检查", r"验证",
    ]),
    ("config", "Config / setup", [
        r"\bconfigur", r"\bset up\b", r"\bsetup\b", r"\binstall\b",
        r"配置", r"安装",
    ]),
    ("explore", "Explore", [
        r"\bfind\b", r"\bsearch\b", r"\bwhere\b", r"\bwhich\b",
        r"找", r"搜索",
    ]),
]


def _classify_prompt(text: str) -> str:
    """Return a category slug for a user-prompt string."""
    if not text:
        return "other"
    for slug, _, patterns in PROMPT_CATEGORIES:
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return slug
    return "other"


def build_tool_usage(scans: List[FileScan]) -> Dict[str, Any]:
    """
    Count tool invocations across all sessions.  Subagent sidechains are
    grouped under their parent project, using the same project labels as
    the project table.
    """
    counts: Counter[str] = Counter()
    by_project: Dict[str, Counter[str]] = defaultdict(Counter)

    for _, label, group in project_groups(scans):
        project_counter: Counter[str] = Counter()
        for s in group:
            counts.update(s.tool_counts)
            project_counter.update(s.tool_counts)
        if project_counter:
            by_project[label] = project_counter

    return {
        "tools": [
            {"name": name, "count": cnt}
            for name, cnt in counts.most_common()
        ],
        "byProject": {
            proj: [{"name": n, "count": c} for n, c in items.most_common()]
            for proj, items in by_project.items()
        },
        "total": sum(counts.values()),
        "uniqueTools": len(counts),
    }


def build_workflow_timeline(scans: List[FileScan],
                            max_events_per_session: int = 80) -> Dict[str, Any]:
    """
    Coarse timeline of the recent sessions (only scans with timeline events;
    `scan_all` populates those for the most recent main sessions).
    """
    recent = [s for s in scans
              if s.timeline_events and not s.is_subagent]
    recent.sort(key=lambda s: s.mtime, reverse=True)

    out: List[Dict[str, Any]] = []
    for s in recent:
        events = list(s.timeline_events)
        # Trim to max_events_per_session, keeping first and last.
        if len(events) > max_events_per_session:
            head = events[:max_events_per_session // 2]
            tail = events[-(max_events_per_session // 2):]
            events = head + tail
        out.append({
            "sessionId": s.path.stem,
            "file": str(s.path),
            "events": events,
            "firstEvent": events[0]["t"],
            "lastEvent": events[-1]["t"],
        })
    return {"sessions": out, "count": len(out)}


def build_prompt_categories(scans: List[FileScan]) -> Dict[str, Any]:
    """Bucket user prompts by heuristic category (same task set as tasks)."""
    counts: Counter[str] = Counter()
    examples: Dict[str, List[str]] = defaultdict(list)
    label_map = {slug: label for slug, label, _ in PROMPT_CATEGORIES}

    for s in scans:
        if s.is_subagent:
            continue
        for text in s.user_texts:
            cat = _classify_prompt(text)
            counts[cat] += 1
            # Keep at most 1 example per category to keep JSON small.
            if len(examples[cat]) < 1 and text.strip():
                examples[cat].append(text[:120].replace("\n", " "))

    total = sum(counts.values()) or 1
    return {
        "categories": [
            {
                "slug": slug,
                "label": label_map.get(slug, slug),
                "count": counts.get(slug, 0),
                "sharePct": round(100 * counts.get(slug, 0) / total, 1),
            }
            for slug in [s for s, *_ in PROMPT_CATEGORIES] + ["other"]
        ],
        "total": total,
        "examples": examples,
    }


def build_task_durations(scans: List[FileScan]) -> Dict[str, Any]:
    """
    Duration stats for real user tasks (main sessions only): each duration is
    `next_task_ts - this_task_ts`, capped at 2h per the spec.  Emits fixed-size
    stats — the raw array never enters the payload.
    """
    durations: List[int] = []
    for s in scans:
        if s.is_subagent:
            continue
        dts = s.task_dts
        for i in range(len(dts) - 1):
            d = (dts[i + 1] - dts[i]).total_seconds()
            if d < 0:
                d = 0
            if d > MAX_TASK_DURATION_SECONDS:
                d = MAX_TASK_DURATION_SECONDS
            durations.append(int(d))

    durations.sort()
    n = len(durations)

    def pct(q: float) -> int:
        # Linear interpolation between neighbouring samples (numpy-style).
        if not n:
            return 0
        pos = q * (n - 1)
        low = int(pos)
        high = min(low + 1, n - 1)
        frac = pos - low
        return int(durations[low] + (durations[high] - durations[low]) * frac)

    return {
        "longest": durations[-1] if durations else 0,
        "count": n,
        "p50": pct(0.5),
        "p90": pct(0.9),
    }


def parse_model_efficiency(
    ccusage_daily_raw: Dict[str, Any],
    jsonl_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Model efficiency = tokens / task, cost / task, cache share.

    `cacheShare` is the fraction of prompt tokens that were served from
    cache: `cache_read / (cache_read + cache_creation + plain input)` —
    unlike a naive read/(read+creation) ratio it cannot be inflated by a
    call that was mostly fresh input.
    """
    tokens = ccusage_daily_raw.get("totals") or {}
    cache_read = int(tokens.get("cacheReadTokens", 0) or 0)
    cache_creation = int(tokens.get("cacheCreationTokens", 0) or 0)
    inp = int(tokens.get("inputTokens", 0) or 0)
    out = int(tokens.get("outputTokens", 0) or 0)
    total = int(tokens.get("totalTokens", 0) or 0)
    cost = float(tokens.get("totalCost", 0.0) or 0.0)
    total_tasks = jsonl_summary.get("totalTasks", 0) or 1

    prompt_total = cache_read + cache_creation + inp
    cache_share = (cache_read / prompt_total) if prompt_total else 0.0
    return {
        "tokensPerTask": int(total / total_tasks),
        "costPerTask": round(cost / total_tasks, 4),
        "outputRatio": round(out / max(1, total), 4),
        "cacheShare": round(cache_share, 4),
        "cacheReadTokens": cache_read,
        "cacheCreationTokens": cache_creation,
        "inputTokens": inp,
        "totalTokens": total,
        "totalCost": round(cost, 4),
    }


def build(scans: List[FileScan],
          ccusage_daily_raw: Optional[Dict[str, Any]] = None,
          jsonl_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Top-level aggregator for the advanced analytics, from file scans."""
    efficiency = (
        parse_model_efficiency(ccusage_daily_raw or {}, jsonl_summary or {})
        if ccusage_daily_raw is not None and jsonl_summary is not None
        else None
    )
    return {
        "toolUsage": build_tool_usage(scans),
        "workflowTimeline": build_workflow_timeline(scans),
        "promptCategories": build_prompt_categories(scans),
        "taskDurations": build_task_durations(scans),
        "modelEfficiency": efficiency,
    }


def parse_all(root: Optional[Path] = None,
              ccusage_daily_raw: Optional[Dict[str, Any]] = None,
              jsonl_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compat entrypoint: scan `root`, then build."""
    return build(
        scan_all(root),
        ccusage_daily_raw=ccusage_daily_raw,
        jsonl_summary=jsonl_summary,
    )


if __name__ == "__main__":
    res = parse_all()
    print("Tools:", res["toolUsage"]["tools"][:8])
    print("Tool total:", res["toolUsage"]["total"])
    print("Prompt categories:", res["promptCategories"]["categories"][:4])
    print("Sessions in timeline:", res["workflowTimeline"]["count"])
