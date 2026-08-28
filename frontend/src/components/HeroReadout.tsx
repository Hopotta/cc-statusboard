import { formatTokens, formatTokensLong } from "../utils/format";
import { formatLongDateTimeEn } from "../utils/date";

/**
 * The signature element: a single oversized numeric readout (the flight-deck
 * "total tokens processed" callout).  Big mono number, eyebrow label, and a
 * small ASCII-style ornament on the right.
 */
export function HeroReadout({
  totalTokens,
  cost,
  generatedAt,
}: {
  totalTokens: number;
  cost: number;
  generatedAt: string;
}) {
  // Use the actual host:port the dashboard was loaded from so the "Local" cell
  // stays correct when the launcher is invoked with --port.
  const port =
    typeof window !== "undefined" && window.location.port
      ? window.location.port
      : "5173";
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";

  return (
    <header className="relative panel overflow-hidden grid-bg">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-signal/60 to-transparent" />
      <div className="p-8 sm:p-10 flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span className="live-dot" aria-hidden />
            <span className="eyebrow">Claude Code Statusboard</span>
          </div>
          <div>
            <div className="eyebrow mb-3">Tokens Processed</div>
            <div className="flex items-baseline gap-4">
              <span className="readout text-[clamp(48px,9vw,108px)] leading-none">
                {formatTokens(totalTokens)}
              </span>
              <span className="font-mono text-sm text-muted">
                {formatTokensLong(totalTokens)}
              </span>
            </div>
          </div>
        </div>

        {/* Right side ornament — callouts like a flight-data strip */}
        <div className="grid grid-cols-2 gap-x-10 gap-y-3 self-start lg:self-end">
          <Ornament label="Spend" value={`$${cost.toFixed(2)}`} />
          <Ornament
            label="Generated"
            value={formatLongDateTimeEn(new Date(generatedAt))}
          />
          <Ornament label="Source" value="ccusage · jsonl" />
          <Ornament label="Local" value={`${host}:${port}`} />
        </div>
      </div>
    </header>
  );
}

function Ornament({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="eyebrow">{label}</span>
      <span className="font-mono text-sm text-fg">{value}</span>
    </div>
  );
}