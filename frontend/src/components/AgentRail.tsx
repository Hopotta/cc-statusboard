import type { AgentDescriptor } from "../types";
import anthropicLogo from "../assets/anthropic.svg";
import openaiLogo from "../assets/openai.svg";

interface Props {
  agents: AgentDescriptor[];
  selected: Set<string>;
  onChange: (ids: Set<string>) => void;
}

/** A compact, multi-select source switcher that belongs to the hero card. */
export function AgentRail({ agents, selected, onChange }: Props) {
  const allSelected = agents.length > 0 && agents.every((agent) => selected.has(agent.id));

  const selectAll = () => onChange(new Set(agents.map((agent) => agent.id)));
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  return (
    <div className="border-t border-ink-700/80 px-5 py-4 sm:px-10 sm:py-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="eyebrow text-signal">Agents</span>
          <span className="font-mono text-[11px] text-muted">
            multi-select telemetry sources
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest2 text-muted">
          {selected.size}/{agents.length} selected
        </span>
      </div>
      <div className="mt-4 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Select agents">
        <AgentButton
          label="All"
          source="Show every connected source and keep placeholders visible"
          selected={allSelected}
          connected
          onClick={selectAll}
          icon={<AllIcon />}
        />
        {agents.map((agent) => (
          <AgentButton
            key={agent.id}
            label={agent.label}
            source={agent.source}
            selected={selected.has(agent.id)}
            connected={agent.state === "connected"}
            onClick={() => toggle(agent.id)}
            icon={<AgentIcon id={agent.id} />}
          />
        ))}
      </div>
    </div>
  );
}

function AgentButton({
  label,
  source,
  selected,
  connected,
  onClick,
  icon,
}: {
  label: string;
  source: string;
  selected: boolean;
  connected: boolean;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      title={`${label} — ${source}`}
      className={`group relative flex min-w-[82px] shrink-0 flex-col items-center gap-2 rounded-md border px-3 py-2.5 font-mono transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal/70 ${
        selected
          ? "border-signal/70 bg-signal/10 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
          : "border-ink-700 bg-ink-950/45 text-muted hover:border-ink-600 hover:text-fg"
      } ${!connected ? "border-dashed opacity-70 hover:opacity-100" : ""}`}
    >
      <span className={`agent-icon grid h-7 w-7 place-items-center ${selected ? "text-signal" : "text-muted group-hover:text-fg"}`}>
        {icon}
      </span>
      <span className="whitespace-nowrap text-[10px] leading-none">{label}</span>
      {!connected && (
        <span className="absolute right-1.5 top-1.5 h-1 w-1 rounded-full bg-muted/70" aria-label="Placeholder" />
      )}
    </button>
  );
}

function AgentIcon({ id }: { id: string }) {
  switch (id) {
    case "claude-code":
      return <img src={anthropicLogo} alt="" className="h-6 w-6 brightness-0 invert" />;
    case "codex":
      return <img src={openaiLogo} alt="" className="h-6 w-6 object-contain" />;
    case "gemini-cli":
      return <GeminiMark />;
    default:
      return <TerminalMark />;
  }
}

function AllIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 fill-current" aria-hidden>
      <rect x="3" y="3" width="7" height="7" rx="1.5" opacity=".95" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" opacity=".55" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" opacity=".55" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" opacity=".95" />
    </svg>
  );
}

function GeminiMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 fill-current" aria-hidden>
      <path d="M12 2.5c1.1 5.2 4.3 8.4 9.5 9.5-5.2 1.1-8.4 4.3-9.5 9.5-1.1-5.2-4.3-8.4-9.5-9.5 5.2-1.1 8.4-4.3 9.5-9.5Z" />
    </svg>
  );
}

function TerminalMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 fill-none stroke-current" strokeWidth="1.8" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="m7 9 3 3-3 3M13 15h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
