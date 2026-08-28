import type { ToolUsage } from "../types";

interface Props {
  toolUsage: ToolUsage;
}

export function ToolUsage({ toolUsage }: Props) {
  const max = Math.max(1, ...toolUsage.tools.map((t) => t.count));

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Tool usage
        </h2>
        <span className="eyebrow">
          {toolUsage.total} calls · {toolUsage.uniqueTools} tools
        </span>
      </div>

      <ul className="flex flex-col gap-2">
        {toolUsage.tools.slice(0, 12).map((t, idx) => {
          const pct = (t.count / max) * 100;
          return (
            <li key={t.name} className="flex items-center gap-3">
              <span className="font-mono text-[10px] text-muted w-6">
                {String(idx + 1).padStart(2, "0")}
              </span>
              <span className="font-mono text-sm text-fg w-32 truncate">{t.name}</span>
              <div className="relative flex-1 h-1.5 bg-ink-800 rounded-sm overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 bg-mint"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="font-mono text-xs text-fg tnum w-10 text-right">
                {t.count}
              </span>
            </li>
          );
        })}
      </ul>

      {Object.keys(toolUsage.byProject).length > 0 && (
        <details className="mt-2">
          <summary className="eyebrow cursor-pointer hover:text-fg transition-colors">
            by project ({Object.keys(toolUsage.byProject).length})
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
            {Object.entries(toolUsage.byProject).map(([proj, items]) => (
              <div key={proj} className="border border-ink-700 rounded p-3">
                <div className="eyebrow mb-2 truncate">{proj}</div>
                <ul className="flex flex-col gap-1">
                  {items.slice(0, 5).map((t) => (
                    <li
                      key={t.name}
                      className="flex items-center justify-between font-mono text-xs"
                    >
                      <span className="text-fg truncate">{t.name}</span>
                      <span className="text-muted">{t.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}