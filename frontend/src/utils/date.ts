/**
 * Local-date helpers.
 *
 * The Python parser emits dates from `dt.date().isoformat()` (the user's local
 * timezone).  We mirror that on the frontend so date-string lookups match.
 *
 * `new Date().toISOString().slice(0, 10)` is wrong here — it would emit the UTC
 * date instead of the local one, which silently desyncs at any timezone boundary.
 */

export function localISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**Diff in whole days between two `YYYY-MM-DD` strings (b - a).*/
export function diffDays(a: string, b: string): number {
  const [ay, am, ad] = a.split("-").map(Number);
  const [by, bm, bd] = b.split("-").map(Number);
  return Math.round((Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / 86_400_000);
}