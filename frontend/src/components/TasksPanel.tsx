import { useLayoutEffect, useRef, useState } from "react";
import { ACCENT_CLASS, type Accent, type TaskStats } from "../types";
import { formatSeconds } from "../utils/format";

/**
 * Task analytics: total / avg / longest / busiest day, plus the real
 * hour-of-day task distribution.  Bars brighten toward the cursor and a
 * heatmap-style tooltip follows the mouse.
 */
export function TasksPanel({ tasks }: { tasks: TaskStats }) {
  const hourly = tasks.hourlyTasks ?? [];
  const maxHourly = Math.max(1, ...hourly);

  const [hover, setHover] = useState<number | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef({ x: 0, y: 0 });

  const placeTip = () => {
    const tip = tipRef.current;
    if (!tip) return;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const { x, y } = cursorRef.current;
    let left = x + 14;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    let top = y - h - 14;
    if (top < 8) top = y + 18;
    tip.style.transform = `translate(${left}px, ${top}px)`;
  };

  // Jump to the new anchor without animating across the screen, then
  // re-enable the smooth 90ms follow (same choreography as the heatmap).
  useLayoutEffect(() => {
    if (hover === null) return;
    const tip = tipRef.current;
    if (!tip) return;
    tip.style.transition = "none";
    placeTip();
    requestAnimationFrame(() => {
      if (tipRef.current) tipRef.current.style.transition = "transform 90ms ease-out";
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover]);

  const onBarsMouseMove = (e: React.MouseEvent) => {
    cursorRef.current = { x: e.clientX, y: e.clientY };
    if (hover !== null) placeTip();
  };

  return (
    <section className="panel p-5 sm:p-6 h-full flex flex-col gap-4">
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
        <span className="eyebrow">Task distribution</span>
        <div
          className="flex items-end gap-[2px] h-16"
          onMouseMove={onBarsMouseMove}
          onMouseLeave={() => setHover(null)}
        >
          {Array.from({ length: 24 }).map((_, i) => {
            const count = hourly[i] ?? 0;
            const height = count ? Math.max(8, (count / maxHourly) * 100) : 2;
            return (
              <div
                key={i}
                onMouseEnter={() => setHover(i)}
                className="task-col flex-1 h-full flex items-end"
              >
                <div
                  style={{ height: `${height}%` }}
                  className={`task-bar w-full rounded-sm ${
                    count ? "bg-signal/60" : "bg-ink-700/60"
                  }`}
                />
              </div>
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

      {hover !== null && (
        <div
          ref={tipRef}
          className="fixed left-0 top-0 z-50 pointer-events-none will-change-transform"
        >
          <div className="panel px-3.5 py-2.5 flex flex-col gap-1.5 min-w-max">
            <span className="font-mono text-xs text-fg whitespace-nowrap">
              {String(hover).padStart(2, "0")}:00 – {String((hover + 1) % 24).padStart(2, "0")}:00
            </span>
            <span className="font-mono text-[11px] text-signal">
              tasks&nbsp;&nbsp;{(hourly[hover] ?? 0).toLocaleString("en-US")}
            </span>
          </div>
        </div>
      )}
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