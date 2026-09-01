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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .jsonl_parser import (
    FileScan,
    MAX_TASK_DURATION_SECONDS,
    project_groups,
    scan_all,
)

if TYPE_CHECKING:
    from .contracts import JsonlSummary, UsageTotals

# Heuristic prompt categories — best-effort, regex based, first match wins.
# Order matters: debug guards its colloquial failure words before ui/run can
# steal them; report precedes refactor so "更新readme" isn't a "refactor";
# anchored acks (continue) can't steal real instructions.
#
# Bump PROMPT_CLASSIFIER_VERSION whenever the regexes or ordering change:
# category shares are user-visible trends, and a silent classifier edit would
# read as a behavior change.  The version ships in the artifact next to the
# counts so consumers can tell the two apart.
PROMPT_CLASSIFIER_VERSION = 1

PROMPT_CATEGORIES: List[Tuple[str, str, List[str]]] = [
    ("debug", "Debug / fix", [
        r"\bbug\b", r"\bfix\b", r"\berror\b", r"\bcrash\b", r"\bbroken\b",
        r"why is .* not", r"doesn't work", r"fails to", r"报错", r"崩溃",
        r"修复", r"问题", r"失败", r"排查", r"怎么回事", r"什么情况",
        r"闪退", r"卡在那", r"没反应", r"崩了", r"异常", r"用不了",
        r"跑不通", r"怎么解决", r"解决了", r"修吧", r"修一下", r"修好",
        r"坏了", r"不对劲",
    ]),
    ("continue", "Continue / ack", [
        r"^继续\b", r"^接着\b", r"^(好了?|好的?|可以了?|确认|弄好了?)\b",
        r"^(已填入|已写入|已更新|算了|说中文|没毛病|效果很好|连接好了|开完会了)\b",
        r"^(ok|hello)\b", r"^方案\s?[0-9a-cＡ-Ｃ]{1,2}\b",
    ]),
    ("git", "Git operations", [
        r"commit", r"push", r"merge", r"revert", r"回退",
        r"回滚", r"分支", r"分枝", r"gitee", r"github", r"git ?init",
        r"gitignore", r"worktree", r"合并.{0,8}(main|worktree)", r"合并吧",
    ]),
    ("run", "Run / execute", [
        r"^(帮我)?(启动|重启|运行|跑|开一下|开启|执行)", r"跑一下",
        r"怎么(启动|运行|跑)", r"帮我导出", r"转换成", r"转成", r"部署",
    ]),
    ("ui", "UI / style tweak", [
        r"前端|界面|样式|字体|字号|颜色|布局|居中|对齐|边框|滚动条|按钮",
        r"输入框|header|footer|折叠|展开|悬浮|气泡|遮挡|渐变|透明|模糊",
        r"宽度|高度|加宽|收窄|太窄|太宽|太矮|增高|间隔|往左|往右|往下|往上",
        r"美观|难看|好看|不协调",
    ]),
    ("maintain", "Cleanup / system", [
        r"缓存", r"杀掉", r"杀进程", r"残留进程", r"清理", r"C盘", r"磁盘",
        r"内存占用", r"内存不够", r"占用情况", r"驱动",
    ]),
    ("report", "Docs / reports", [
        r"readme", r"changelog", r"\.md\b", r"md文件", r"更新到", r"写成",
        r"总结成", r"记录到", r"分析报告", r"周报", r"讲稿", r"组会", r"导师",
        r"汇报",
    ]),
    ("refactor", "Refactor", [
        r"\brefactor\b", r"\brestructur", r"\breorganiz", r"\bcleanup\b",
        r"重构", r"整理", r"清理", r"优化", r"改成", r"改为", r"改一下",
        r"改回", r"调整", r"删掉", r"删除", r"去掉", r"移除", r"清掉",
        r"更新",
    ]),
    ("feature", "New feature", [
        r"\badd\b.*\bfeature\b", r"\bimplement\b", r"\bcreate\b", r"\bbuild\b",
        r"加.*功能", r"实现", r"创建", r"添加", r"写一个", r"写一篇",
        r"帮我写", r"做一个", r"做个", r"加上", r"加一个", r"加进",
        r"生成", r"接入", r"引入",
    ]),
    ("explain", "Explain / docs", [
        r"\bexplain\b", r"\bwhat does\b", r"\bhow does\b", r"\bdocs?\b",
        r"说明", r"解释", r"文档", r"介绍", r"总结", r"梳理", r"捋一",
        r"概括", r"什么意思", r"是啥", r"有什么区别", r"怎么用",
        r"如何使用", r"教我", r"代表什么", r"含义", r"说人话", r"没看懂",
    ]),
    ("plan", "Plan / design", [
        r"\bplan\b", r"\bdesign\b", r"\barchitect", r"\bschema\b",
        r"规划", r"设计", r"架构", r"方案", r"计划",
    ]),
    ("review", "Review / test", [
        r"\breview\b", r"\btest\b", r"\bcheck\b", r"\bverify\b",
        r"审查", r"测试", r"检查", r"验证",
        r"看看.{0,24}(?:是否|正常|结果|怎么样)", r"有没有(?:问题|错误|差异)",
    ]),
    ("config", "Config / setup", [
        r"\bconfigur", r"\bset up\b", r"\bsetup\b", r"\binstall\b",
        r"配置", r"安装", r"端口", r"代理", r"\bproxy\b", r"初始化",
        r"环境变量", r"设置为", r"设置成",
    ]),
    ("explore", "Explore", [
        r"\bfind\b", r"\bsearch\b", r"\bwhere\b", r"\bwhich\b",
        r"找", r"搜索", r"在哪", r"哪些", r"多少", r"几个", r"有没有",
        r"帮我看看", r"看看",
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
        events = list(s.timeline_events or [])
        # Trim to max_events_per_session, keeping first and last.
        if len(events) > max_events_per_session:
            head = events[:max_events_per_session // 2]
            tail = events[-(max_events_per_session // 2):]
            events = head + tail
        out.append({
            "sessionId": s.path.stem,
            # No local file path here: sessionId already identifies the
            # session, and the artifact stays free of the machine's
            # directory layout.
            "events": events,
            "firstEvent": events[0]["t"],
            "lastEvent": events[-1]["t"],
        })
    return {"sessions": out, "count": len(out)}


def build_prompt_categories(scans: List[FileScan]) -> Dict[str, Any]:
    """Bucket user prompts by heuristic category (same task set as tasks).

    Only aggregate counts enter the payload — no prompt text.
    """
    counts: Counter[str] = Counter()
    label_map = {slug: label for slug, label, _ in PROMPT_CATEGORIES}

    for s in scans:
        if s.is_subagent:
            continue
        for text in s.user_texts:
            counts[_classify_prompt(text)] += 1

    total = sum(counts.values()) or 1
    return {
        "classifierVersion": f"v{PROMPT_CLASSIFIER_VERSION}",
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
    totals: "UsageTotals",
    jsonl_summary: "JsonlSummary",
) -> Dict[str, Any]:
    """
    Model efficiency = tokens / task, cost / task, cache share.

    `totals` is the flat native totals dict (native_usage.py) — the same
    numbers the summary panel shows.  `cacheShare` is the fraction of
    prompt tokens that were served from cache:
    `cache_read / (cache_read + cache_creation + plain input)` — unlike a
    naive read/(read+creation) ratio it cannot be inflated by a call that
    was mostly fresh input.
    """
    cache_read = int(totals.get("cacheReadTokens", 0) or 0)
    cache_creation = int(totals.get("cacheCreationTokens", 0) or 0)
    inp = int(totals.get("inputTokens", 0) or 0)
    out = int(totals.get("outputTokens", 0) or 0)
    total = int(totals.get("totalTokens", 0) or 0)
    cost = float(totals.get("totalCost", 0.0) or 0.0)
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
          totals: Optional["UsageTotals"] = None,
          jsonl_summary: Optional["JsonlSummary"] = None) -> Dict[str, Any]:
    """Top-level aggregator for the advanced analytics, from file scans.

    `totals` is the flat native usage totals dict; without it (or the
    summary) modelEfficiency is omitted.
    """
    efficiency = (
        parse_model_efficiency(totals or {}, jsonl_summary or {})
        if totals is not None and jsonl_summary is not None
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
              totals: Optional["UsageTotals"] = None,
              jsonl_summary: Optional["JsonlSummary"] = None) -> Dict[str, Any]:
    """Compat entrypoint: scan `root`, then build."""
    return build(
        scan_all(root),
        totals=totals,
        jsonl_summary=jsonl_summary,
    )


if __name__ == "__main__":
    res = parse_all()
    print("Tools:", res["toolUsage"]["tools"][:8])
    print("Tool total:", res["toolUsage"]["total"])
    print("Prompt categories:", res["promptCategories"]["categories"][:4])
    print("Sessions in timeline:", res["workflowTimeline"]["count"])
