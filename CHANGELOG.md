# Changelog

All notable changes to cc-statusboard will be documented in this file.

## [0.3.0] - 2026-08-30

### Added

- Per-session analytics: every session gets a tokens/cost/tasks rollup (subagent sidechain logs fold into their parent session) with a sortable Sessions table answering "which session was the most expensive?"
- Token throughput: a stacked mode showing the daily input / output / cache-read / cache-creation composition, plus outlier markers on days beyond mean + 2σ
- "Today" metric tile: tokens used today with a ±% vs-yesterday indicator (replaces the Current Streak tile)
- ccusage outage resilience: when a data build fails, the server keeps serving the last known-good `statusboard.json` instead of refusing to start
- Task-duration stats are emitted as fixed-size summaries (`longest` / `count` / `p50` / `p90`)

### Changed

- Single-pass parsing pipeline: every JSONL file is read exactly once per rebuild (previously ~8 times); the JSONL change watcher is one shared implementation with a 10 s rebuild cooldown
- Task definition tightened: system-injected user messages (`isMeta` caveats, slash-command expansions, interrupt placeholders) no longer count as tasks — task totals dropped ~35% and all task metrics now share one consistent population
- "Cache hit" metric replaced by "Cache share" = `cache_read / (cache_read + cache_creation + input)`, computed once in the backend (the old read/(read+creation) ratio was systematically inflated)
- Tool-usage per-project breakdown uses the same normalized project labels as the project table; subagent tool calls fold into the parent project
- `statusboard.json` slimmed from 221 KB to ~150 KB (raw 6k-element task-duration array removed)
- The frontend skips re-rendering when a poll returns an unchanged `generatedAt`
- The aggregator no longer imports ccusage under the hood — normalization happens in the build entrypoint

### Fixed

- Token trend could render NaN when a custom range included a date that only had task data (daily slots lacked the token fields)
- `normalize_totals` tolerates null / string numbers in ccusage output
- The workflow timeline no longer lists subagent sidechain files as sessions
- Files under `memory/` directories are never treated as session logs
- Duplicate `TimelineEvent` / `TimelineSession` type definitions unified into `types.ts`

## [0.2.0] - 2026-08-30

### Added

- Real per-project token accounting: tokens are measured from the JSONL `message.usage` records (deduplicated per API response via `message.id`) instead of being estimated from file-count share; per-project cost is priced per model using unit prices derived from ccusage daily `modelBreakdowns` (global-average fallback for unpriced models)
- Project entries now carry a per-model `modelUsage` breakdown
- Token throughput panel: selectable time range (all / 1M / 3M / 6M / 1Y) plus a custom range with a fully English calendar picker (year dropdown, one-click start/end switching, viewport-edge flipping)
- Models panel: rollup-by-provider mode with one aggregated bar per provider
- MIT license
- This changelog

### Changed

- All dates rendered in pinned en-US formatting regardless of OS/browser locale; CJK font fallbacks added for unavoidable Chinese folder names
- Activity heatmap redesigned as a fixed last-6-months, token-only grid that fills its card width with square cells, uniform gaps on both axes and month labels aligned to their columns; mouse-follow tooltip and cursor spotlight
- Layout: Token throughput, Models and Project statusboard are standalone panels; Tasks sits beside Activity at equal height; metric strip expanded to six tiles (adds Cache Hit)
- Tasks panel: the hour-of-day chart now renders the real task distribution (`tasks.hourlyTasks`, local-hour buckets) instead of a hardcoded placeholder shape, with a heatmap-style cursor-following tooltip showing the hour range and task count
- Activity heatmap: the viewport keeps its 6-month size but the grid now spans the full history with a six-month empty lead-in — drag or touchpad-scroll horizontally to pan back in time, pinned to the most recent weeks by default
- Server start now rebuilds the frontend bundle whenever `dist` is older than the sources (`--no-build` to skip), so every launch path serves the latest UI instead of a stale build

### Fixed

- Server served the stale `statusboard.json` baked into `frontend/dist` instead of the freshly generated root file
- Vite dev server served a mirror copy (`frontend/public/statusboard.json`) that could go stale; dev and production now read the root `statusboard.json` directly — a single data artefact
- Task-tool subagent logs were counted as standalone projects (25 fake `agent-*` worktree projects); they now fold into their parent project's tokens, and their prompts no longer count as user tasks
- Cache Hit stat tile showed 1% instead of 99.5% (percent-scale bug)
- Per-project tokens/cost were identical across all single-file projects (file-share estimation replaced by real measurement, see above)

## [0.1.0] - 2026-08-28

### Added

- Data collection layer: ccusage wrapper (session/daily/monthly) and JSONL parser (tasks, active time, projects) joined by an aggregator into a single `statusboard.json`
- Advanced analytics: tool usage, prompt categories, model efficiency, workflow timeline
- React + Vite + Tailwind mission-control dashboard: hero readout, metric strip, activity heatmap, token trend, model distribution, tasks panel, project table
- CLI: `generate_statusboard.py` (one-shot / watch), `serve_statusboard.py` (static server + auto-regeneration), cross-platform `bin/` launchers
