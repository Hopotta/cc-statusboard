# Changelog

All notable changes to cc-statusboard will be documented in this file.

## [0.4.0] - 2026-08-31

### Changed

- **Architecture (A3): the rebuild critical path no longer runs `ccusage`.** Global totals, the model breakdown and the daily series are computed natively from the deduplicated JSONL `message.usage` records (`native_usage.py`), so a full rebuild costs the scan time alone (~4 s) and stays fresh during active use. Previously ccusage (28–32 s per call at ~283 MB, fatal in parallel) froze the token/model/daily panels for as long as the session stayed active.
- `ccusage` is demoted to a background reconciler and pricing source (`reconcile.py`): it runs serially with a 300 s timeout at server start and every 6 h, refreshing `.ccusage_cache.json` (now `{fingerprint, ranAt, daily}`; legacy caches with a `session` block still readable). It can never stall or fail a rebuild.
- Headline token/cost figures switched from the ccusage aggregation to the JSONL-native one — and the reconciliation uncovered a misreading in the old accounting: ccusage's daily rollup also covers other agents' session logs (`~/.codex`, the gpt-*/codex-* models ≈ 4.75% of its volume here). The cross-check now compares only models both sides see (`meta.ccusageTotalTokens`), reports the excluded volume as `meta.ccusageOtherAgentsTokens`, and on the same model universe the native total runs ~1% *above* ccusage's (its cross-file resume dedup) — not ~5% below.
- Dollar figures are priced natively (tokens × blended per-model unit rates derived from ccusage's daily `modelBreakdowns`); the frontend marks every cost with a "~" and a confidence tooltip (blended pricing, ±10% on router models).
- The P2-2 backlog trigger condition was rewritten: the per-file parse cache now targets the scan stage (watched via the new timing log), not the ccusage stage that actually hit the wall.

### Added

- `meta` block in `statusboard.json`: `pricingSource` / `pricingAsOf`, `ccusageReconciledAt`, `ccusageTotalTokens`, `ccusageOtherAgentsTokens`, `totalTokensDiffPct` — provenance for what is native (always fresh) vs. what leans on ccusage.
- `tasks.filterStats` sentinel: how user-shaped entries were classified (toolResult / isMeta / injected-prefix / task), so an upstream JSONL format change shifts a visible distribution instead of silently distorting task metrics; the build prints a warning when the injected share exceeds 55%.
- `[timing]` rebuild latency log (`scan / aggregate / total`) and ccusage duration logging in the reconciler — trigger conditions can now be data-driven.
- `python collector/generate_statusboard.py --reconcile` for an on-demand ccusage refresh.

### Fixed

- Active-use staleness: ccusage-side panels (tokens/cost/models/daily) no longer freeze while Claude Code is running, and the silent partial-staleness mode (fallback to a stale ccusage cache behind a fresh `generatedAt`) is structurally gone — the only numbers that can age are pricing, which is labeled with its as-of date.
- A failed ccusage run with no cache at all no longer aborts the build; costs price to 0 and `meta.pricingSource` flags it.
- Zero-usage synthetic assistant entries (model `<synthetic>`: error bubbles, interrupt notices) no longer appear as 0-token rows in the model breakdown.

## [0.3.1] - 2026-08-31

### Changed

- Activity heatmap: the plain CSS `:hover` cell scale is replaced by a subtle ripple across the hovered cell's 3×3 neighbourhood, written synchronously from a delegated `mouseover` listener so it tracks the cursor with no frame of lag on fast swipes; the highlight ring is gone and the grid JSX is memoized so tooltip re-renders never touch the ~340 cells
- Tasks: the hour-of-day distribution's hover target is now the full-height column (zero-count hours included, so every hour shows its tooltip) while the brighten/glow effect stays on the bar itself

### Fixed

- Token throughput: toggling total/stacked no longer shifts the x-axis and plot area (the legend is always mounted and merely hidden in total view)

## [0.3.0] - 2026-08-30

### Added

- Per-session analytics: every session gets a tokens/cost/tasks rollup (subagent sidechain logs fold into their parent session) with a sortable Sessions table answering "which session was the most expensive?"
- Token throughput: a stacked mode showing the daily input / output / cache-read / cache-creation composition, plus outlier markers on days beyond mean + 2σ
- "Today" metric tile: tokens used today with a ±% vs-yesterday indicator (replaces the Current Streak tile)
- ccusage outage resilience: when a data build fails, the server keeps serving the last known-good `statusboard.json` instead of refusing to start
- Task-duration stats are emitted as fixed-size summaries (`longest` / `count` / `p50` / `p90`)
- Stale-state signalling: while builds fail, responses carry an `X-Statusboard-Stale` header and the top bar shows "stale since HH:MM:SS — showing last known-good data"
- ccusage output cache keyed by the JSONL input fingerprint — unchanged data skips the ccusage subprocesses entirely (startup ~55 s → ~4 s), the two ccusage calls run in parallel, and a failed refresh falls back to the stale cache
- Prompt taxonomy expanded from 8 to 14 categories (`continue`, `git`, `run`, `ui`, `maintain`, `report` added) with colloquial synonym patterns mined from real "other" prompts — the "other" share drops from 59% to ~18%
- Prompt categories panel shows a hint bar when the "other" bucket exceeds 40%, flagging the heuristic split as a rough hint

### Changed

- Single-pass parsing pipeline: every JSONL file is read exactly once per rebuild (previously ~8 times); the JSONL change watcher is one shared implementation with a 10 s rebuild cooldown
- Task definition tightened: system-injected user messages (`isMeta` caveats, slash-command expansions, interrupt placeholders) no longer count as tasks — task totals dropped ~35% and all task metrics now share one consistent population
- "Cache hit" metric replaced by "Cache share" = `cache_read / (cache_read + cache_creation + input)`, computed once in the backend (the old read/(read+creation) ratio was systematically inflated)
- Tool-usage per-project breakdown uses the same normalized project labels as the project table; subagent tool calls fold into the parent project
- `statusboard.json` slimmed from 221 KB to ~72 KB: raw 6k-element task-duration array removed, compact serialization by default (`--pretty` to opt out), and no prompt text in the artifact (prompt-category examples and workflow-timeline prompt labels dropped)
- The frontend skips re-rendering when a poll returns an unchanged `generatedAt`
- The aggregator no longer imports ccusage under the hood — normalization happens in the build entrypoint
- Advanced analytics reordered: Prompt categories and Tool usage (15 tools, always expanded) now sit above Model efficiency and Workflow timeline

### Fixed

- Token trend could render NaN when a custom range included a date that only had task data (daily slots lacked the token fields)
- `normalize_totals` tolerates null / string numbers in ccusage output
- The workflow timeline no longer lists subagent sidechain files as sessions
- Files under `memory/` directories are never treated as session logs
- Duplicate `TimelineEvent` / `TimelineSession` type definitions unified into `types.ts`
- Background task notifications and list-shaped interrupt placeholders leaked into the task population (now filtered alongside the string-shaped ones)
- Prompt-category bars could be squeezed to zero width in the third-width layout (rank column hidden below xl, label column resized)

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
