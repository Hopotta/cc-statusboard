import { ACCENT_CLASS, type Accent } from "../types";

/**
 * Small metric tile.  Compact eyebrow label + big number + optional subline.
 * Used in the secondary metrics strip beneath the hero readout.
 */
export function StatTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: Accent;
}) {
  const accentClass = accent ? ACCENT_CLASS[accent] : "text-fg";
  return (
    <div className="panel px-5 py-4 flex flex-col gap-1.5">
      <span className="eyebrow">{label}</span>
      <span className={`readout text-3xl ${accentClass}`}>{value}</span>
      {sub && <span className="font-mono text-xs text-muted">{sub}</span>}
    </div>
  );
}