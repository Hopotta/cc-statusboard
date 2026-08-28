/**
 * Number formatters shared across the dashboard.
 *
 * - formatTokens: 12_345_678 -> "12.35M"
 * - formatSeconds: 13_289     -> "3h 41m"
 * - formatPct:     0.756      -> "75.6%"
 */

const TOKEN_UNITS: Array<[number, string]> = [
  [1_000_000_000_000, "T"],
  [1_000_000_000, "B"],
  [1_000_000, "M"],
  [1_000, "K"],
];

export function formatTokens(n: number, fractionDigits = 2): string {
  if (!n || n < 1) return "0";
  for (const [base, suffix] of TOKEN_UNITS) {
    if (n >= base) {
      const v = n / base;
      // If the scaled value is exactly an integer, don't show decimals.
      const rounded = Number(v.toFixed(fractionDigits));
      return `${rounded}${suffix}`;
    }
  }
  return n.toString();
}

export function formatTokensLong(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatSeconds(secs: number): string {
  if (!secs || secs < 0) return "0m";
  const total = Math.floor(secs);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

export function formatPct(p: number, fractionDigits = 1): string {
  if (!isFinite(p)) return "0%";
  return `${p.toFixed(fractionDigits)}%`;
}

export function formatUSD(n: number): string {
  if (!isFinite(n)) return "$0.00";
  if (n >= 100) return `$${n.toFixed(0)}`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(3)}`;
}

export function relativeTime(d: Date | null): string {
  if (!d) return "—";
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return d.toLocaleTimeString();
}