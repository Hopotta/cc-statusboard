"""
jsonl_parser.py
===============

Parses Claude Code session JSONL files under `~/.claude/projects/`.

Every file is read exactly ONCE per rebuild (`scan_all`); the resulting
`FileScan` objects feed the task/time rollup (`summarize`), the project
rollup (`project_rollup`) and the advanced analytics in `advanced.py`.

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
    A "task" is a real user message: type=user, no toolUseResult, not
    system-injected (no isMeta, no slash-command expansion, no interrupt
    placeholder).  Anything else is not a task.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
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
        # Skip per-project `memory/` directories (notes, not session logs)
        # and zero-byte files.
        if "memory" in path.parts:
            continue
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


def extract_text(content: Any) -> str:
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


def is_real_user_task(entry: Dict[str, Any]) -> bool:
    """
    Spec: a task is a real user prompt.  Filters out tool responses
    (`toolUseResult` present) and system-injected user-shaped entries:
    `isMeta` caveats, slash-command expansions (`<command-…>` /
    `<local-command-…>`) and interrupt placeholders.
    """
    if entry.get("type") != "user":
        return False
    if "toolUseResult" in entry:
        return False
    if entry.get("isMeta"):
        return False
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        stripped = content.lstrip()
        if stripped.startswith(("<command-", "<local-command-", "[Request interrupted")):
            return False
    return True


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


@dataclass
class FileScan:
    """Everything the dashboard needs from one JSONL file, from a single read."""
    path: Path
    is_subagent: bool
    mtime: float = 0.0
    cwd: Optional[str] = None                      # first raw cwd in the file
    tokens: int = 0                                # deduped per message.id
    model_usage: Dict[str, Dict[str, int]] = field(default_factory=dict)
    task_isos: List[str] = field(default_factory=list)      # aligned with task_dts
    task_dts: List[datetime] = field(default_factory=list)
    tool_counts: Counter = field(default_factory=Counter)
    user_texts: List[str] = field(default_factory=list)     # main files only
    timeline_events: Optional[List[Dict[str, Any]]] = None  # recent sessions only
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None


def scan_all(root: Optional[Path] = None,
             timeline_sessions: int = 10) -> List[FileScan]:
    """Single pass over all JSONL files under `root` (default ~/.claude/projects)."""
    files = list(iter_jsonl_files(root))
    mtimes: Dict[Path, float] = {}
    for p in files:
        try:
            mtimes[p] = p.stat().st_mtime
        except OSError:
            mtimes[p] = 0.0
    # Only the most recent main sessions get timeline events (#14: never
    # subagent sidechains).
    main_files = [p for p in files if not is_subagent_file(p)]
    timeline_set = set(
        sorted(main_files, key=lambda p: mtimes[p], reverse=True)[:timeline_sessions]
    )
    scans: List[FileScan] = []
    for p in files:
        scans.append(
            _scan_file(p, mtimes[p], want_timeline=p in timeline_set)
        )
    return scans


def _scan_file(path: Path, mtime: float, want_timeline: bool) -> FileScan:
    entries = _safe_load(path)
    scan = FileScan(path=path, is_subagent=is_subagent_file(path), mtime=mtime)
    seen_ids: set = set()
    events: Optional[List[Dict[str, Any]]] = [] if want_timeline else None

    for e in entries:
        ts = e.get("timestamp")
        if isinstance(ts, str):
            if scan.first_ts is None:
                scan.first_ts = ts
            scan.last_ts = ts
        if e.get("cwd") and not scan.cwd:
            scan.cwd = e["cwd"]

        etype = e.get("type")
        if etype == "user":
            # Timeline keeps the raw flow (minus tool-result echoes); task
            # metrics use the stricter is_real_user_task filter.
            if events is not None and ts and "toolUseResult" not in e:
                text = extract_text((e.get("message") or {}).get("content"))
                label = text[:80].replace("\n", " ").strip() or "(empty)"
                events.append({"t": ts, "kind": "user", "label": label})
            if not is_real_user_task(e):
                continue
            dt = _parse_ts(ts)
            if dt is not None:
                scan.task_isos.append(ts)
                scan.task_dts.append(dt)
            if not scan.is_subagent:
                text = extract_text((e.get("message") or {}).get("content"))
                if text.strip():
                    scan.user_texts.append(text)

        elif etype == "assistant":
            msg = e.get("message") or {}
            content = msg.get("content")
            if events is not None and ts:
                if isinstance(content, list):
                    tool_names = [b.get("name") for b in content
                                  if isinstance(b, dict) and b.get("type") == "tool_use"]
                    if tool_names:
                        events.append({"t": ts, "kind": "tool",
                                       "label": ", ".join(tool_names)})
                    else:
                        events.append({"t": ts, "kind": "assistant", "label": "reply"})
                else:
                    events.append({"t": ts, "kind": "assistant", "label": "reply"})
            if isinstance(content, list):
                # Claude Code routinely issues parallel tool calls in a single
                # assistant message; each `tool_use` block counts.
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        scan.tool_counts[block.get("name") or "unknown"] += 1
            u = msg.get("usage")
            if not u:
                continue
            # Content blocks of one API response share a message.id and each
            # carries the full usage; count each response exactly once.
            mid = msg.get("id")
            if mid:
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
            inp = int(u.get("input_tokens", 0) or 0)
            out = int(u.get("output_tokens", 0) or 0)
            cc = int(u.get("cache_creation_input_tokens", 0) or 0)
            cr = int(u.get("cache_read_input_tokens", 0) or 0)
            scan.tokens += inp + out + cc + cr
            bucket = scan.model_usage.setdefault(msg.get("model") or "unknown", {
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheCreationTokens": 0,
                "cacheReadTokens": 0,
            })
            bucket["inputTokens"] += inp
            bucket["outputTokens"] += out
            bucket["cacheCreationTokens"] += cc
            bucket["cacheReadTokens"] += cr

    if events is not None:
        scan.timeline_events = events
    return scan


def compute_active_time(timestamps: List[str]) -> int:
    """
    Per spec:
        For each task, duration = next_user_task_timestamp - this_task_timestamp,
        capped at MAX_TASK_DURATION_SECONDS (2h).
    Returns total active seconds.
    """
    if not timestamps:
        return 0

    parsed: List[datetime] = [d for d in (_parse_ts(ts) for ts in timestamps)
                              if d is not None]

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


def project_groups(scans: List[FileScan]) -> List[Tuple[str, str, List[FileScan]]]:
    """
    Group scans into projects by the cwd each session was started in.

    Returns [(cwd_key, project_label, scans)].  Subagent sidechains are
    attached to the project of the session folder they live under, never to
    their worktree cwd.
    """
    by_cwd: Dict[str, List[FileScan]] = {}
    folder_key: Dict[Path, str] = {}  # project slug dir -> cwd key
    key_cwd: Dict[str, Optional[str]] = {}  # cwd key -> first raw cwd

    for s in scans:
        if s.is_subagent:
            continue
        raw = s.cwd or f"<folder:{s.path.parent.name}>"
        key = raw.replace("\\", "/").rstrip("/").lower() or "<unknown>"
        by_cwd.setdefault(key, []).append(s)
        folder_key.setdefault(s.path.parent, key)
        if key not in key_cwd or key_cwd[key] is None:
            key_cwd[key] = s.cwd

    for s in scans:
        if not s.is_subagent:
            continue
        key = folder_key.get(s.path.parent.parent.parent)
        if key:
            by_cwd.setdefault(key, []).append(s)

    out: List[Tuple[str, str, List[FileScan]]] = []
    for key, group in by_cwd.items():
        first_cwd = key_cwd.get(key)
        out.append((key, project_label_from_cwd(first_cwd or key), group))
    out.sort(key=lambda g: g[1])
    return out


def project_rollup(scans: List[FileScan]) -> List[Dict[str, Any]]:
    """Per-project rollup derived from file scans (same shape as before)."""
    rollup: List[Dict[str, Any]] = []
    for key, label, group in project_groups(scans):
        tasks_total = 0
        active_total = 0
        tokens_total = 0
        model_usage: Dict[str, Dict[str, int]] = {}
        first_cwd: Optional[str] = None
        for s in group:
            if first_cwd is None and s.cwd:
                first_cwd = s.cwd
            tokens_total += s.tokens
            for model, bucket in s.model_usage.items():
                acc = model_usage.setdefault(model, {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cacheCreationTokens": 0,
                    "cacheReadTokens": 0,
                })
                for field_name, value in bucket.items():
                    acc[field_name] += value
            if not s.is_subagent:
                tasks_total += len(s.task_isos)
                active_total += compute_active_time(s.task_isos)
        rollup.append({
            "project": label,
            "projectPath": first_cwd,
            "files": len(group),
            "tasks": tasks_total,
            "activeSeconds": active_total,
            "tokens": tokens_total,
            "modelUsage": model_usage,
        })
    rollup.sort(key=lambda x: x["tasks"], reverse=True)
    return rollup


def session_rollup(scans: List[FileScan]) -> List[Dict[str, Any]]:
    """
    Per-session rollup (P1-3).  A session is one main JSONL file; subagent
    sidechain files fold into the session whose folder they live under.
    """
    groups: Dict[str, List[FileScan]] = {}
    order: List[str] = []
    for s in scans:
        uuid = s.path.parent.parent.name if s.is_subagent else s.path.stem
        if uuid not in groups:
            groups[uuid] = []
            order.append(uuid)
        groups[uuid].append(s)

    sessions: List[Dict[str, Any]] = []
    for uuid in order:
        group = groups[uuid]
        main = [s for s in group if not s.is_subagent]
        anchor = main[0] if main else group[0]
        model_usage: Dict[str, Dict[str, int]] = {}
        tokens_total = 0
        for s in group:
            tokens_total += s.tokens
            for model, bucket in s.model_usage.items():
                acc = model_usage.setdefault(model, {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cacheCreationTokens": 0,
                    "cacheReadTokens": 0,
                })
                for field_name, value in bucket.items():
                    acc[field_name] += value
        tasks_total = sum(len(s.task_isos) for s in main)
        active_total = sum(compute_active_time(s.task_isos) for s in main)
        sessions.append({
            "sessionId": uuid,
            "project": project_label_from_cwd(anchor.cwd),
            "projectPath": anchor.cwd,
            "files": len(group),
            "tasks": tasks_total,
            "activeSeconds": active_total,
            "tokens": tokens_total,
            "modelUsage": model_usage,
            "firstTs": anchor.first_ts,
            "lastTs": anchor.last_ts,
        })
    sessions.sort(key=lambda x: x["tokens"], reverse=True)
    return sessions


def summarize(scans: List[FileScan]) -> Dict[str, Any]:
    """Aggregate file scans into the jsonl summary consumed by the aggregator."""
    main = [s for s in scans if not s.is_subagent]
    total_tasks = sum(len(s.task_isos) for s in main)
    total_active = sum(compute_active_time(s.task_isos) for s in main)

    daily_tasks: Dict[str, int] = {}
    daily_active: Dict[str, int] = {}
    hourly_tasks: Dict[int, int] = {}

    for s in main:
        parsed = list(zip(s.task_isos, s.task_dts))
        for i, (iso_t, dt) in enumerate(parsed):
            day = dt.date().isoformat()
            daily_tasks[day] = daily_tasks.get(day, 0) + 1
            # Hour-of-day buckets use the user's LOCAL hour, not UTC.
            local_hour = dt.astimezone().hour
            hourly_tasks[local_hour] = hourly_tasks.get(local_hour, 0) + 1
            # Active seconds for this task on this day.
            if i + 1 < len(parsed):
                delta = int((parsed[i + 1][1] - dt).total_seconds())
                if delta > MAX_TASK_DURATION_SECONDS:
                    delta = MAX_TASK_DURATION_SECONDS
                if delta < 0:
                    delta = 0
                daily_active[day] = daily_active.get(day, 0) + delta

    return {
        "totalTasks": total_tasks,
        "totalActiveSeconds": total_active,
        "projects": project_rollup(scans),
        "sessions": session_rollup(scans),
        "filesScanned": len(scans),
        "dailyTasks": [{"date": d, "tasks": c} for d, c in sorted(daily_tasks.items())],
        "dailyActive": [{"date": d, "activeSeconds": s} for d, s in sorted(daily_active.items())],
        "hourlyTasks": [hourly_tasks.get(h, 0) for h in range(24)],
    }


def project_breakdown(files: List[Path]) -> List[Dict[str, Any]]:
    """Roll up the given files into projects (kept for direct callers/tests)."""
    return project_rollup(scan_files(files))


def parse_all(root: Optional[Path] = None) -> Dict[str, Any]:
    """Top-level: scan all JSONL and return aggregated task/time/project stats."""
    return summarize(scan_all(root))


def scan_files(files: List[Path]) -> List[FileScan]:
    """Scan an explicit list of files (no timeline events)."""
    scans: List[FileScan] = []
    for p in files:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        scans.append(_scan_file(p, mtime, want_timeline=False))
    return scans


if __name__ == "__main__":
    res = parse_all()
    print("files scanned:", res["filesScanned"])
    print("total tasks:", res["totalTasks"])
    print("total active seconds:", res["totalActiveSeconds"])
    print("projects:", res["projects"][:5])
