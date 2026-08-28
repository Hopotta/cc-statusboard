"""
advanced.py
===========

Higher-order analytics derived from JSONL session logs.

Provides:
    - tool usage stats:      how often each tool was invoked
    - agent workflow timeline: user→assistant→tool sequence per session
    - prompt categories:      simple heuristic buckets for user prompts
    - model efficiency:       tokens / task, cost / task, cache hit rate
    - per-project comparison: tokens, tasks, time, tools

The heuristics here are intentionally simple — they're meant to be
    suggestive, not authoritative.  See PROMPT_CATEGORIES for the keyword map.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .jsonl_parser import (
    CLAUDE_PROJECTS_DIR,
    _safe_load,
    is_real_user_task,
    iter_jsonl_files,
    project_label_from_cwd,
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


def _extract_text(content: Any) -> str:
    """Assistant/user message `content` can be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        cmd = inp.get("command") or inp.get("file_path") or ""
                        if cmd:
                            chunks.append(f"[{block.get('name', '?')}: {cmd}]")
                elif block.get("type") == "tool_result":
                    chunks.append("[tool result]")
            elif isinstance(block, str):
                chunks.append(block)
        return "\n".join(chunks)
    return ""


def parse_tool_usage(root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Count tool invocations across all sessions.

    Walks assistant messages and pulls `tool_use` blocks.  Each block has a
    `name` (the tool name) and `input` (the arguments).  We don't extract
    argument details — just the names + counts.
    """
    counts: Counter[str] = Counter()
    by_project: Dict[str, Counter[str]] = defaultdict(Counter)

    for fp in iter_jsonl_files(root):
        # Per-file project resolution.
        project_key: Optional[str] = None
        for line in _safe_load(fp):
            if project_key is None and line.get("cwd"):
                project_key = project_label_from_cwd(line["cwd"])
                break

        for line in _safe_load(fp):
            if line.get("type") != "assistant":
                continue
            msg = line.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "unknown"
                    counts[name] += 1
                    if project_key:
                        by_project[project_key][name] += 1
                    # No break: Claude Code routinely issues parallel tool calls
                    # in a single assistant message; each `tool_use` block counts.

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


def parse_workflow_timeline(root: Optional[Path] = None,
                             max_sessions: int = 10,
                             max_events_per_session: int = 80) -> Dict[str, Any]:
    """
    Build a coarse timeline of recent sessions.

    For each recent session we return an array of events:
        { t: ISO timestamp, kind: 'user'|'assistant'|'tool', label: str }

    Capped at `max_sessions` × `max_events_per_session` to keep payload size sane.
    The strip view (front-end) and the detail view share the same events; if you
    expand a session in the UI it shows the same events, no second fetch.
    """
    sessions: List[Tuple[float, Path]] = []
    for fp in iter_jsonl_files(root):
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            continue
        sessions.append((mtime, fp))
    sessions.sort(reverse=True)

    out: List[Dict[str, Any]] = []
    for _, fp in sessions[:max_sessions]:
        events: List[Dict[str, Any]] = []
        for line in _safe_load(fp):
            ts = line.get("timestamp")
            kind = line.get("type")
            if not ts or kind not in ("user", "assistant"):
                continue
            # Skip tool-result echoes (type=user with a toolUseResult): they would
            # duplicate the tool_use event we already capture on the assistant side.
            if kind == "user" and "toolUseResult" in line:
                continue
            if kind == "user":
                text = _extract_text(line.get("message", {}).get("content", ""))
                label = text[:80].replace("\n", " ").strip() or "(empty)"
                events.append({"t": ts, "kind": "user", "label": label})
            elif kind == "assistant":
                content = line.get("message", {}).get("content", [])
                # If there's a tool_use, surface the tool name(s).
                if isinstance(content, list):
                    tool_names = [b.get("name") for b in content
                                  if isinstance(b, dict) and b.get("type") == "tool_use"]
                    if tool_names:
                        events.append({"t": ts, "kind": "tool",
                                       "label": ", ".join(tool_names)})
                        continue
                events.append({"t": ts, "kind": "assistant", "label": "reply"})
        if events:
            # Trim to max_events_per_session, keeping first and last.
            if len(events) > max_events_per_session:
                head = events[:max_events_per_session // 2]
                tail = events[-(max_events_per_session // 2):]
                events = head + tail
            out.append({
                "sessionId": fp.stem,
                "file": str(fp),
                "events": events,
                "firstEvent": events[0]["t"],
                "lastEvent": events[-1]["t"],
            })
    return {"sessions": out, "count": len(out)}


def parse_task_durations(root: Optional[Path] = None) -> List[int]:
    """Return the duration (in seconds) of each real user task across all sessions.

    Each duration is `next_task_ts - this_task_ts`, capped at 2h per the spec.
    Used to surface the actual longest task — not the longest project-average.
    """
    from datetime import datetime
    from .jsonl_parser import MAX_TASK_DURATION_SECONDS, is_real_user_task

    durations: List[int] = []
    for fp in iter_jsonl_files(root):
        entries = _safe_load(fp)
        ts_list: List[datetime] = []
        for e in entries:
            if not is_real_user_task(e):
                continue
            t = e.get("timestamp")
            if not t:
                continue
            try:
                ts_list.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
            except (ValueError, AttributeError):
                continue
        for i in range(len(ts_list) - 1):
            d = (ts_list[i + 1] - ts_list[i]).total_seconds()
            if d < 0:
                d = 0
            if d > MAX_TASK_DURATION_SECONDS:
                d = MAX_TASK_DURATION_SECONDS
            durations.append(int(d))
    return durations


def parse_prompt_categories(root: Optional[Path] = None) -> Dict[str, Any]:
    """Bucket user prompts by heuristic category."""
    counts: Counter[str] = Counter()
    examples: Dict[str, List[str]] = defaultdict(list)
    label_map = {slug: label for slug, label, _ in PROMPT_CATEGORIES}

    for fp in iter_jsonl_files(root):
        for line in _safe_load(fp):
            if not is_real_user_task(line):
                continue
            text = _extract_text(line.get("message", {}).get("content", ""))
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


def parse_model_efficiency(
    ccusage_daily_raw: Dict[str, Any],
    jsonl_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Model efficiency = tokens / task, cost / task, cache hit rate.

    The cache hit rate is `(cacheRead) / (cacheRead + input)`.  In practice the
    real metric is `cache_read / total_prompt_tokens`, but we don't get separate
    prompt totals so this approximation is what ccusage exposes.
    """
    tokens = ccusage_daily_raw.get("totals") or {}
    cache_read = int(tokens.get("cacheReadTokens", 0))
    cache_creation = int(tokens.get("cacheCreationTokens", 0))
    inp = int(tokens.get("inputTokens", 0))
    out = int(tokens.get("outputTokens", 0))
    total = int(tokens.get("totalTokens", 0))
    cost = float(tokens.get("totalCost", 0.0))
    total_tasks = jsonl_summary.get("totalTasks", 0) or 1

    cache_total = cache_read + cache_creation
    cache_share = (cache_read / cache_total) if cache_total else 0.0
    return {
        "tokensPerTask": int(total / total_tasks),
        "costPerTask": round(cost / total_tasks, 4),
        "outputRatio": round(out / max(1, total), 4),
        "cacheHitRate": round(cache_share, 4),
        "cacheReadTokens": cache_read,
        "cacheCreationTokens": cache_creation,
        "totalTokens": total,
        "totalCost": round(cost, 4),
    }


def parse_all(root: Optional[Path] = None,
              ccusage_daily_raw: Optional[Dict[str, Any]] = None,
              jsonl_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Top-level aggregator for Phase 4 analytics."""
    tools = parse_tool_usage(root)
    timeline = parse_workflow_timeline(root)
    prompts = parse_prompt_categories(root)
    durations = parse_task_durations(root)
    efficiency = (
        parse_model_efficiency(ccusage_daily_raw or {}, jsonl_summary or {})
        if ccusage_daily_raw is not None and jsonl_summary is not None
        else None
    )
    return {
        "toolUsage": tools,
        "workflowTimeline": timeline,
        "promptCategories": prompts,
        "taskDurations": {
            "durations": durations,
            "longest": max(durations) if durations else 0,
            "count": len(durations),
        },
        "modelEfficiency": efficiency,
    }


if __name__ == "__main__":
    import sys
    res = parse_all()
    print("Tools:", res["toolUsage"]["tools"][:8])
    print("Tool total:", res["toolUsage"]["total"])
    print("Prompt categories:", res["promptCategories"]["categories"][:4])
    print("Sessions in timeline:", res["workflowTimeline"]["count"])