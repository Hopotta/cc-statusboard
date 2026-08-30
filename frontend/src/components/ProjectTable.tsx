import { useMemo, useState } from "react";
import type { ProjectStat } from "../types";
import { formatSeconds, formatTokens, formatUSD } from "../utils/format";

type SortKey = "tokens" | "tasks" | "time" | "spend";

const SORT_DEFS: Array<{
  key: SortKey;
  label: string;
  get: (p: ProjectStat) => number;
}> = [
  { key: "tokens", label: "Tokens", get: (p) => p.tokens },
  { key: "tasks", label: "Tasks", get: (p) => p.tasks },
  { key: "time", label: "Time", get: (p) => p.activeSeconds },
  { key: "spend", label: "Spend", get: (p) => p.cost },
];

/**
 * Project statusboard: a typographic table of projects.  Click a metric
 * column header to sort by it (click again to flip direction).  Tabular-nums
 * and a hairline rule between rows.
 */
export function ProjectTable({ projects }: { projects: ProjectStat[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("tokens");
  const [desc, setDesc] = useState(true);

  const sorted = useMemo(() => {
    const def = SORT_DEFS.find((d) => d.key === sortKey)!;
    return [...projects].sort((a, b) => {
      const delta = def.get(a) - def.get(b);
      return (desc ? -delta : delta) || a.project.localeCompare(b.project);
    });
  }, [projects, sortKey, desc]);

  const maxTasks = Math.max(1, ...projects.map((p) => p.tasks));

  if (!projects.length) {
    return (
      <section className="panel p-5 sm:p-6">
        <h2 className="eyebrow mb-3">Projects</h2>
        <p className="font-mono text-sm text-muted">No project activity yet.</p>
      </section>
    );
  }

  const pickSort = (key: SortKey) => {
    if (key === sortKey) {
      setDesc((v) => !v);
    } else {
      setSortKey(key);
      setDesc(true);
    }
  };

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Project statusboard
        </h2>
        <span className="eyebrow">{projects.length} project{projects.length === 1 ? "" : "s"}</span>
      </div>

      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-ink-700">
              <Th>Project</Th>
              {SORT_DEFS.map(({ key, label }) => (
                <Th
                  key={key}
                  className="text-right cursor-pointer select-none hover:text-signal transition-colors"
                  onClick={() => pickSort(key)}
                  mark={sortKey === key ? (desc ? "↓" : "↑") : ""}
                >
                  {label}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, idx) => (
              <tr
                key={`${p.project}-${idx}`}
                className="border-b border-ink-700/60 hover:bg-ink-800/40 transition-colors"
              >
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-[10px] text-muted w-6">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <div className="flex flex-col min-w-0">
                      <span className="font-mono text-sm text-fg truncate">
                        {p.project}
                      </span>
                      {p.projectPath && (
                        <span className="font-mono text-[10px] text-muted truncate max-w-xs">
                          {p.projectPath}
                        </span>
                      )}
                    </div>
                  </div>
                </td>
                <Td className="text-right">{formatTokens(p.tokens, 2)}</Td>
                <Td className="text-right">
                  <div className="flex items-center justify-end gap-3">
                    <div className="hidden sm:block w-24 h-1 bg-ink-800 rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-mint"
                        style={{ width: `${(p.tasks / maxTasks) * 100}%` }}
                      />
                    </div>
                    <span className="text-fg w-10">{p.tasks}</span>
                  </div>
                </Td>
                <Td className="text-right">{formatSeconds(p.activeSeconds)}</Td>
                <Td className="text-right text-muted">{formatUSD(p.cost)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Th({
  children,
  className = "",
  mark = "",
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  mark?: string;
  onClick?: () => void;
}) {
  return (
    <th
      className={`eyebrow py-3 px-4 font-normal ${className}`}
      scope="col"
      onClick={onClick}
    >
      {children}
      {mark && (
        <span className="ml-1 text-signal font-mono" aria-hidden>
          {mark}
        </span>
      )}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`py-3 px-4 font-mono text-sm tnum ${className}`}>
      {children}
    </td>
  );
}
