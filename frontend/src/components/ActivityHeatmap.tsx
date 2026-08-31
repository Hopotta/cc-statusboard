import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DailyActivity } from "../types";
import { localISODate, formatLongDateTimeEn } from "../utils/date";

/**
 * Contribution-style heatmap of daily token activity.  One row of week
 * columns (7 stacked day-cells each); color intensity scales with that
 * day's tokens relative to the max.
 *
 * The viewport always shows a 6-month window and its geometry is computed
 * from the card width, but the grid itself spans the full history: drag
 * (or scroll horizontally) to pan back in time.  The view stays pinned to
 * the most recent weeks by default.  Month labels use the same column
 * pitch, so they stay aligned at any width.
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
  const { cells, windowWeeks } = useMemo(
    () => buildScrollyGrid(days, MONTHS),
    [days],
  );
  const monthLabels = useMemo(() => buildMonthLabels(cells), [cells]);
  const maxTokens = Math.max(1, ...cells.map((c) => c.tokens));

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef({ x: 0, y: 0 });
  const areaRef = useRef<HTMLDivElement>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const [areaW, setAreaW] = useState(0);
  const hoverCell = hoverIdx !== null ? cells[hoverIdx] : null;

  // Subtle ripple: the hovered cell lifts a little and its 3×3
  // neighbourhood slightly less.  It is applied synchronously inside a
  // delegated mouseover listener — routing it through React state lagged
  // a frame behind the cursor, leaving the highlight stranded on the
  // previous cell.  Cells that stay affected keep their transform (no
  // reset-and-restart dip); the grid JSX below is memoized so the tooltip
  // re-render costs nothing.
  const cellRefs = useRef<Array<HTMLDivElement | null>>([]);
  const rippleRef = useRef<HTMLDivElement[]>([]);
  const blockRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = blockRef.current;
    if (!el) return;
    const onOver = (e: MouseEvent) => {
      const t = (e.target as Element).closest(".heat-cell");
      const idx = t ? Number((t as HTMLElement).dataset.i) : NaN;
      const next: HTMLDivElement[] = [];
      if (!Number.isNaN(idx)) {
        const hr = idx % DAYS;
        const hw = Math.floor(idx / DAYS);
        for (let w = Math.max(0, hw - 1); w <= hw + 1; w++) {
          for (let r = Math.max(0, hr - 1); r <= Math.min(DAYS - 1, hr + 1); r++) {
            const c = cellRefs.current[w * DAYS + r];
            if (!c || c.classList.contains("opacity-0")) continue;
            const tf = `scale(${w === hw && r === hr ? 1.3 : 1.08})`;
            if (c.style.transform !== tf) c.style.transform = tf;
            next.push(c);
          }
        }
        setHoverIdx(idx);
      }
      for (const old of rippleRef.current) {
        if (!next.includes(old)) old.style.transform = "";
      }
      rippleRef.current = next;
    };
    const onLeave = () => {
      for (const old of rippleRef.current) old.style.transform = "";
      rippleRef.current = [];
    };
    el.addEventListener("mouseover", onOver);
    el.addEventListener("mouseleave", onLeave);
    return () => {
      el.removeEventListener("mouseover", onOver);
      el.removeEventListener("mouseleave", onLeave);
    };
  }, []);

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
  // Geometry is sized so a 6-month window fills the viewport exactly; the
  // full-history block simply extends beyond it to the left.
  const cell = Math.max(
    CELL_MIN,
    Math.min(
      Math.floor(gridW / (windowWeeks + GAP_RATIO * (windowWeeks - 1))),
      CELL_CAP,
    ),
  );
  const gap = Math.min((gridW - windowWeeks * cell) / (windowWeeks - 1), GAP_MAX);
  const pitch = cell + gap;
  const blockW = weeks * pitch - gap;
  const blockH = DAYS * cell + (DAYS - 1) * gap;

  // Memoized so a hover (hoverIdx state change) doesn't re-diff ~340
  // cells — the element reference stays identical and React skips the
  // whole subtree.
  const gridBody = useMemo(
    () => (
      <>
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
                const idx = wi * DAYS + di;
                return (
                  <div
                    key={di}
                    ref={(el) => {
                      cellRefs.current[idx] = el;
                    }}
                    data-i={empty ? undefined : idx}
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
      </>
    ),
    [cells, monthLabels, maxTokens, cell, gap, pitch, blockH, weeks],
  );

  // Drag-to-pan: mousedown + move scrolls the history horizontally.
  const dragRef = useRef<{ x: number; left: number } | null>(null);
  const onDragStart = (e: React.MouseEvent) => {
    const el = areaRef.current;
    if (!el) return;
    dragRef.current = { x: e.clientX, left: el.scrollLeft };
  };
  const endDrag = () => {
    dragRef.current = null;
  };

  // Release outside the grid must still end the drag.
  useEffect(() => {
    const up = () => endDrag();
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, []);

  // Touchpad: when the cursor is over the grid, scrolling pans the history
  // instead of the page.  Needs a native non-passive listener to
  // preventDefault; hands back to the page at either end of the history
  // (or when the grid fits the viewport and there is nothing to pan).
  useEffect(() => {
    const scope = scopeRef.current;
    if (!scope) return;
    const onWheel = (e: WheelEvent) => {
      const el = areaRef.current;
      if (!el) return;
      const max = el.scrollWidth - el.clientWidth;
      if (max <= 0) return;
      const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      const atStart = el.scrollLeft <= 0 && delta < 0;
      const atEnd = el.scrollLeft >= max && delta > 0;
      if (atStart || atEnd) return;
      e.preventDefault();
      el.scrollLeft = Math.max(0, Math.min(max, el.scrollLeft + delta));
    };
    scope.addEventListener("wheel", onWheel, { passive: false });
    return () => scope.removeEventListener("wheel", onWheel);
  }, []);

  // Keep the view pinned to the most recent weeks (also after the first
  // width measurement, when the block reaches its real size).
  useLayoutEffect(() => {
    const el = areaRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [cells.length, areaW]);

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
    if (!hoverCell) return;
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
  }, [hoverCell]);

  const onGridMouseMove = (e: React.MouseEvent) => {
    cursorRef.current = { x: e.clientX, y: e.clientY };
    if (dragRef.current) {
      const el = areaRef.current;
      if (el) el.scrollLeft = dragRef.current.left - (e.clientX - dragRef.current.x);
    }
    if (hoverCell) placeTip();

    // Cursor-following spotlight, via CSS vars so cells never re-render.
    // Vars live on the outer (non-scrolling) scope so the ::after overlay
    // stays fixed to the viewport while the grid pans underneath.
    const el = scopeRef.current;
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
          Activity
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
        ref={scopeRef}
        className="heat-scope relative flex-1 flex items-center min-h-[150px]"
        onMouseMove={onGridMouseMove}
        onMouseLeave={() => {
          endDrag();
          setHoverIdx(null);
        }}
      >
        <div
          ref={areaRef}
          className="flex h-full w-full items-center overflow-x-auto select-none cursor-grab active:cursor-grabbing [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          onMouseDown={onDragStart}
          onMouseUp={endDrag}
        >
        {/* One block holds labels + columns so they always share the pitch */}
        <div
          ref={blockRef}
          className="relative shrink-0"
          style={{ marginLeft: ROW_LABEL_W, width: blockW }}
        >
          {gridBody}
        </div>
        </div>
      </div>

      {hoverCell && (
        <div
          ref={tipRef}
          className="fixed left-0 top-0 z-50 pointer-events-none will-change-transform"
        >
          <HeatTooltip cell={hoverCell} />
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

function buildScrollyGrid(
  days: DailyActivity[],
  windowMonths: number,
): { cells: Cell[]; windowWeeks: number } {
  // The viewport geometry is sized for a `windowMonths`-month window (same
  // as the old fixed grid), while `cells` spans the full history so the
  // user can pan back in time.
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const winStart = new Date(
    today.getFullYear(),
    today.getMonth() - (windowMonths - 1),
    1,
  );
  while (winStart.getDay() !== 0) {
    winStart.setDate(winStart.getDate() - 1);
  }
  const windowWeeks = cellsBetween(days, winStart, today).length / DAYS;

  let start = winStart;
  if (days.length) {
    const earliest = days.reduce((a, d) => (d.date < a ? d.date : a), days[0].date);
    const e = new Date(
      Number(earliest.slice(0, 4)),
      Number(earliest.slice(5, 7)) - 1,
      1,
    );
    // Lead in with six empty months before the earliest data so the
    // history can always be panned through.
    e.setMonth(e.getMonth() - 6);
    while (e.getDay() !== 0) {
      e.setDate(e.getDate() - 1);
    }
    if (e < start) start = e;
  }
  return { cells: cellsBetween(days, start, today), windowWeeks };
}

function cellsBetween(days: DailyActivity[], start: Date, today: Date): Cell[] {
  // Dense grid: one cell per day from `start` (a Sunday) through today.
  // Keyed by the user's LOCAL date string so the lookup matches what the
  // Python parser wrote.  Padded with empty cells to a whole number of
  // weeks so every column has exactly 7 cells and the days line up
  // horizontally.
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
