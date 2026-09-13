"""Read local Codex rollout logs into the collector's shared scan shape.

Codex stores sessions beneath ``~/.codex/sessions`` (and moves completed
ones to ``~/.codex/archived_sessions``).  The log format is event-oriented:
``token_usage_record`` carries one response's usage, while ``response_item``
contains the user messages and tool calls.  Keeping this adapter small lets
the existing native rollups and analytics consume Codex without special
cases.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .jsonl_parser import FileScan, is_real_user_task

CODEX_HOME = Path(os.path.expanduser("~/.codex"))
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
CODEX_ARCHIVED_SESSIONS_DIR = CODEX_HOME / "archived_sessions"


def iter_jsonl_files() -> Iterable[Path]:
    """Yield current and archived Codex rollouts once each."""
    seen: set[Path] = set()
    for root in (CODEX_SESSIONS_DIR, CODEX_ARCHIVED_SESSIONS_DIR):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.jsonl")):
            try:
                resolved = path.resolve()
                if path.stat().st_size == 0 or resolved in seen:
                    continue
            except OSError:
                continue
            seen.add(resolved)
            yield path


def _safe_load(path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
    except OSError:
        return []
    return entries


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _message_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "input_text"
    )


def _empty_usage() -> Dict[str, int]:
    return {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheCreationTokens": 0,
        "cacheReadTokens": 0,
    }


def _add_usage(scan: FileScan, model: str, timestamp: Any,
               usage: Dict[str, Any]) -> None:
    """Map Codex's usage accounting to the dashboard's four token buckets.

    ``cached_input_tokens`` is a subset of Codex's ``input_tokens``.  Split
    it out so the four displayed buckets still sum exactly to ``total_tokens``
    rather than double-counting cache reads.
    """
    input_tokens = _as_int(usage.get("input_tokens"))
    cached_tokens = _as_int(usage.get("cached_input_tokens"))
    cache_write = _as_int(usage.get("cache_write_input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    plain_input = max(0, input_tokens - cached_tokens - cache_write)
    values = {
        "inputTokens": plain_input,
        "outputTokens": output_tokens,
        "cacheCreationTokens": cache_write,
        "cacheReadTokens": cached_tokens,
    }
    total = sum(values.values())
    if not total:
        return

    scan.tokens += total
    bucket = scan.model_usage.setdefault(model, _empty_usage())
    for key, value in values.items():
        bucket[key] += value

    if isinstance(timestamp, str) and len(timestamp) >= 10:
        day_bucket = scan.usage_daily.setdefault(timestamp[:10], {})
        day_model = day_bucket.setdefault(model, _empty_usage())
        for key, value in values.items():
            day_model[key] += value


def _usage_delta(current: Dict[str, Any], previous: Optional[Dict[str, int]]) -> Dict[str, int]:
    """Return a safe delta from Codex's legacy cumulative token counter."""
    keys = ("input_tokens", "cached_input_tokens",
            "cache_write_input_tokens", "output_tokens")
    values = {key: _as_int(current.get(key)) for key in keys}
    if previous is None or any(values[key] < previous.get(key, 0) for key in keys):
        # A compaction/restart can reset the cumulative counter.  Its
        # accompanying ``last_token_usage`` is handled by the caller.
        return values
    return {key: values[key] - previous.get(key, 0) for key in keys}


