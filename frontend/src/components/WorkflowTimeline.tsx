import { useState } from "react";

interface TimelineEvent {
  t: string;
  kind: "user" | "assistant" | "tool";
  label: string;
}

interface TimelineSession {
  sessionId: string;
  file: string;
  events: TimelineEvent[];
  firstEvent: string;
  lastEvent: string;
}

/**
 * Agent workflow timeline — visualises the user→assistant→tool sequence
 * within recent sessions.  Each session is a horizontal strip of dots.
 */
export function WorkflowTimeline({
  sessions,
}: {
  sessions: TimelineSession[];
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!sessions || !sessions.length) {
    return (
      <section className="panel p-5 sm:p-6">
        <h2 className="eyebrow mb-3">Workflow timeline</h2>
        <p className="font-mono text-sm text-muted">No sessions yet.</p>
      </section>
    );
  }

  return (
    <section className="panel p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-sm tracking-widest2 uppercase text-muted">
          Workflow timeline
        </h2>
        <span className="eyebrow">
          {sessions.length} recent session{sessions.length === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="flex flex-col gap-3">
        {sessions.map((s) => {
          const isOpen = expanded === s.sessionId;
          const first = new Date(s.firstEvent);
          const last = new Date(s.lastEvent);
          const durMin = Math.max(
            1,
            Math.round((last.getTime() - first.getTime()) / 60000),
          );
          const userCount = s.events.filter((e) => e.kind === "user").length;
          const toolCount = s.events.filter((e) => e.kind === "tool").length;
          const replyCount = s.events.filter((e) => e.kind === "assistant").length;

          return (
            <li
              key={s.sessionId}
              className="border border-ink-700 rounded p-3 sm:p-4 flex flex-col gap-3"
            >
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : s.sessionId)}
                className="flex items-center justify-between gap-4 text-left"
              >
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="font-mono text-sm text-fg truncate">
                    {s.sessionId.slice(0, 8)}…
                  </span>
                  <span className="font-mono text-[10px] text-muted">
                    {first.toLocaleString(undefined, {
                      month: "short",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}{" "}
                    →{" "}
                    {last.toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}{" "}
                    ({durMin}m)
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-[11px] text-muted shrink-0">
                  <span>
                    <span className="text-signal">●</span> {userCount}
                  </span>
                  <span>
                    <span className="text-mint">●</span> {toolCount}
                  </span>
                  <span>
                    <span className="text-sun">●</span> {replyCount}
                  </span>
                </div>
              </button>

              <Strip events={s.events} />

              {isOpen && (
                <div className="mt-1 border-t border-ink-700 pt-3 max-h-72 overflow-y-auto">
                  <ul className="flex flex-col gap-1.5">
                    {s.events.slice(0, 50).map((e, i) => (
                      <li key={i} className="flex items-baseline gap-3">
                        <span className="font-mono text-[10px] text-muted w-14 shrink-0">
                          {new Date(e.t).toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <KindBadge kind={e.kind} />
                        <span className="font-mono text-xs text-fg truncate">
                          {e.label}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Strip({ events }: { events: TimelineEvent[] }) {
  return (
    <div className="relative h-2 bg-ink-800 rounded-sm overflow-hidden flex">
      {events.slice(0, 80).map((e, i) => (
        <span
          key={i}
          className="block h-full"
          style={{
            flex: 1,
            background:
              e.kind === "user"
                ? "#FF7A3D"
                : e.kind === "tool"
                  ? "#6FE3C2"
                  : "#FFB454",
            opacity: 0.85,
          }}
          title={e.label}
        />
      ))}
    </div>
  );
}

function KindBadge({ kind }: { kind: TimelineEvent["kind"] }) {
  const cls =
    kind === "user"
      ? "text-signal border-signal/60"
      : kind === "tool"
        ? "text-mint border-mint/60"
        : "text-sun border-sun/60";
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-widest2 border rounded px-1.5 py-0.5 shrink-0 ${cls}`}
    >
      {kind}
    </span>
  );
}