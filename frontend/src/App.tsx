import { useMemo } from "react";
import { useStatusboard } from "./hooks/useStatusboard";
import { HeroReadout } from "./components/HeroReadout";
import { StatTile } from "./components/StatTile";
import { ActivityHeatmap } from "./components/ActivityHeatmap";
import { TokenTrend } from "./components/TokenTrend";
import { ModelDistribution } from "./components/ModelDistribution";
import { TasksPanel } from "./components/TasksPanel";
import { ProjectTable } from "./components/ProjectTable";
import { ToolUsage } from "./components/ToolUsage";
import { PromptCategories } from "./components/PromptCategories";
import { ModelEfficiency } from "./components/ModelEfficiency";
import { WorkflowTimeline } from "./components/WorkflowTimeline";
import { formatSeconds, formatTokens, formatUSD, formatPct, relativeTime } from "./utils/format";
import { localISODate, diffDays, formatDateTimeEn } from "./utils/date";

export default function App() {
  const { data, loading, error, lastUpdated, reload } = useStatusboard(5000);

  const streak = useMemo(() => {
    if (!data) return { current: 0, longest: 0 };
    const dates = new Set(data.dailyActivity.map((d) => d.date));

    // Current streak: walk backwards from today (local) while the date is in the set.
    let current = 0;
    const cursor = new Date();
    while (dates.has(localISODate(cursor))) {
      current += 1;
      cursor.setDate(cursor.getDate() - 1);
    }

    // Longest streak: single linear pass over sorted dates.
    let longest = 0;
    let run = 0;
    let prev: string | null = null;
    for (const d of [...dates].sort()) {
      if (prev && diffDays(prev, d) === 1) {
        run += 1;
      } else {
        run = 1;
      }
      if (run > longest) longest = run;
      prev = d;
    }
    return { current, longest };
  }, [data]);

  return (
    <div className="min-h-screen bg-ink-950 text-fg">
      {/* Top nav strip */}
      <TopBar
        lastUpdated={lastUpdated}
        onReload={reload}
        loading={loading}
        error={error}
      />

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 sm:py-12 flex flex-col gap-8">
        {error && !data && (
          <ErrorBanner message={error} />
        )}
        {!data ? (
          <LoadingState />
        ) : (
          <>
            <HeroReadout
              totalTokens={data.summary.totalTokens}
              cost={data.tokens.cost}
              generatedAt={data.generatedAt}
            />

            <SectionHeader
              index="01"
              title="Overview"
              sub="daily activity, tokens, models, tasks, projects"
            />

            {/* Secondary metric strip */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <StatTile
                label="Total Time"
                value={formatSeconds(data.summary.totalTime)}
                sub="active task time"
                accent="signal"
              />
              <StatTile
                label="Total Tasks"
                value={String(data.summary.totalTasks)}
                sub={`avg ${formatSeconds(data.summary.averageTask)}`}
                accent="mint"
              />
              <StatTile
                label="Most Used"
                value={
                  data.summary.mostUsedModel
                    ? `${data.summary.mostUsedModel.sharePct.toFixed(0)}%`
                    : "—"
                }
                sub={data.summary.mostUsedModel?.modelName ?? "no data"}
                accent="sun"
              />
              <StatTile
                label="Current Streak"
                value={`${streak.current}d`}
                sub={`longest ${streak.longest}d`}
              />
              <StatTile
                label="Spend"
                value={formatUSD(data.tokens.cost)}
                sub="cumulative"
              />
              <StatTile
                label="Cache Hit"
                value={
                  data.advanced.modelEfficiency
                    ? formatPct(data.advanced.modelEfficiency.cacheHitRate, 0)
                    : "—"
                }
                sub="token reuse"
              />
            </div>

            {/* Heatmap fills its card and spreads its week columns; tasks keep a compact column */}
            <div className="flex flex-col md:flex-row gap-6 items-stretch">
              <div className="min-w-0 flex-1">
                <ActivityHeatmap days={data.dailyActivity} />
              </div>
              <div className="min-w-0 md:w-80 xl:w-96 shrink-0">
                <TasksPanel tasks={data.tasks} />
              </div>
            </div>

            {/* Token throughput — standalone */}
            <TokenTrend days={data.dailyActivity} />

            {/* Models — standalone */}
            <ModelDistribution models={data.models} />

            {/* Project statusboard — standalone */}
            <ProjectTable projects={data.projects} />

            {/* Phase 4: Advanced Analytics */}
            <SectionHeader
              index="02"
              title="Advanced analytics"
              sub="tool usage, prompt categories, model efficiency, workflow timeline"
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <ToolUsage toolUsage={data.advanced.toolUsage} />
              </div>
              <PromptCategories
                categories={data.advanced.promptCategories.categories}
                total={data.advanced.promptCategories.total}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {data.advanced.modelEfficiency && (
                <ModelEfficiency efficiency={data.advanced.modelEfficiency} />
              )}
              <div className="lg:col-span-2">
                <WorkflowTimeline
                  sessions={data.advanced.workflowTimeline.sessions}
                />
              </div>
            </div>

            <Footer
              generatedAt={data.generatedAt}
              topModel={data.summary.mostUsedModel?.modelName ?? "—"}
              totalTokens={data.summary.totalTokens}
            />
          </>
        )}
      </main>
    </div>
  );
}

function SectionHeader({
  index,
  title,
  sub,
}: {
  index: string;
  title: string;
  sub: string;
}) {
  return (
    <div className="flex items-end justify-between border-b border-ink-700 pb-3">
      <div className="flex items-baseline gap-4">
        <span className="font-mono text-[11px] text-signal">§ {index}</span>
        <h2 className="font-mono text-base text-fg uppercase tracking-widest2">
          {title}
        </h2>
      </div>
      <span className="font-mono text-xs text-muted hidden sm:inline">{sub}</span>
    </div>
  );
}

function TopBar({
  lastUpdated,
  onReload,
  loading,
  error,
}: {
  lastUpdated: Date | null;
  onReload: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <nav className="sticky top-0 z-10 border-b border-ink-700 bg-ink-950/80 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-12 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LogoMark />
          <span className="font-mono text-sm tracking-widest2 uppercase">
            cc-statusboard
          </span>
          <span className="eyebrow hidden sm:inline">v0.1</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-mono text-[11px] text-muted">
            {error ? (
              <span className="text-signal">error: {error}</span>
            ) : loading ? (
              "loading…"
            ) : (
              <>updated {relativeTime(lastUpdated)}</>
            )}
          </span>
          <button
            type="button"
            onClick={onReload}
            className="font-mono text-xs px-2.5 py-1 rounded border border-ink-700 hover:border-signal/60 hover:text-signal transition-colors"
          >
            Reload
          </button>
        </div>
      </div>
    </nav>
  );
}

function LogoMark() {
  return (
    <span
      aria-hidden
      className="inline-block w-4 h-4 rounded-sm bg-signal"
      style={{
        clipPath:
          "polygon(0 0, 100% 0, 100% 60%, 60% 60%, 60% 100%, 0 100%)",
      }}
    />
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="panel p-5 border-signal/40">
      <h2 className="eyebrow text-signal mb-2">Data feed offline</h2>
      <p className="font-mono text-sm text-fg">
        Couldn't read statusboard.json — {message}.
      </p>
      <p className="font-mono text-xs text-muted mt-2">
        Run{" "}
        <code className="px-1 py-0.5 rounded bg-ink-800 border border-ink-700">
          python collector/generate_statusboard.py
        </code>{" "}
        from the project root, then refresh.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="panel p-10 flex flex-col gap-3 items-start">
      <span className="live-dot" />
      <span className="eyebrow">Awaiting telemetry</span>
      <p className="font-mono text-sm text-muted">
        Fetching statusboard.json from the dev server…
      </p>
    </div>
  );
}

function Footer({
  generatedAt,
  topModel,
  totalTokens,
}: {
  generatedAt: string;
  topModel: string;
  totalTokens: number;
}) {
  return (
    <footer className="border-t border-ink-700 pt-6 pb-2 grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono text-[11px] text-muted">
      <FootCell label="Generated" value={formatDateTimeEn(new Date(generatedAt))} />
      <FootCell label="Top model" value={topModel} />
      <FootCell label="Total tokens" value={formatTokens(totalTokens, 2)} />
      <FootCell label="Build" value="cc-statusboard v0.1" />
    </footer>
  );
}

function FootCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="eyebrow">{label}</span>
      <span className="text-fg">{value}</span>
    </div>
  );
}