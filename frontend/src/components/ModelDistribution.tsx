import { useMemo, useState } from "react";
import type { ModelStat } from "../types";
import { formatTokens, formatPct, formatUSD } from "../utils/format";

/**
 * Horizontal bar list of model usage.  Hand-rendered bars for tighter
 * typography control.  Sortable by model (token share, default) or grouped
 * by provider (OpenAI, DeepSeek, …).
 */
export function ModelDistribution({ models }: { models: ModelStat[] }) {
  const [sort, setSort] = useState<"model" | "provider">("model");

  const providerGroups = useMemo(() => groupByProvider(models), [models]);

  const toggle =
    "font-mono text-[11px] px-2.5 py-1 rounded border transition-colors";

  let body: React.ReactNode;
  if (!models.length) {
    body = <p className="font-mono text-sm text-muted">No model data yet.</p>;
  } else if (sort === "model") {
    const max = Math.max(...models.map((m) => m.totalTokens));
    body = (
      <ul className="grid md:grid-cols-2 md:gap-x-10 gap-y-3">
        {models.map((m, idx) => (
          <li key={m.modelName} className="flex flex-col gap-1.5 min-w-0">
            <ModelRow
              rank={String(idx + 1).padStart(2, "0")}
              name={m.modelName}
              note={providerOf(m.modelName)}
              pct={(m.totalTokens / max) * 100}
              stat={m}
            />
          </li>
        ))}
      </ul>
    );
  } else {
    const max = Math.max(...providerGroups.map((g) => g.total));
    body = (
      <ul className="flex flex-col gap-3">
        {providerGroups.map((g, idx) => (
          <li key={g.provider} className="flex flex-col gap-1.5 min-w-0">
            <ModelRow
              rank={String(idx + 1).padStart(2, "0")}
              name={g.provider}
              note={`${g.models.length} model${g.models.length === 1 ? "" : "s"}`}
              pct={(g.total / max) * 100}
              stat={{
                totalTokens: g.total,
                cost: g.cost,
                sharePct: g.share,
              }}
            />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Models
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSort("model")}
            className={`${toggle} ${
              sort === "model"
                ? "text-signal border-signal/50"
                : "text-muted border-ink-700 hover:border-signal/40 hover:text-signal"
            }`}
          >
            by model
          </button>
          <button
            type="button"
            onClick={() => setSort("provider")}
            className={`${toggle} ${
              sort === "provider"
                ? "text-signal border-signal/50"
                : "text-muted border-ink-700 hover:border-signal/40 hover:text-signal"
            }`}
          >
            by provider
          </button>
        </div>
      </div>
      {body}
    </section>
  );
}

function ModelRow({
  rank,
  name,
  note,
  pct,
  stat,
}: {
  rank?: string;
  name: string;
  note?: string;
  pct: number;
  stat: Pick<ModelStat, "totalTokens" | "cost" | "sharePct">;
}) {
  return (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2 min-w-0">
          {rank && (
            <span className="font-mono text-[10px] text-muted w-6 shrink-0">
              {rank}
            </span>
          )}
          <span className="font-mono text-sm text-fg truncate">{name}</span>
          {note && (
            <span className="font-mono text-[9px] uppercase tracking-widest2 text-muted/80 shrink-0">
              {note}
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-3 shrink-0">
          <span className="font-mono text-[11px] text-muted">{formatUSD(stat.cost)}</span>
          <span className="font-mono text-sm text-fg tnum w-16 text-right">
            {formatTokens(stat.totalTokens, 2)}
          </span>
          <span className="font-mono text-sm text-signal tnum w-12 text-right">
            {formatPct(stat.sharePct)}
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
    </>
  );
}

interface ProviderGroup {
  provider: string;
  models: ModelStat[];
  total: number;
  cost: number;
  share: number;
}

function groupByProvider(models: ModelStat[]): ProviderGroup[] {
  const map = new Map<string, ModelStat[]>();
  let grandTotal = 0;
  for (const m of models) {
    const p = providerOf(m.modelName);
    if (!map.has(p)) map.set(p, []);
    map.get(p)!.push(m);
    grandTotal += m.totalTokens;
  }
  const groups = [...map.entries()].map(([provider, ms]) => ({
    provider,
    // Tokens-descending inside each provider group.
    models: [...ms].sort((a, b) => b.totalTokens - a.totalTokens),
    total: ms.reduce((s, m) => s + m.totalTokens, 0),
    cost: ms.reduce((s, m) => s + m.cost, 0),
    share: grandTotal ? (ms.reduce((s, m) => s + m.totalTokens, 0) / grandTotal) * 100 : 0,
  }));
  // Biggest providers first.
  return groups.sort((a, b) => b.total - a.total);
}

const PROVIDER_RULES: Array<[RegExp, string]> = [
  [/claude|anthropic/i, "Anthropic"],
  [/gpt|^o\d|codex|openai/i, "OpenAI"],
  [/deepseek/i, "DeepSeek"],
  [/minimax/i, "MiniMax"],
  [/glm|zhipu|chatglm/i, "Zhipu"],
  [/gemini|palm|bard/i, "Google"],
  [/qwen|qwq/i, "Alibaba"],
  [/mistral|mixtral/i, "Mistral"],
  [/llama|meta/i, "Meta"],
];

function providerOf(modelName: string): string {
  for (const [re, name] of PROVIDER_RULES) {
    if (re.test(modelName)) return name;
  }
  return "Other";
}
