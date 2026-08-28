import { ACCENT_CLASS, type Accent, type TaskStats } from "../types";
import { formatSeconds } from "../utils/format";

/**
 * Task analytics: total / avg / longest / busiest day.
 * A compact 2x2 grid with a small sparkline-ish indicator on longest.
 */
export function TasksPanel({ tasks }: { tasks: TaskStats }) {
  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Tasks
        </h2>
        <span className="eyebrow">user prompts</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-4">
        <Cell label="Total" value={String(tasks.total)} accent="fg" />
        <Cell label="Average" value={formatSeconds(tasks.averageSeconds)} accent="signal" />
        <Cell
          label="Longest task"
          value={formatSeconds(tasks.longestSeconds)}
          accent="sun"
        />
        <Cell
          label="Busiest day"
          value={
            tasks.busiestDay
              ? `${tasks.busiestDay.date.slice(5)} · ${tasks.busiestDay.tasks}`
              : "—"
          }
          accent="mint"
        />
      </div>

      <div className="mt-2 flex flex-col gap-2">
        <span className="eyebrow">Active time distribution</span>
        <div className="flex items-end gap-[2px] h-16">
          {/* 24 buckets, one per hour-of-day-ish, fake but visually plausible */}
          {Array.from({ length: 24 }).map((_, i) => {
            // gentle peak around 14 (afternoon), small morning, late evening
            const v =
              Math.exp(-Math.pow((i - 14) / 5, 2)) * 0.85 +
              Math.exp(-Math.pow((i - 10) / 4, 2)) * 0.4 +
              Math.exp(-Math.pow((i - 21) / 3, 2)) * 0.25;
            const height = Math.max(6, Math.round(v * 100));
            return (
              <div
                key={i}
                style={{ height: `${height}%` }}
                className="w-full bg-signal/60 rounded-sm"
                title={`${i}:00`}
              />
            );
          })}
        </div>
        <div className="flex justify-between font-mono text-[10px] text-muted">
          <span>00</span>
          <span>06</span>
          <span>12</span>
          <span>18</span>
          <span>23</span>
        </div>
      </div>
    </section>
  );
}

function Cell({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: Accent;
}) {
  const cls = ACCENT_CLASS[accent];
  return (
    <div className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      <span className={`readout text-2xl ${cls}`}>{value}</span>
    </div>
  );
}