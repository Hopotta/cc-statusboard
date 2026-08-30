# Changelog

All notable changes to cc-statusboard will be documented in this file.

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

### Fixed

- Server served the stale `statusboard.json` baked into `frontend/dist` instead of the freshly generated root file
- Cache Hit stat tile showed 1% instead of 99.5% (percent-scale bug)
- Per-project tokens/cost were identical across all single-file projects (file-share estimation replaced by real measurement, see above)

## [0.1.0] - 2026-08-28

### Added

- Data collection layer: ccusage wrapper (session/daily/monthly) and JSONL parser (tasks, active time, projects) joined by an aggregator into a single `statusboard.json`
- Advanced analytics: tool usage, prompt categories, model efficiency, workflow timeline
- React + Vite + Tailwind mission-control dashboard: hero readout, metric strip, activity heatmap, token trend, model distribution, tasks panel, project table
- CLI: `generate_statusboard.py` (one-shot / watch), `serve_statusboard.py` (static server + auto-regeneration), cross-platform `bin/` launchers
