import type { PromptCategory } from "../types";

/**
 * Prompt categories — donut-ish bar chart of how user's prompts split across
 * categories (debug / refactor / feature / etc).  Implemented with stacked
 * bars so it reads at a glance and feels instrument-like.
 */
export function PromptCategories({
  categories,
  total,
}: {
  categories: PromptCategory[];
  total: number;
}) {
  const ordered = [...categories].sort((a, b) => b.count - a.count);
  const max = Math.max(1, ...ordered.map((c) => c.count));
  const other = categories.find((c) => c.slug === "other");

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Prompt categories
        </h2>
        <span className="eyebrow">{total} prompts</span>
      </div>

      {other && other.sharePct > 40 && (
        <p className="font-mono text-[11px] text-sun border border-sun/30 bg-sun/5 rounded px-3 py-2">
          {other.sharePct.toFixed(0)}% of prompts match no heuristic category —
          read the split as a rough hint, not ground truth.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {ordered.map((c, idx) => (
          <div key={c.slug} className="flex items-center gap-2">
            <span className="hidden xl:block font-mono text-[10px] text-muted w-5 shrink-0">
              {String(idx + 1).padStart(2, "0")}
            </span>
            <span className="font-mono text-sm text-fg w-36 xl:w-40 shrink-0 truncate">
              {c.label}
            </span>
            <div className="relative flex-1 min-w-4 h-1.5 bg-ink-800 rounded-sm overflow-hidden">
              <div
                className="absolute inset-y-0 left-0"
                style={{
                  width: `${(c.count / max) * 100}%`,
                  background: barColor(idx),
                }}
              />
            </div>
            <span className="font-mono text-xs text-fg tnum w-8 text-right shrink-0">
              {c.count}
            </span>
            <span className="font-mono text-[11px] text-muted tnum w-10 text-right shrink-0">
              {c.sharePct.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>

      {total === 0 && (
        <p className="font-mono text-xs text-muted">
          No categorized prompts yet — usage will appear after a few sessions.
        </p>
      )}
    </section>
  );
}

function barColor(idx: number): string {
  const palette = ["#FF7A3D", "#FFB454", "#6FE3C2", "#8A93A1", "#FF7A3D", "#6FE3C2"];
  return palette[idx % palette.length];
}