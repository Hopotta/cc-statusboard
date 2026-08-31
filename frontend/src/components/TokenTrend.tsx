import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyActivity } from "../types";
import { formatTokens } from "../utils/format";
import { localISODate, EN_MONTHS_LONG } from "../utils/date";

type RangeKey = "all" | "1m" | "3m" | "6m" | "1y" | "custom";

const RANGE_MONTHS: Partial<Record<RangeKey, number>> = {
  "1m": 1,
  "3m": 3,
  "6m": 6,
  "1y": 12,
};

const RANGE_LABELS: Array<{ key: RangeKey; label: string }> = [
  { key: "all", label: "all" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "custom", label: "custom" },
];

export function TokenTrend({ days }: { days: DailyActivity[] }) {
  const [range, setRange] = useState<RangeKey>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [openPicker, setOpenPicker] = useState<"from" | "to" | null>(null);
  const [mode, setMode] = useState<"total" | "stacked">("total");

  const pickRange = (key: RangeKey) => {
    setRange(key);
    // Jump straight into picking: opening the calendar for the user.
    setOpenPicker(key === "custom" ? "from" : null);
  };

  // Close on any outside mousedown.  Clicks on either date trigger stay
  // untouched, so pressing the other date swaps pickers in one click.
  useEffect(() => {
    if (!openPicker) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Element | null;
      if (t && t.closest("[data-datepicker]")) return;
      setOpenPicker(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [openPicker]);

  const filtered = useMemo(() => {
    if (range === "all") return days;
    if (range === "custom") {
      if (!from || !to) return [];
      return days.filter((d) => d.date >= from && d.date <= to);
    }
    const months = RANGE_MONTHS[range]!;
    const cutoff = new Date();
    cutoff.setDate(1);
    cutoff.setMonth(cutoff.getMonth() - months + 1);
    const iso = localISODate(cutoff);
    return days.filter((d) => d.date >= iso);
  }, [days, range, from, to]);

  const data = useMemo(
    () =>
      filtered.map((d) => ({
        date: d.date.slice(5), // MM-DD
        fullDate: d.date,
        tokens: d.tokens,
        input: d.inputTokens,
        output: d.outputTokens,
        cacheRead: d.cacheReadTokens,
        cacheCreation: d.cacheCreationTokens,
        cost: d.cost,
        tasks: d.tasks,
      })),
    [filtered],
  );

  // Outlier days: tokens beyond mean + 2σ of the selected range.
  const anomalies = useMemo(() => {
    if (data.length < 8) return [];
    const mean = data.reduce((a, d) => a + d.tokens, 0) / data.length;
    const sd = Math.sqrt(
      data.reduce((a, d) => a + (d.tokens - mean) ** 2, 0) / data.length,
    );
    const cutoff = mean + 2 * sd;
    return data.filter((d) => d.tokens > cutoff);
  }, [data]);

  const btn =
    "font-mono text-[11px] px-2.5 py-1 rounded border transition-colors";
  const btnOn = "text-signal border-signal/50";
  const btnOff =
    "text-muted border-ink-700 hover:border-signal/40 hover:text-signal";

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Token throughput
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {RANGE_LABELS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => pickRange(key)}
              className={`${btn} ${range === key ? btnOn : btnOff}`}
            >
              {label}
            </button>
          ))}
          <span className="flex items-center gap-2 ml-2">
            {(["total", "stacked"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`${btn} ${mode === m ? btnOn : btnOff}`}
              >
                {m}
              </button>
            ))}
            {anomalies.length > 0 && (
              <span className="font-mono text-[10px] text-muted">
                ◉ outlier &gt; μ+2σ
              </span>
            )}
          </span>
          {range === "custom" && (
            <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted">
              <DateField
                label="start date"
                value={from}
                onChange={setFrom}
                open={openPicker === "from"}
                onToggle={() => setOpenPicker(openPicker === "from" ? null : "from")}
              />
              →
              <DateField
                label="end date"
                value={to}
                onChange={setTo}
                open={openPicker === "to"}
                onToggle={() => setOpenPicker(openPicker === "to" ? null : "to")}
              />
            </span>
          )}
        </div>
      </div>
      {range === "custom" && from && to && from > to ? (
        <p className="font-mono text-sm text-muted h-72 flex items-center justify-center">
          Start date is after end date — adjust the range.
        </p>
      ) : data.length === 0 ? (
        <p className="font-mono text-sm text-muted h-72 flex items-center justify-center">
          {range === "custom" && (!from || !to)
            ? "Pick a start and end date to chart the range."
            : "No activity in this range."}
        </p>
      ) : (
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 6, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="tokGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FF7A3D" stopOpacity={0.55} />
                <stop offset="100%" stopColor="#FF7A3D" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="#232831" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#8A93A1"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              tick={{ fontFamily: "JetBrains Mono, monospace" }}
            />
            <YAxis
              stroke="#8A93A1"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              width={42}
              tickFormatter={(v) => formatTokens(v as number, 1)}
              tick={{ fontFamily: "JetBrains Mono, monospace" }}
            />
            <Tooltip
              cursor={{ stroke: "#FF7A3D", strokeOpacity: 0.4, strokeDasharray: "3 3" }}
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#8A93A1", fontSize: 11, fontFamily: "JetBrains Mono" }}
              itemStyle={{ color: "#E6E9EF", fontFamily: "JetBrains Mono", fontSize: 12 }}
              formatter={(value: number, name: string) => [
                formatTokens(value, 2),
                name,
              ]}
              labelFormatter={(_, payload) =>
                payload?.[0]?.payload?.fullDate ?? ""
              }
            />
            {/* Always mounted so toggling modes doesn't resize the plot area
                and shift the x-axis; invisible in total view. */}
            <Legend
              wrapperStyle={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "#8A93A1",
                paddingTop: 10,
                visibility: mode === "total" ? "hidden" : "visible",
              }}
              iconType="plainrect"
              iconSize={8}
            />
            {mode === "stacked" ? (
              <>
                <Area type="monotone" dataKey="cacheRead" name="cache read" stackId="1"
                  stroke="#6FE3C2" fill="#6FE3C2" fillOpacity={0.3} strokeWidth={1} />
                <Area type="monotone" dataKey="input" name="input" stackId="1"
                  stroke="#8A93A1" fill="#8A93A1" fillOpacity={0.25} strokeWidth={1} />
                <Area type="monotone" dataKey="cacheCreation" name="cache creation" stackId="1"
                  stroke="#FFB454" fill="#FFB454" fillOpacity={0.3} strokeWidth={1} />
                <Area type="monotone" dataKey="output" name="output" stackId="1"
                  stroke="#FF7A3D" fill="#FF7A3D" fillOpacity={0.35} strokeWidth={1} />
              </>
            ) : (
              <Area
                type="monotone"
                dataKey="tokens"
                name="tokens"
                stroke="#FF7A3D"
                strokeWidth={1.5}
                fill="url(#tokGradient)"
              />
            )}
            {anomalies.map((d) => (
              <ReferenceDot
                key={d.fullDate}
                x={d.date}
                y={d.tokens}
                r={4}
                fill="none"
                stroke="#FF7A3D"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

const tooltipStyle: React.CSSProperties = {
  background: "#13161B",
  border: "1px solid #232831",
  borderRadius: 6,
  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
};

/* ------------------------------------------------------------------ */
/* Custom date picker.                                                 */
/*                                                                     */
/* Native <input type="date"> renders its format AND its calendar      */
/* popup in the *browser's* UI locale (zh-CN Chrome shows yyyy/mm/日), */
/* regardless of the page language.  This mini calendar keeps the      */
/* dashboard fully English and matches the terminal styling.           */
/* ------------------------------------------------------------------ */

function isoDate(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function DateField({
  label,
  value,
  onChange,
  open,
  onToggle,
}: {
  label: string;
  value: string;
  onChange: (iso: string) => void;
  open: boolean;
  onToggle: () => void;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [flipX, setFlipX] = useState(false);
  const [flipY, setFlipY] = useState(false);

  // Flip the popover toward the page interior when the trigger sits near
  // a viewport edge (narrow windows, bottom-docked panels).
  useLayoutEffect(() => {
    if (!open || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setFlipX(r.left + 240 > window.innerWidth);
    setFlipY(r.bottom + 280 > window.innerHeight && r.top > 300);
  }, [open]);

  return (
    <span ref={ref} data-datepicker className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-label={label}
        title={label}
        className={`font-mono text-[11px] px-2.5 py-1 rounded border bg-ink-900 transition-colors ${
          open
            ? "text-signal border-signal/50"
            : value
              ? "text-fg border-ink-700 hover:border-signal/40"
              : "text-muted border-ink-700 hover:border-signal/40 hover:text-signal"
        }`}
      >
        {value || "yyyy-mm-dd"}
      </button>
      {open && (
        <MiniCalendar
          value={value}
          onChange={onChange}
          onClose={onToggle}
          flipX={flipX}
          flipY={flipY}
        />
      )}
    </span>
  );
}

const WEEKDAY_HEAD = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function MiniCalendar({
  value,
  onChange,
  onClose,
  flipX,
  flipY,
}: {
  value: string;
  onChange: (iso: string) => void;
  onClose: () => void;
  flipX: boolean;
  flipY: boolean;
}) {
  const initial = value
    ? new Date(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, 1)
    : new Date();
  const [view, setView] = useState(
    () => new Date(initial.getFullYear(), initial.getMonth(), 1),
  );
  const [yearOpen, setYearOpen] = useState(false);

  const y = view.getFullYear();
  const m = view.getMonth();
  const firstWeekday = new Date(y, m, 1).getDay();
  const daysInMonth = new Date(y, m + 1, 0).getDate();

  const move = (delta: number) =>
    setView(new Date(view.getFullYear(), view.getMonth() + delta, 1));

  const yearBtn =
    "font-mono text-[11px] text-fg tracking-widest2 uppercase hover:text-signal transition-colors";
  const years: number[] = [];
  {
    const cy = new Date().getFullYear();
    for (let yy = cy; yy >= cy - 11; yy--) years.push(yy);
  }

  const dayBtn =
    "w-7 h-7 flex items-center justify-center font-mono text-[10px] rounded-sm transition-colors";

  return (
    <div
      className={`absolute z-50 panel p-3 w-[232px] flex flex-col gap-2 shadow-[0_8px_24px_rgba(0,0,0,0.5)] ${
        flipX ? "right-0" : "left-0"
      } ${flipY ? "bottom-full mb-1" : "top-full mt-1"}`}
    >
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous month"
          onClick={() => move(-1)}
          className="font-mono text-xs text-muted hover:text-signal px-1"
        >
          ‹
        </button>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[11px] text-fg tracking-widest2 uppercase">
            {EN_MONTHS_LONG[m]}
          </span>
          <span className="relative">
            <button
              type="button"
              aria-label="Pick year"
              onClick={() => setYearOpen((v) => !v)}
              className={`${yearBtn} ${yearOpen ? "text-signal" : ""}`}
            >
              {y} ▾
            </button>
            {yearOpen && (
              <div className="absolute right-0 top-full mt-1 z-10 panel py-1 w-[72px] max-h-44 overflow-y-auto shadow-[0_8px_24px_rgba(0,0,0,0.5)]">
                {years.map((yy) => (
                  <button
                    key={yy}
                    type="button"
                    onClick={() => {
                      setView(new Date(yy, view.getMonth(), 1));
                      setYearOpen(false);
                    }}
                    className={`w-full px-3 py-1 text-right font-mono text-[11px] transition-colors ${
                      yy === y
                        ? "text-signal"
                        : "text-muted hover:text-fg hover:bg-ink-800"
                    }`}
                  >
                    {yy}
                  </button>
                ))}
              </div>
            )}
          </span>
        </div>
        <button
          type="button"
          aria-label="Next month"
          onClick={() => move(1)}
          className="font-mono text-xs text-muted hover:text-signal px-1"
        >
          ›
        </button>
      </div>

      <div className="grid grid-cols-7">
        {WEEKDAY_HEAD.map((w) => (
          <span
            key={w}
            className="h-5 flex items-center justify-center font-mono text-[9px] text-muted uppercase"
          >
            {w}
          </span>
        ))}
        {Array.from({ length: firstWeekday }).map((_, i) => (
          <span key={`pad-${i}`} />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((d) => {
          const iso = isoDate(y, m, d);
          const selected = iso === value;
          return (
            <button
              key={d}
              type="button"
              onClick={() => {
                onChange(iso);
                onClose();
              }}
              className={`${dayBtn} ${
                selected
                  ? "bg-signal text-ink-950 font-semibold"
                  : "text-fg hover:bg-ink-800"
              }`}
            >
              {d}
            </button>
          );
        })}
      </div>
    </div>
  );
}