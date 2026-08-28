import type { ModelStat } from "../types";
import { formatTokens, formatPct, formatUSD } from "../utils/format";

/**
 * Horizontal bar list of model usage.  Uses Recharts' BarChart on its side,
 * but because we're constrained to a compact list we hand-render the bars
 * for tighter typography control.
 */
export function ModelDistribution({ models }: { models: ModelStat[] }) {
  if (!models.length) {
    return (
      <section className="panel p-5 sm:p-6">
        <h2 className="eyebrow mb-3">Models</h2>
        <p className="font-mono text-sm text-muted">No model data yet.</p>
      </section>
    );
  }
  const max = Math.max(...models.map((m) => m.totalTokens));

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Models
        </h2>
        <span className="eyebrow">by tokens</span>
      </div>
      <ul className="flex flex-col gap-3">
        {models.map((m, idx) => {
          const pct = (m.totalTokens / max) * 100;
          const share = m.sharePct;
          return (
            <li key={m.modelName} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-mono text-[10px] text-muted w-6">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <span className="font-mono text-sm text-fg truncate">
                    {m.modelName}
                  </span>
                </div>
                <div className="flex items-baseline gap-3 shrink-0">
                  <span className="font-mono text-[11px] text-muted">
                    {formatUSD(m.cost)}
                  </span>
                  <span className="font-mono text-sm text-fg tnum w-16 text-right">
                    {formatTokens(m.totalTokens, 2)}
                  </span>
                  <span className="font-mono text-sm text-signal tnum w-12 text-right">
                    {formatPct(share)}
                  </span>
                </div>
              </div>
              <div className="relative h-1.5 bg-ink-800 rounded-sm overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 bg-signal"
                  style={{ width: `${pct}%` }}
                />
                {/* Tick at 50%, 100% */}
                <div className="absolute inset-y-0 left-1/2 w-px bg-ink-700" />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}