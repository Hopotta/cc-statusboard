import { useMemo } from "react";
import type { DailyActivity } from "../types";

/**
 * Contribution-style heatmap of daily activity for the past ~365 days.
 * Two stacked rows per week: token activity on top, task activity below.
 * Cell color intensity scales with that day's value relative to its max.
 */
export function ActivityHeatmap({ days }: { days: DailyActivity[] }) {
  const cells = useMemo(() => buildYearGrid(days), [days]);

  // Find maxes for color scaling.
  const maxTokens = Math.max(1, ...cells.map((c) => c.tokens));
  const maxTasks = Math.max(1, ...cells.map((c) => c.tasks));

  const monthLabels = useMemo(() => buildMonthLabels(cells), [cells]);

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Activity · last 12 months
        </h2>
        <div className="flex items-center gap-3 font-mono text-[10px] text-muted">
          <span>less</span>
          <Swatch tokens={0.05} maxTokens={1} tasks={0} maxTasks={1} />
          <Swatch tokens={0.25} maxTokens={1} tasks={0.25} maxTasks={1} />
          <Swatch tokens={0.5} maxTokens={1} tasks={0.5} maxTasks={1} />
          <Swatch tokens={0.75} maxTokens={1} tasks={0.75} maxTasks={1} />
          <Swatch tokens={1} maxTokens={1} tasks={1} maxTasks={1} />
          <span>more</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="flex flex-col gap-2 min-w-fit">
          {/* Month labels along the top */}
          <div className="flex gap-1 pl-7">
            {monthLabels.map((m, i) => (
              <div
                key={i}
                className="font-mono text-[10px] text-muted tracking-widest2 uppercase"
                style={{ width: 53, marginLeft: i === 0 ? m.offset * 12 : 0 }}
              >
                {m.label}
              </div>
            ))}
          </div>

          {/* Two stacked rows: tokens (top), tasks (bottom) */}
          <Row
            label="tok"
            cells={cells}
            getValue={(c) => c.tokens}
            max={maxTokens}
            channel="tokens"
          />
          <Row
            label="tsk"
            cells={cells}
            getValue={(c) => c.tasks}
            max={maxTasks}
            channel="tasks"
          />
        </div>
      </div>

      <p className="font-mono text-[11px] text-muted">
        Each week has two cells stacked vertically: <span className="text-signal">tok</span> for
        tokens processed, <span className="text-mint">tsk</span> for tasks completed.
      </p>
    </section>
  );
}

function Swatch({
  tokens,
  maxTokens,
  tasks,
  maxTasks,
}: {
  tokens: number;
  maxTokens: number;
  tasks: number;
  maxTasks: number;
}) {
  return (
    <span
      className="inline-block w-3 h-3 rounded-sm"
      style={{
        background: `linear-gradient(135deg, ${rgba("signal", tokens / maxTokens)}, ${rgba("mint", tasks / maxTasks)})`,
      }}
    />
  );
}

function Row({
  label,
  cells,
  getValue,
  max,
  channel,
}: {
  label: string;
  cells: Cell[];
  getValue: (c: Cell) => number;
  max: number;
  channel: "tokens" | "tasks";
}) {
  // We want to render Sunday-first columns.  Build weeks.
  const weeks: Cell[][] = [];
  let week: Cell[] = [];
  cells.forEach((c, i) => {
    week.push(c);
    if (week.length === 7 || i === cells.length - 1) {
      weeks.push(week);
      week = [];
    }
  });

  return (
    <div className="flex gap-1 items-center">
      <span className="eyebrow w-6">{label}</span>
      <div className="flex gap-1">
        {weeks.map((w, wi) => (
          <div key={wi} className="flex flex-col gap-1">
            {w.map((c, di) => {
              const v = getValue(c);
              const ratio = max ? v / max : 0;
              return (
                <div
                  key={di}
                  title={`${c.date} · ${v.toLocaleString()} ${channel === "tokens" ? "tokens" : "tasks"}`}
                  className="w-[10px] h-[10px] rounded-[2px] border border-ink-700"
                  style={{
                    background: v
                      ? rgba(channel === "tokens" ? "signal" : "mint", ratio)
                      : "transparent",
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

interface Cell {
  date: string;
  tokens: number;
  tasks: number;
}

function buildYearGrid(days: DailyActivity[]): Cell[] {
  // Build a dense grid: one cell per day for the last ~365 days, ordered Sun..Sat.
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(start.getDate() - 364);

  // Align start to Sunday.
  while (start.getDay() !== 0) {
    start.setDate(start.getDate() - 1);
  }

  const lookup = new Map(days.map((d) => [d.date, d]));
  const cells: Cell[] = [];
  const cursor = new Date(start);
  while (cursor <= today) {
    const iso = cursor.toISOString().slice(0, 10);
    const day = lookup.get(iso);
    cells.push({
      date: iso,
      tokens: day?.tokens ?? 0,
      tasks: day?.tasks ?? 0,
    });
    cursor.setDate(cursor.getDate() + 1);
  }
  return cells;
}

function buildMonthLabels(cells: Cell[]): { label: string; offset: number }[] {
  const out: { label: string; offset: number }[] = [];
  let prevMonth = -1;
  cells.forEach((c, i) => {
    const m = Number(c.date.slice(5, 7));
    if (m !== prevMonth) {
      const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      out.push({ label: monthNames[m - 1] ?? "", offset: i % 7 });
      prevMonth = m;
    }
  });
  return out;
}

function rgba(channel: "signal" | "mint", ratio: number): string {
  const r = Math.max(0.05, Math.min(1, ratio));
  // signal: #FF7A3D, mint: #6FE3C2
  const base = channel === "signal" ? [255, 122, 61] : [111, 227, 194];
  return `rgba(${base[0]}, ${base[1]}, ${base[2]}, ${r.toFixed(3)})`;
}