def _scan_file(path: Path, mtime: float, want_timeline: bool) -> FileScan:
    entries = _safe_load(path)
    scan = FileScan(path=path, is_subagent=False, mtime=mtime)
    events: Optional[List[Dict[str, Any]]] = [] if want_timeline else None
    model_by_turn: Dict[str, str] = {}
    fallback_model = "Codex"

    # Context rows carry the selected model, while usage rows point back to a
    # turn.  Collect this mapping before consuming the usage events because
    # the two row types are allowed to arrive in either order.
    for entry in entries:
        if entry.get("type") == "session_meta":
            payload = entry.get("payload") or {}
            if isinstance(payload, dict):
                model = payload.get("model")
                if isinstance(model, str) and model:
                    fallback_model = model
        if entry.get("type") != "turn_context":
            continue
        payload = entry.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            continue
        for key in ("turn_id", "root_turn_id"):
            turn_id = payload.get(key)
            if isinstance(turn_id, str):
                model_by_turn[turn_id] = model

    seen_responses: set[str] = set()
    # Codex pre-0.6 rollouts do not have ``token_usage_record``.  Their
    # `event_msg/token_count` entries expose a cumulative counter instead.
    # Never consume both shapes from one file: some migrations retain legacy
    # telemetry alongside the modern canonical records.
    has_canonical_usage = any(entry.get("type") == "token_usage_record" for entry in entries)
    prior_legacy_total: Optional[Dict[str, int]] = None
    for entry in entries:
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str):
            if scan.first_ts is None:
                scan.first_ts = timestamp
            scan.last_ts = timestamp
        payload = entry.get("payload") or {}
        if not isinstance(payload, dict):
            continue

        if entry.get("type") == "session_meta" and not scan.cwd:
            cwd = payload.get("cwd")
            if isinstance(cwd, str):
                scan.cwd = cwd
        if entry.get("type") == "session_meta" and not scan.session_id:
            session_id = payload.get("id") or payload.get("session_id")
            if isinstance(session_id, str) and session_id:
                scan.session_id = session_id
        elif entry.get("type") == "turn_context" and not scan.cwd:
            cwd = payload.get("cwd")
            if isinstance(cwd, str):
                scan.cwd = cwd

        if entry.get("type") == "token_usage_record":
            response_id = payload.get("response_id")
            if isinstance(response_id, str):
                if response_id in seen_responses:
                    continue
                seen_responses.add(response_id)
            model = (
                model_by_turn.get(str(payload.get("turn_id")))
                or model_by_turn.get(str(payload.get("root_turn_id")))
                or "Codex"
            )
            usage = payload.get("usage")
            if isinstance(usage, dict):
                _add_usage(scan, model, timestamp, usage)
            continue

        if entry.get("type") == "event_msg" and not has_canonical_usage:
            if payload.get("type") != "token_count":
                continue
            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            cumulative = info.get("total_token_usage")
            latest = info.get("last_token_usage")
            legacy_usage: Optional[Dict[str, int]] = None
            if isinstance(cumulative, dict):
                delta = _usage_delta(cumulative, prior_legacy_total)
                # A reset is not a billable delta; prefer the explicit last
                # response counter in that rare case.
                if prior_legacy_total is not None and any(
                    _as_int(cumulative.get(key)) < prior_legacy_total.get(key, 0)
                    for key in delta
                ) and isinstance(latest, dict):
                    legacy_usage = {key: _as_int(latest.get(key)) for key in delta}
                else:
                    legacy_usage = delta
                prior_legacy_total = {
                    key: _as_int(cumulative.get(key)) for key in delta
                }
            elif isinstance(latest, dict):
                legacy_usage = {key: _as_int(latest.get(key)) for key in (
                    "input_tokens", "cached_input_tokens",
                    "cache_write_input_tokens", "output_tokens",
                )}
            if legacy_usage:
                _add_usage(scan, fallback_model, timestamp, legacy_usage)
            continue

        if entry.get("type") != "response_item":
            continue
        item_type = payload.get("type")
        if item_type == "message" and payload.get("role") == "user":
            text = _message_text(payload.get("content"))
            # A lightweight Claude-shaped view lets the shared task filter
            # reject empty/synthetic rows without retaining prompt content.
            task_entry = {
                "type": "user",
                "timestamp": timestamp,
                "message": {"content": text},
            }
            if is_real_user_task(task_entry):
                dt = _parse_ts(timestamp)
                if isinstance(timestamp, str) and dt is not None:
                    scan.task_isos.append(timestamp)
                    scan.task_dts.append(dt)
                if text.strip():
                    scan.user_texts.append(text)
                if events is not None and isinstance(timestamp, str):
                    events.append({"t": timestamp, "kind": "user", "label": "user"})
        elif item_type == "message" and payload.get("role") == "assistant":
            if events is not None and isinstance(timestamp, str):
                events.append({"t": timestamp, "kind": "assistant", "label": "reply"})
        elif item_type in {"function_call", "custom_tool_call", "tool_search_call"}:
            name = str(payload.get("name") or item_type)
            scan.tool_counts[name] += 1
            if events is not None and isinstance(timestamp, str):
                events.append({"t": timestamp, "kind": "tool", "label": name})

    if not scan.tokens:
        # A handful of rollout files are imported transcript/metadata stubs:
        # they contain user-shaped history but no provider response or usage
        # counter at all.  They are not Codex usage sessions, so allowing
        # their messages into task/hour/project rollups creates impossible
        # rows (tasks/time but zero tokens and spend).
        scan.task_isos.clear()
        scan.task_dts.clear()
        scan.user_texts.clear()
        scan.tool_counts.clear()
        events = [] if events is not None else None
    if events is not None:
        scan.timeline_events = events
    return scan


def scan_all(timeline_sessions: int = 10) -> List[FileScan]:
    """Scan Codex rollouts once, adding timeline detail only for recents."""
    files = list(iter_jsonl_files())
    mtimes: Dict[Path, float] = {}
    for path in files:
        try:
            mtimes[path] = path.stat().st_mtime
        except OSError:
            mtimes[path] = 0.0
    timeline_set = set(sorted(files, key=lambda path: mtimes[path], reverse=True)[:timeline_sessions])
    return [_scan_file(path, mtimes[path], path in timeline_set) for path in files]


def scan_files(files: List[Path]) -> List[FileScan]:
    """Test-friendly explicit-file variant."""
    scans: List[FileScan] = []
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        scans.append(_scan_file(path, mtime, want_timeline=False))
    return scans
