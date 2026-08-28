import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DailyActivity } from "../types";
import { localISODate, formatLongDateTimeEn } from "../utils/date";

/**
 * Contribution-style heatmap of daily activity.
 * Two stacked rows per week: token activity on top, task activity below.
 * Cell color intensity scales with that day's value relative to its max.
 *
 * The range is selectable (1–12 months, step 1). Cell size is constant so
 * switching ranges stretches the grid horizontally, never the cells.
 */

const MONTHS_MIN = 1;
const MONTHS_MAX = 12;

// 10px cell + 4px gap — keep in sync with the cell classes below.
const CELL = 10;
const GAP = 4;
const WEEK_W = 7 * CELL + 6 * GAP; // 94px
const DAY_STEP = CELL + GAP; // 14px

type Channel = "tokens" | "tasks";

export function ActivityHeatmap({ days }: { days: DailyActivity[] }) {
  const [months, setMonths] = useState(12);
  const cells = useMemo(() => buildGrid(days, months), [days, months]);
  const monthLabels = useMemo(() => buildMonthLabels(cells), [cells]);

  const maxTokens = Math.max(1, ...cells.map((c) => c.tokens));
  const maxTasks = Math.max(1, ...cells.map((c) => c.tasks));

  const [hover, setHover] = useState<{ cell: Cell; channel: Channel } | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef({ x: 0, y: 0 });
  const gridRef = useRef<HTMLDivElement>(null);

  const placeTip = () => {
    const tip = tipRef.current;
    if (!tip) return;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const { x, y } = cursorRef.current;
    let left = x + 14; // up-right of the cursor = top-right corner of the square
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    let top = y - h - 14;
    if (top < 8) top = y + 18;
    tip.style.transform = `translate(${left}px, ${top}px)`;
  };

  // Position as soon as a new cell is hovered (tooltip just mounted).
  useLayoutEffect(() => {
    if (!hover) return;
    const tip = tipRef.current;
    if (!tip) return;
    // Jump to the new anchor without animating across the screen…
    tip.style.transition = "none";
    placeTip();
    // …then re-enable the smooth follow.
    requestAnimationFrame(() => {
      if (tipRef.current) tipRef.current.style.transition = "transform 90ms ease-out";
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover]);

  const onGridMouseMove = (e: React.MouseEvent) => {
    cursorRef.current = { x: e.clientX, y: e.clientY };
    if (hover) placeTip();

    // Cursor-following spotlight, via CSS vars so cells never re-render.
    const el = gridRef.current;
    if (el) {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    }
  };

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Activity · last {months} month{months === 1 ? "" : "s"}
        </h2>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 font-mono text-[10px] text-muted">
            <span>less</span>
            <Swatch tokens={0.05} maxTokens={1} tasks={0} maxTasks={1} />
            <Swatch tokens={0.25} maxTokens={1} tasks={0.25} maxTasks={1} />
            <Swatch tokens={0.5} maxTokens={1} tasks={0.5} maxTasks={1} />
            <Swatch tokens={0.75} maxTokens={1} tasks={0.75} maxTasks={1} />
            <Swatch tokens={1} maxTokens={1} tasks={1} maxTasks={1} />
            <span>more</span>
          </div>
          <MonthStepper months={months} onChange={setMonths} />
        </div>
      </div>

      <div
        className="overflow-x-auto heat-scope"
        onMouseMove={onGridMouseMove}
        onMouseLeave={() => setHover(null)}
      >
        <div className="flex flex-col gap-2 min-w-fit">
          {/* Month labels along the top */}
          <div className="relative h-4 pl-7">
            {monthLabels.map((m, i) => (
              <div
                key={i}
                className="absolute top-0 font-mono text-[10px] text-muted tracking-widest2 uppercase whitespace-nowrap"
                style={{ left: 28 + m.x }}
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
            onEnter={(cell, channel) => setHover({ cell, channel })}
          />
          <Row
            label="tsk"
            cells={cells}
            getValue={(c) => c.tasks}
            max={maxTasks}
            channel="tasks"
            onEnter={(cell, channel) => setHover({ cell, channel })}
          />
        </div>
      </div>

      <p className="font-mono text-[11px] text-muted">
        Each week has two cells stacked vertically: <span className="text-signal">tok</span> for
        tokens processed, <span className="text-mint">tsk</span> for tasks completed.
      </p>

      {hover && (
        <div
          ref={tipRef}
          className="fixed left-0 top-0 z-50 pointer-events-none will-change-transform"
        >
          <HeatTooltip cell={hover.cell} channel={hover.channel} />
        </div>
      )}
    </section>
  );
}

function HeatTooltip({ cell, channel }: { cell: Cell; channel: Channel }) {
  const d = new Date(
    Number(cell.date.slice(0, 4)),
    Number(cell.date.slice(5, 7)) - 1,
    Number(cell.date.slice(8, 10)),
  );
  const weekday = WEEKDAY_LONG[d.getDay()];
  return (
    <div className="panel px-3.5 py-2.5 flex flex-col gap-1.5 min-w-max">
      <span className="font-mono text-xs text-fg whitespace-nowrap">
        {weekday} · {formatLongDateTimeEn(d).split(", ")[0]}
      </span>
      <div className="flex flex-col gap-0.5 font-mono text-[11px]">
        <span className={channel === "tokens" ? "text-signal" : "text-muted"}>
          tok&nbsp;&nbsp;{cell.tokens.toLocaleString("en-US")}
        </span>
        <span className={channel === "tasks" ? "text-mint" : "text-muted"}>
          tsk&nbsp;&nbsp;{cell.tasks.toLocaleString("en-US")}
        </span>
      </div>
    </div>
  );
}

const WEEKDAY_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function MonthStepper({
  months,
  onChange,
}: {
  months: number;
  onChange: (n: number) => void;
}) {
  const btn =
    "font-mono text-xs w-6 h-6 rounded border border-ink-700 text-muted hover:border-signal/60 hover:text-signal transition-colors disabled:opacity-30 disabled:hover:border-ink-700 disabled:hover:text-muted flex items-center justify-center";
  return (
    <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted">
      <button
        type="button"
        aria-label="Fewer months"
        className={btn}
        disabled={months <= MONTHS_MIN}
        onClick={() => onChange(Math.max(MONTHS_MIN, months - 1))}
      >
        −
      </button>
      <span className="tnum w-16 text-center">
        {months} {months === 1 ? "month" : "months"}
      </span>
      <button
        type="button"
        aria-label="More months"
        className={btn}
        disabled={months >= MONTHS_MAX}
        onClick={() => onChange(Math.min(MONTHS_MAX, months + 1))}
      >
        +
      </button>
    </div>
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
  onEnter,
}: {
  label: string;
  cells: Cell[];
  getValue: (c: Cell) => number;
  max: number;
  channel: Channel;
  onEnter: (cell: Cell, channel: Channel) => void;
}) {
  // Sunday-first columns.  Build weeks.
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
                  onMouseEnter={() => onEnter(c, channel)}
                  className="heat-cell w-[10px] h-[10px] rounded-[2px] border border-ink-700"
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

function buildGrid(days: DailyActivity[], months: number): Cell[] {
  // Dense grid: one cell per day from the Sunday on/before the first day of
  // (months - 1) months ago, through today.  Keyed by the user's LOCAL date
  // string so the lookup matches what the Python parser wrote.
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today.getFullYear(), today.getMonth() - (months - 1), 1);
  while (start.getDay() !== 0) {
    start.setDate(start.getDate() - 1);
  }

  const lookup = new Map(days.map((d) => [d.date, d]));
  const cells: Cell[] = [];
  const cursor = new Date(start);
  while (cursor <= today) {
    const iso = localISODate(cursor);
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

function buildMonthLabels(cells: Cell[]): { label: string; x: number }[] {
  const out: { label: string; x: number }[] = [];
  let prevMonth = -1;
  cells.forEach((c, i) => {
    const m = Number(c.date.slice(5, 7));
    if (m !== prevMonth) {
      const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const w = Math.floor(i / 7);
      const d = i % 7;
      out.push({ label: monthNames[m - 1] ?? "", x: w * WEEK_W + d * DAY_STEP });
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
