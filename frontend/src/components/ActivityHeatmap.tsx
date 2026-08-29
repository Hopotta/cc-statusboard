import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DailyActivity } from "../types";
import { localISODate, formatLongDateTimeEn } from "../utils/date";

/**
 * Contribution-style heatmap of daily token activity for the last 6 months.
 * One row of week columns (7 stacked day-cells each); color intensity scales
 * with that day's tokens relative to the max.
 *
 * The grid fills whatever width/height the card gives it: cell size is the
 * largest square that fits both axes (with small minimum gaps), and leftover
 * space is distributed evenly between week columns (space-between), so the
 * grid stretches from the left edge to the card's right padding.  Month
 * labels use the same column pitch, so they stay aligned at any width.
 */

const MONTHS = 6;
const ROW_LABEL_W = 28; // "tok" gutter (w-6 + gap-1)
const DAYS = 7;
const CELL_MIN = 4;
const CELL_CAP = 22;
// Gap scales with the cell so squares stay square-ish spaced at any width:
// solving cell*weeks + ratio*cell*(weeks-1) = gridW for cell.
const GAP_RATIO = 0.32;
const GAP_MAX = 14;

export function ActivityHeatmap({ days }: { days: DailyActivity[] }) {
  const cells = useMemo(() => buildGrid(days, MONTHS), [days]);
  const monthLabels = useMemo(() => buildMonthLabels(cells), [cells]);
  const maxTokens = Math.max(1, ...cells.map((c) => c.tokens));

  const [hover, setHover] = useState<Cell | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef({ x: 0, y: 0 });
  const areaRef = useRef<HTMLDivElement>(null);
  const [areaW, setAreaW] = useState(0);

  // Track the grid area so the cells can fill it at any card width.
  useLayoutEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const measure = () => setAreaW(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const weeks = Math.ceil(cells.length / DAYS);
  const gridW = Math.max(0, areaW - ROW_LABEL_W);
  // ONE gap value for both axes: cells and gaps stay identical horizontally
  // and vertically at every card width (no flat rectangles, no squeezed rows).
  const cell = Math.max(
    CELL_MIN,
    Math.min(Math.floor(gridW / (weeks + GAP_RATIO * (weeks - 1))), CELL_CAP),
  );
  const gap = Math.min((gridW - weeks * cell) / (weeks - 1), GAP_MAX);
  const pitch = cell + gap;
  const blockW = weeks * pitch - gap;
  const blockH = DAYS * cell + (DAYS - 1) * gap;

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
    const el = areaRef.current;
    if (el) {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    }
  };

  return (
    <section className="panel p-5 sm:p-6 h-full flex flex-col gap-4 min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Activity · last {MONTHS} months
        </h2>
        <div className="flex items-center gap-3 font-mono text-[10px] text-muted shrink-0">
          <span>less</span>
          <Swatch ratio={0.05} />
          <Swatch ratio={0.25} />
          <Swatch ratio={0.5} />
          <Swatch ratio={0.75} />
          <Swatch ratio={1} />
          <span>more</span>
        </div>
      </div>

      <div
        ref={areaRef}
        className="heat-scope relative flex-1 flex items-center min-h-[120px]"
        onMouseMove={onGridMouseMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* One block holds labels + columns so they always share the pitch */}
        <div className="relative" style={{ marginLeft: ROW_LABEL_W, width: blockW }}>
          {/* Month labels along the top, aligned to the same column pitch */}
          <div className="relative" style={{ height: 14, marginBottom: 6 }}>
            {monthLabels.map((m, i) => (
              <div
                key={i}
                className="absolute top-0 font-mono text-[10px] text-muted tracking-widest2 uppercase whitespace-nowrap"
                style={{ left: m.col * pitch }}
              >
                {m.label}
              </div>
            ))}
          </div>
          {/* Week columns — one uniform gap on both axes */}
          <div className="flex" style={{ gap, height: blockH }}>
            {weeksArr(weeks).map((_, wi) => (
              <div
                key={wi}
                className="flex flex-col shrink-0"
                style={{ gap, width: cell }}
              >
                {cells.slice(wi * DAYS, wi * DAYS + DAYS).map((c, di) => {
                  const v = c.tokens;
                  const ratio = maxTokens ? v / maxTokens : 0;
                  const empty = c.date === "";
                  return (
                    <div
                      key={di}
                      onMouseEnter={empty ? undefined : () => setHover(c)}
                      className={`heat-cell rounded-[2px] border border-ink-700 shrink-0 ${empty ? "opacity-0" : ""}`}
                      style={{
                        width: cell,
                        height: cell,
                        background: v
                          ? rgba("signal", ratio)
                          : "transparent",
                      }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="font-mono text-[11px] text-muted">
        Each column is one week, each cell one day —{" "}
        <span className="text-signal">tok</span> intensity = tokens processed that day.
      </p>

      {hover && (
        <div
          ref={tipRef}
          className="fixed left-0 top-0 z-50 pointer-events-none will-change-transform"
        >
          <HeatTooltip cell={hover} />
        </div>
      )}
    </section>
  );
}

function HeatTooltip({ cell }: { cell: Cell }) {
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
      <span className="font-mono text-[11px] text-signal">
        tok&nbsp;&nbsp;{cell.tokens.toLocaleString("en-US")}
      </span>
    </div>
  );
}

const WEEKDAY_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function Swatch({ ratio }: { ratio: number }) {
  return (
    <span
      className="inline-block w-3 h-3 rounded-sm"
      style={{ background: rgba("signal", Math.max(0.05, ratio)) }}
    />
  );
}

function weeksArr(n: number): number[] {
  return Array.from({ length: n }, (_, i) => i);
}

interface Cell {
  date: string;
  tokens: number;
  tasks: number;
}

function buildGrid(days: DailyActivity[], months: number): Cell[] {
  // Dense grid: one cell per day from the Sunday on/before the first day of
  // (months - 1) months ago, through today.  Keyed by the user's LOCAL date
  // string so the lookup matches what the Python parser wrote.  Padded with
  // empty cells to a whole number of weeks so every column has exactly 7
  // cells and the days line up horizontally.
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
  while (cells.length % DAYS !== 0) {
    cells.push({ date: "", tokens: 0, tasks: 0 });
  }
  return cells;
}

function buildMonthLabels(cells: Cell[]): { label: string; col: number }[] {
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const out: { label: string; col: number }[] = [];
  let prevMonth = -1;
  cells.forEach((c, i) => {
    if (c.date === "") return;
    const m = Number(c.date.slice(5, 7));
    if (m !== prevMonth) {
      out.push({ label: monthNames[m - 1] ?? "", col: Math.floor(i / DAYS) });
      prevMonth = m;
    }
  });
  // A stray day-or-two of a month can sit right next to the next month's
  // label (e.g. Aug 31 alone before a Sep-start grid) — drop the crowded
  // label and keep the fuller month's, like GitHub does.
  return out.filter(
    (l, i) => !(i < out.length - 1 && out[i + 1].col - l.col < 2),
  );
}

function rgba(channel: "signal" | "mint", ratio: number): string {
  const r = Math.max(0.05, Math.min(1, ratio));
  // signal: #FF7A3D, mint: #6FE3C2
  const base = channel === "signal" ? [255, 122, 61] : [111, 227, 194];
  return `rgba(${base[0]}, ${base[1]}, ${base[2]}, ${r.toFixed(3)})`;
}
