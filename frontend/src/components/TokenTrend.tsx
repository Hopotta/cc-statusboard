import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyActivity } from "../types";
import { formatTokens } from "../utils/format";

export function TokenTrend({ days }: { days: DailyActivity[] }) {
  // If very few days, pad by repeating the same range so the chart isn't squished.
  const data = days.map((d) => ({
    date: d.date.slice(5), // MM-DD
    fullDate: d.date,
    tokens: d.tokens,
    input: d.inputTokens,
    output: d.outputTokens,
    cache: d.cacheReadTokens + d.cacheCreationTokens,
    cost: d.cost,
    tasks: d.tasks,
  }));

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Token throughput
        </h2>
        <span className="eyebrow">per day</span>
      </div>
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
            <Area
              type="monotone"
              dataKey="tokens"
              name="tokens"
              stroke="#FF7A3D"
              strokeWidth={1.5}
              fill="url(#tokGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

const tooltipStyle: React.CSSProperties = {
  background: "#13161B",
  border: "1px solid #232831",
  borderRadius: 6,
  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
};