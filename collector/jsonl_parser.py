"""
jsonl_parser.py
===============

Parses Claude Code session JSONL files under `~/.claude/projects/`.

Schema (per line, only the fields we care about):
    {
        "type": "user" | "assistant" | "system" | "attachment" | ...,
        "timestamp": "ISO-8601 UTC",
        "message": {"role": "user", "content": <str | [blocks]>}
        "toolUseResult": {...}      # present only on tool responses
        "sessionId": "...",
        "cwd": "D:\\path\\to\\project"
    }

Per the spec:
    A "task" is a real user message: type=user AND no toolUseResult.
    Anything else (tool response, system, assistant, attachment) is not a task.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CLAUDE_PROJECTS_DIR = Path(os.path.expanduser("~/.claude/projects"))


# How long can a single "active task" be before we assume the user stepped away?
# Spec: cap each task at 2h to avoid counting idle wall-clock as work time.
MAX_TASK_DURATION_SECONDS = 2 * 60 * 60


def iter_jsonl_files(root: Optional[Path] = None) -> Iterable[Path]:
    """Yield all *.jsonl session files under the projects dir."""
    root = root or CLAUDE_PROJECTS_DIR
    if not root.exists():
        return
    for path in sorted(root.rglob("*.jsonl")):
        # Skip files in `memory/` directory if present (those are per-project memory,
        # not session logs).  Also skip files that are zero bytes.
        try:
            if path.stat().st_size == 0:
                continue
        except OSError:
            continue
        yield path


def _safe_load(path: Path) -> List[Dict[str, Any]]:
    """Read a jsonl file and parse each non-empty line as JSON; skip malformed lines."""
    out: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def is_real_user_task(entry: Dict[str, Any]) -> bool:
    """
    Spec: a task is type=user AND no toolUseResult.
    That filters out tool responses (which are echoed back as type=user too).
    """
    if entry.get("type") != "user":
        return False
    if "toolUseResult" in entry:
        return False
    return True


def task_timestamps(entries: List[Dict[str, Any]]) -> List[str]:
    """Return the timestamps (ISO strings) of all real user tasks in order."""
    return [e["timestamp"] for e in entries if is_real_user_task(e) and e.get("timestamp")]


def compute_active_time(timestamps: List[str]) -> int:
    """
    Per spec:
        For each task, duration = next_user_task_timestamp - this_task_timestamp,
        capped at MAX_TASK_DURATION_SECONDS (2h).
    Returns total active seconds.
    """
    from datetime import datetime

    if not timestamps:
        return 0

    # Parse once, dropping any malformed timestamps.
    parsed: List[datetime] = []
    for ts in timestamps:
        try:
            # 'Z' suffix is UTC; fromisoformat in 3.11+ handles it.
            parsed.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except (ValueError, AttributeError):
            continue

    total = 0
    for i in range(len(parsed) - 1):
        delta = (parsed[i + 1] - parsed[i]).total_seconds()
        # Cap to avoid counting "user left the computer" time.
        if delta < 0:
            delta = 0
        if delta > MAX_TASK_DURATION_SECONDS:
            delta = MAX_TASK_DURATION_SECONDS
        total += int(delta)
    return total


def project_label_from_cwd(cwd: Optional[str]) -> str:
    """
    Derive a short human-friendly project label from the cwd path.

    Examples:
        D:\\Agent-RAG              -> "Agent-RAG"
        D:\\                       -> "D:\\"  (root drive, keep as-is)
        C:\\Users\\me\\proj        -> "proj"
        /home/me/cool-app         -> "cool-app"
    """
    if not cwd:
        return "unknown"
    # Normalize separators.
    p = cwd.replace("\\", "/").rstrip("/")
    if not p:
        return cwd  # bare drive like "D:\\"
    last = p.split("/")[-1]
    # If the last segment is empty or just a drive letter ("D:"), prefer the
    # parent directory's name (e.g. for `D:\\` -> use the folder above).
    if not last or (len(last) <= 2 and last.endswith(":")):
        parts = [x for x in p.split("/") if x]
        if len(parts) >= 2:
            return parts[-1]
        return cwd
    return last or "unknown"


def is_subagent_file(path: Path) -> bool:
    """
    Task-tool subagent logs live under <project>/<session>/subagents/ and
    carry a worktree cwd — they are sidechains, not user sessions.
    """
    return "subagents" in path.parts


def project_breakdown(files: List[Path]) -> List[Dict[str, Any]]:
    """
    Per-project rollup derived from JSONL files.

    Strategy: group sessions by the cwd each session was started in.  Multiple
    sessions with the same cwd are one project entry; sessions whose cwd is
    missing or empty fall back to the folder under ~/.claude/projects/.
    """
    by_cwd: Dict[str, List[Path]] = {}
    cwd_order: Dict[str, str] = {}  # cwd -> canonical (first seen) cwd value
    main_files = [p for p in files if not is_subagent_file(p)]
    subagent_files = [p for p in files if is_subagent_file(p)]

    folder_key: Dict[Path, str] = {}  # project slug dir -> cwd key
    for p in main_files:
        # Inspect just enough lines to discover a cwd.
        entries = _safe_load(p)
        cwd = None
        for e in entries:
            c = e.get("cwd")
            if c:
                cwd = c
                break
        if not cwd:
            # Fall back to the parent folder as a synthetic key.
            cwd = f"<folder:{p.parent.name}>"
        cwd = cwd.replace("\\", "/").rstrip("/").lower() or "<unknown>"
        by_cwd.setdefault(cwd, []).append(p)
        cwd_order.setdefault(cwd, cwd)
        folder_key.setdefault(p.parent, cwd)

    # Subagent logs (<slug>/<session>/subagents/) belong to the project of
    # the session folder they live under, not to their worktree cwd.
    for p in subagent_files:
        key = folder_key.get(p.parent.parent.parent)
        if key:
            by_cwd.setdefault(key, []).append(p)

    rollup: List[Dict[str, Any]] = []
    for key, key_files in by_cwd.items():
        tasks_total = 0
        active_total = 0
        tokens_total = 0
        model_usage: Dict[str, Dict[str, int]] = {}
        first_cwd: Optional[str] = None
        for fp in key_files:
            entries = _safe_load(fp)
            # Content blocks of one API response share a message.id and each
            # carries the full usage; count each response exactly once.
            seen_ids: set = set()
            for e in entries:
                if first_cwd is None and e.get("cwd"):
                    first_cwd = e["cwd"]
                if e.get("type") != "assistant":
                    continue
                msg = e.get("message") or {}
                u = msg.get("usage")
                if not u:
                    continue
                mid = msg.get("id")
                if mid:
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                inp = int(u.get("input_tokens", 0))
                out = int(u.get("output_tokens", 0))
                cc = int(u.get("cache_creation_input_tokens", 0))
                cr = int(u.get("cache_read_input_tokens", 0))
                tokens_total += inp + out + cc + cr
                bucket = model_usage.setdefault(msg.get("model") or "unknown", {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cacheCreationTokens": 0,
                    "cacheReadTokens": 0,
                })
                bucket["inputTokens"] += inp
                bucket["outputTokens"] += out
                bucket["cacheCreationTokens"] += cc
                bucket["cacheReadTokens"] += cr
            ts = [] if is_subagent_file(fp) else task_timestamps(entries)
            tasks_total += len(ts)
            active_total += compute_active_time(ts)
        rollup.append({
            "project": project_label_from_cwd(first_cwd or key),
            "projectPath": first_cwd,
            "files": len(key_files),
            "tasks": tasks_total,
            "activeSeconds": active_total,
            "tokens": tokens_total,
            "modelUsage": model_usage,
        })
    rollup.sort(key=lambda x: x["tasks"], reverse=True)
    return rollup


def parse_all(root: Optional[Path] = None) -> Dict[str, Any]:
    """Top-level: scan all JSONL and return aggregated task/time/project stats."""
    files = list(iter_jsonl_files(root))
    main_files = [f for f in files if not is_subagent_file(f)]
    total_tasks = 0
    total_active_seconds = 0
    daily_tasks: Dict[str, int] = {}
    daily_active: Dict[str, int] = {}
    hourly_tasks: Dict[int, int] = {}

    from datetime import datetime

    for fp in main_files:
        entries = _safe_load(fp)
        ts = task_timestamps(entries)
        total_tasks += len(ts)
        total_active_seconds += compute_active_time(ts)

        # Per-day rollup (use date string of each task's timestamp).
        parsed_ts: List[Tuple[str, datetime]] = []
        for t in ts:
            try:
                parsed_ts.append((t, datetime.fromisoformat(t.replace("Z", "+00:00"))))
            except (ValueError, AttributeError):
                continue
        for i, (iso_t, dt) in enumerate(parsed_ts):
            day = dt.date().isoformat()
            daily_tasks[day] = daily_tasks.get(day, 0) + 1
            # Hour-of-day buckets use the user's LOCAL hour, not UTC.
            local_hour = dt.astimezone().hour
            hourly_tasks[local_hour] = hourly_tasks.get(local_hour, 0) + 1
            # Active seconds for this task on this day.
            if i + 1 < len(parsed_ts):
                next_iso, next_dt = parsed_ts[i + 1]
                delta = int((next_dt - dt).total_seconds())
                if delta > MAX_TASK_DURATION_SECONDS:
                    delta = MAX_TASK_DURATION_SECONDS
                if delta < 0:
                    delta = 0
                daily_active[day] = daily_active.get(day, 0) + delta

    return {
        "totalTasks": total_tasks,
        "totalActiveSeconds": total_active_seconds,
        "projects": project_breakdown(files),
        "filesScanned": len(files),
        "dailyTasks": [{"date": d, "tasks": c} for d, c in sorted(daily_tasks.items())],
        "dailyActive": [{"date": d, "activeSeconds": s} for d, s in sorted(daily_active.items())],
        "hourlyTasks": [hourly_tasks.get(h, 0) for h in range(24)],
    }


if __name__ == "__main__":
    res = parse_all()
    print("files scanned:", res["filesScanned"])
    print("total tasks:", res["totalTasks"])
    print("total active seconds:", res["totalActiveSeconds"])
    print("projects:", res["projects"][:5])