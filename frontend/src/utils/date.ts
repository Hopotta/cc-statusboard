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

/* ------------------------------------------------------------------ */
/* English date formatting.                                            */
/*                                                                     */
/* `toLocaleString(undefined, …)` resolves to the OS/browser locale —  */
/* on a zh-CN Windows box `month: "short"` renders as "8月28日". These  */
/* helpers pin en-US so the dashboard stays fully English.             */
/* ------------------------------------------------------------------ */

const EN_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const EN_MONTHS_LONG = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"] as const;

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

/** "15:31" — 24-hour clock, zero-padded (no locale involved). */
export function formatTimeEn(d: Date): string {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "Aug 28" */
export function formatShortDateEn(d: Date): string {
  return `${EN_MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`;
}

/** "Aug 28, 15:31" */
export function formatDateTimeEn(d: Date): string {
  return `${formatShortDateEn(d)}, ${formatTimeEn(d)}`;
}

/** "August 28th, 15:31" */
export function formatLongDateTimeEn(d: Date): string {
  return `${EN_MONTHS_LONG[d.getMonth()]} ${ordinal(d.getDate())}, ${formatTimeEn(d)}`;
}