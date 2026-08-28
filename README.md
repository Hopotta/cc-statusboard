# Claude Code Statusboard

A local Web Statusboard for **Claude Code** usage — token / cost / model / task / project
analytics, with a mission-control-style UI built on top of your real session logs.

> Built on top of [`ccusage`](https://ccusage.com/) + Claude Code's JSONL session logs.
> Owns its own intermediate data layer (`statusboard.json`) so the data sources stay
> swappable (Claude Code, Codex, OpenCode, custom agents).

## What you get

| Section                       | Source                    | What it shows                                              |
| ----------------------------- | ------------------------- | ---------------------------------------------------------- |
| **Hero readout**              | both                      | the single most important number — total tokens processed    |
| **Metric strip**              | both                      | time · tasks · top model · streaks · spend                 |
| **Activity heatmap**          | JSONL                     | 12-month contribution-style grid of tokens + tasks         |
| **Token throughput**          | ccusage                   | daily token trend (area chart)                             |
| **Model distribution**        | ccusage                   | share by model, with proportional spend                    |
| **Tasks**                     | JSONL                     | total, average, longest, busiest day                       |
| **Project statusboard**       | JSONL                     | per-project token/task/time table                          |
| **Advanced analytics**        | both                      | tool usage, prompt categories, model efficiency, timeline  |

All numbers are derived from your own `~/.claude/projects/*.jsonl` files and the
`ccusage` JSON output — nothing is fabricated.

## Quick start

```bash
# 1. Generate the data
python collector/generate_statusboard.py --once

# 2. Build the frontend (or use the launcher, which does this for you)
cd frontend && npm install && npm run build && cd ..

# 3. Serve the dashboard
python collector/serve_statusboard.py --port 3456
# open http://127.0.0.1:3456
```

Or, in one shot:

```bash
# Auto-regenerates whenever a JSONL file changes, then serves on :3456
python collector/serve_statusboard.py --watch
```

A cross-platform wrapper is provided:

```bash
bin/cc-statusboard              # POSIX (bash / zsh)
bin/cc-statusboard --watch      # same, with auto-regenerate on JSONL change
bin/cc-statusboard.cmd          # Windows
```

## Project layout

```
cc-statusboard/
├── collector/
│   ├── ccusage_parser.py     # wraps `ccusage` CLI, parses JSON
│   ├── jsonl_parser.py       # walks ~/.claude/projects/, counts tasks & time
│   ├── aggregator.py         # joins both into statusboard.json
│   ├── advanced.py           # Phase 4 analytics (tools, prompts, efficiency, timeline)
│   ├── generate_statusboard.py  # CLI: build + (optional) watch statusboard.json
│   └── serve_statusboard.py  # CLI: serve the built frontend + open browser
├── frontend/
│   ├── src/                 # React + Vite + Tailwind + Recharts
│   ├── public/              # statusboard.json lives here in dev
│   └── dist/                # built artifacts (committed-friendly; gitignored)
├── bin/
│   ├── cc-statusboard       # POSIX launcher
│   └── cc-statusboard.cmd   # Windows launcher
├── statusboard.json         # the canonical data artefact (JSON)
└── README.md
```

## Data model

`statusboard.json` is the single source of truth for the UI.  Top-level keys:

```jsonc
{
  "summary":       { "totalTokens": 18559011, "totalTasks": 55, "totalTimeHuman": "4h 33m",
                     "averageTaskHuman": "4m", "mostUsedModel": { ... }, "totalCost": 1.27 },
  "tokens":        { "total", "input", "output", "cacheCreation", "cacheRead", "cost" },
  "models":        [ { "modelName", "totalTokens", "inputTokens", "outputTokens",
                       "cacheCreationTokens", "cacheReadTokens", "cost", "sharePct" }, ... ],
  "tasks":         { "total", "activeSeconds", "activeHuman", "averageSeconds",
                     "averageHuman", "longestSeconds", "busiestDay" },
  "projects":      [ { "project", "projectPath", "tasks", "activeSeconds",
                       "activeHuman", "tokens", "cost", "files" }, ... ],
  "dailyActivity": [ { "date", "tokens", "inputTokens", "outputTokens",
                       "cacheCreationTokens", "cacheReadTokens", "cost",
                       "tasks", "activeSeconds" }, ... ],
  "advanced": {
    "toolUsage":        { "tools": [...], "total", "uniqueTools", "byProject" },
    "workflowTimeline": { "sessions": [...], "count" },
    "promptCategories": { "categories": [...], "total", "examples" },
    "modelEfficiency":  { "tokensPerTask", "costPerTask", "outputRatio",
                          "cacheHitRate", "cacheReadTokens",
                          "cacheCreationTokens", "totalTokens", "totalCost" }
  },
  "generatedAt": "ISO-8601 UTC timestamp"
}
```

## Design choices

- **Backend:** a thin Python layer.  We delegate token math to `ccusage` (already the
  canonical stats engine) and only write our own parsers for what ccusage doesn't cover
  (tasks, time, projects, tool usage, prompt categories).
- **Storage:** `statusboard.json`, not SQLite — keeps the project portable and lets
  the UI be a pure static bundle.
- **Frontend:** React + Vite + Tailwind + Recharts.  Mission-control palette
  (deep ink, signal amber, mint, sun).  JetBrains Mono for telemetry, Inter for UI.
- **No telemetry leaves your machine** — everything is local.  The dashboard talks
  only to the local Python server.

## Task counting rule

Per the plan:

> A "task" is a real user message: `type=user` AND no `toolUseResult`.

That filters out tool responses (which are echoed back as `type=user` too).

## Active-time rule

> For each user task, duration = next user task timestamp − this task timestamp,
> capped at 2 hours.

The 2-hour cap is intentional: a session can stay open for days while the user is
AFK; without a cap, "active time" would conflate wall-clock with effort.

## Adding a new agent

The schema is intentionally agent-agnostic.  To wire up another agent (Codex,
OpenCode, custom), add an adapter that emits the same shape as
`collector/jsonl_parser.py` and feed it into `aggregator.aggregate()`.

## Development

```bash
# Run data + frontend in watch mode
python collector/serve_statusboard.py --watch &      # gen + watch + serve on :3456
cd frontend && npm run dev                            # vite dev with HMR on :5173
```

When you use the dev server, statusboard.json is mirrored into `frontend/public/`
so Vite can serve it as a static file.

## License

MIT — do whatever.