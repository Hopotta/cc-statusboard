import { ACCENT_CLASS, type Accent, type ModelEfficiency } from "../types";
import { formatPct, formatTokens, formatUSD } from "../utils/format";

/**
 * Model efficiency panel: tokens-per-task, cost-per-task, cache hit rate,
 * output/input ratio.  Shows you whether you're getting good mileage from
 * the model.
 */
export function ModelEfficiency({ efficiency }: { efficiency: ModelEfficiency }) {
  const cacheTotal = efficiency.cacheReadTokens + efficiency.cacheCreationTokens;
  const cacheShare =
    cacheTotal > 0 ? efficiency.cacheReadTokens / cacheTotal : 0;

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Model efficiency
        </h2>
        <span className="eyebrow">per task</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-4">
        <Stat label="Tokens / task" value={formatTokens(efficiency.tokensPerTask, 1)} />
        <Stat label="Cost / task" value={formatUSD(efficiency.costPerTask)} />
        <Stat
          label="Cache hit rate"
          value={formatPct(cacheShare * 100, 1)}
          accent="mint"
        />
        <Stat
          label="Output ratio"
          value={formatPct(efficiency.outputRatio * 100, 2)}
          accent="sun"
        />
      </div>

      <div className="mt-2 flex flex-col gap-2">
        <span className="eyebrow">Cache breakdown</span>
        <div className="flex h-3 rounded-sm overflow-hidden border border-ink-700">
          <div
            className="bg-mint"
            style={{ width: `${cacheShare * 100}%` }}
            title={`Cache read: ${formatTokens(efficiency.cacheReadTokens, 2)}`}
          />
          <div
            className="bg-sun"
            style={{ width: `${(1 - cacheShare) * 100}%` }}
            title={`Cache creation: ${formatTokens(efficiency.cacheCreationTokens, 2)}`}
          />
        </div>
        <div className="flex justify-between font-mono text-[10px] text-muted">
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-mint mr-1 align-middle" />
            read {formatTokens(efficiency.cacheReadTokens, 2)}
          </span>
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-sun mr-1 align-middle" />
            created {formatTokens(efficiency.cacheCreationTokens, 2)}
          </span>
        </div>
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: Accent;
}) {
  const cls = accent ? ACCENT_CLASS[accent] : "text-fg";
  return (
    <div className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      <span className={`readout text-2xl ${cls}`}>{value}</span>
    </div>
  );
}