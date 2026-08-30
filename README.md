# Claude Code Statusboard

A local Web Statusboard for **Claude Code** usage — token / cost / model / task / project
analytics, with a mission-control-style UI built on top of your real session logs.

![Dashboard screenshot](example.png)

> Built on top of [`ccusage`](https://ccusage.com/) + Claude Code's JSONL session logs.
> Owns its own intermediate data layer (`statusboard.json`) so the data sources stay
> swappable (Claude Code, Codex, OpenCode, custom agents).

## What you get

| Section                 | Source  | What it shows                                                          |
| ----------------------- | ------- | ---------------------------------------------------------------------- |
| **Hero readout**        | both    | the single most important number — total tokens processed               |
| **Metric strip**        | both    | time · tasks · top model · today · spend · cache share (6 tiles)        |
| **Activity heatmap**    | JSONL   | token heatmap with a 6-month viewport; drag to pan back through the full history |
| **Token throughput**    | ccusage | daily token trend with selectable range (all / 1M / 3M / 6M / 1Y / custom dates), stacked input/output/cache view and outlier markers |
| **Models**              | ccusage | per-model bars, or rollup by provider (OpenAI, DeepSeek, …)             |
| **Tasks**               | JSONL   | total, average, longest, busiest day, hour-of-day distribution          |
| **Project statusboard** | JSONL   | per-project token/task/time table                                       |
| **Sessions**            | JSONL   | per-session tokens/cost/tasks ranking (sortable)                        |
| **Advanced analytics**  | both    | tool usage, prompt categories, model efficiency, workflow timeline      |

All numbers are derived from your own `~/.claude/projects/*.jsonl` files and the
`ccusage` JSON output — nothing is fabricated.

## Quick start

Requires Python 3.9+ and Node 18+ (run `npm install` inside `frontend/` once).

```bash
# Data generation and stale-frontend rebuilds are handled automatically.
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
│   ├── jsonl_parser.py       # single-pass scan of ~/.claude/projects/ (tasks, time, tokens)
│   ├── advanced.py           # analytics from the scan (tools, prompts, efficiency, timeline)
│   ├── aggregator.py         # joins both into statusboard.json
│   ├── watcher.py            # shared JSONL change watcher (both CLI entrypoints)
│   ├── generate_statusboard.py  # CLI: build + (optional) watch statusboard.json
│   └── serve_statusboard.py  # CLI: serve the built frontend + open browser
├── frontend/
│   ├── src/                 # React + Vite + Tailwind + Recharts
│   └── dist/                # build output
├── bin/
│   ├── cc-statusboard       # POSIX launcher
│   └── cc-statusboard.cmd   # Windows launcher
├── statusboard.json         # generated data artefact
├── CHANGELOG.md
├── LICENSE
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
                     "averageHuman", "longestSeconds", "busiestDay",
                     "hourlyTasks": [24 ints, local-hour task counts] },
  "projects":      [ { "project", "projectPath", "tasks", "activeSeconds",
                       "activeHuman", "tokens", "cost", "files",
                       "modelUsage": { "<model>": { "inputTokens", "outputTokens",
                                                    "cacheCreationTokens",
                                                    "cacheReadTokens" } } }, ... ],
  "sessions":      [ { "sessionId", "project", "projectPath", "files", "tasks",
                       "activeSeconds", "activeHuman", "tokens", "cost",
                       "averageSeconds", "firstTs", "lastTs" }, ... ],
  "dailyActivity": [ { "date", "tokens", "inputTokens", "outputTokens",
                       "cacheCreationTokens", "cacheReadTokens", "cost",
                       "tasks", "activeSeconds" }, ... ],
  "advanced": {
    "toolUsage":        { "tools": [...], "total", "uniqueTools", "byProject" },
    "workflowTimeline": { "sessions": [...], "count" },
    "promptCategories": { "categories": [...], "total", "examples" },
    "modelEfficiency":  { "tokensPerTask", "costPerTask", "outputRatio",
                          "cacheShare", "cacheReadTokens",
                          "cacheCreationTokens", "inputTokens",
                          "totalTokens", "totalCost" }
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

> A "task" is a real user message: `type=user` AND no `toolUseResult`, AND
> not system-injected (no `isMeta`, no `<command-*>` slash-command expansion,
> no interrupt placeholder).

That filters out tool responses (which are echoed back as `type=user` too)
and injected entries, so every task metric counts the same population of
genuine user prompts.

## Active-time rule

> For each user task, duration = next user task timestamp − this task timestamp,
> capped at 2 hours.

The 2-hour cap is intentional: a session can stay open for days while the user is
AFK; without a cap, "active time" would conflate wall-clock with effort.

## Per-project token rule

> Project tokens are measured directly from the `message.usage` records in each
> JSONL file. Multiple content blocks of one API response share a `message.id`
> and each carry the full usage — each response is counted exactly once.

Per-project cost is priced per model using unit prices derived from ccusage's
daily `modelBreakdowns` (models without pricing data fall back to the global
average unit price). Because ccusage additionally deduplicates sessions resumed
across files, the sum of project tokens sits slightly (~5%) below the ccusage
global total by design.

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

Both the dev server (:5173) and the production server (:3456) read the same
root `statusboard.json` — there is a single data artefact.

## License

[MIT](LICENSE) — do whatever.