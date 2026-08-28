import type { ProjectStat } from "../types";
import { formatSeconds, formatTokens, formatUSD } from "../utils/format";

/**
 * Project statusboard: a typographic table of projects with token / task / time
 * columns.  Sorted by tasks desc.  This is the section that benefits most from
 * tabular-nums and a hairline rule between rows.
 */
export function ProjectTable({ projects }: { projects: ProjectStat[] }) {
  if (!projects.length) {
    return (
      <section className="panel p-5 sm:p-6">
        <h2 className="eyebrow mb-3">Projects</h2>
        <p className="font-mono text-sm text-muted">No project activity yet.</p>
      </section>
    );
  }

  const maxTasks = Math.max(...projects.map((p) => p.tasks));

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
              <Th className="text-right">Tokens</Th>
              <Th className="text-right">Tasks</Th>
              <Th className="text-right">Time</Th>
              <Th className="text-right">Spend</Th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p, idx) => (
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
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`eyebrow py-3 px-4 font-normal ${className}`}
      scope="col"
    >
      {children}
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