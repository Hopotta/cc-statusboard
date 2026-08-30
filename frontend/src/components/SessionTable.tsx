import { useMemo, useState } from "react";
import type { SessionStat } from "../types";
import { formatDateTimeEn, formatTimeEn } from "../utils/date";
import { formatSeconds, formatTokens, formatUSD } from "../utils/format";

type SortKey = "tokens" | "spend" | "tasks" | "time" | "recent";

const SORT_DEFS: Array<{
  key: SortKey;
  label: string;
  get: (s: SessionStat) => number;
}> = [
  { key: "tokens", label: "Tokens", get: (s) => s.tokens },
  { key: "spend", label: "Spend", get: (s) => s.cost },
  { key: "tasks", label: "Tasks", get: (s) => s.tasks },
  { key: "time", label: "Time", get: (s) => s.activeSeconds },
  { key: "recent", label: "Last active", get: (s) => Date.parse(s.lastTs ?? "") || 0 },
];

/**
 * Per-session breakdown: which single session burned the most tokens/money.
 * Click a metric column header to sort by it (click again to flip direction).
 */
export function SessionTable({ sessions }: { sessions: SessionStat[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("tokens");
  const [desc, setDesc] = useState(true);

  const sorted = useMemo(() => {
    const def = SORT_DEFS.find((d) => d.key === sortKey)!;
    return [...sessions].sort((a, b) => {
      const delta = def.get(a) - def.get(b);
      return (desc ? -delta : delta) || a.sessionId.localeCompare(b.sessionId);
    });
  }, [sessions, sortKey, desc]);

  if (!sessions.length) {
    return (
      <section className="panel p-5 sm:p-6">
        <h2 className="eyebrow mb-3">Sessions</h2>
        <p className="font-mono text-sm text-muted">No session activity yet.</p>
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
          Sessions
        </h2>
        <span className="eyebrow">
          {sessions.length} session{sessions.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-ink-700">
              <Th>Session</Th>
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
            {sorted.map((s, idx) => (
              <tr
                key={s.sessionId}
                className="border-b border-ink-700/60 hover:bg-ink-800/40 transition-colors"
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-[10px] text-muted w-6 shrink-0">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <div className="flex flex-col min-w-0">
                      <span
                        className="font-mono text-sm text-fg truncate"
                        title={s.sessionId}
                      >
                        {s.sessionId.slice(0, 8)}
                      </span>
                      <span className="font-mono text-[10px] text-muted truncate max-w-xs">
                        {s.project}
                      </span>
                    </div>
                  </div>
                </td>
                <Td className="text-right">{formatTokens(s.tokens, 2)}</Td>
                <Td className="text-right text-muted">{formatUSD(s.cost)}</Td>
                <Td className="text-right">{s.tasks}</Td>
                <Td className="text-right">{formatSeconds(s.activeSeconds)}</Td>
                <Td className="text-right text-muted whitespace-nowrap">
                  {s.lastTs ? (
                    <>
                      {formatDateTimeEn(new Date(s.lastTs))}
                      <span className="ml-2 text-muted/70">
                        {formatTimeEn(new Date(s.lastTs))}
                      </span>
                    </>
                  ) : (
                    "—"
                  )}
                </Td>
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
