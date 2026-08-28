import { useEffect, useState } from "react";
import type { Statusboard } from "../types";

interface UseStatusboardResult {
  data: Statusboard | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  lastUpdated: Date | null;
}

/**
 * Polls ./statusboard.json.  Vite serves the frontend from the parent directory's
 * static files? No — we set the dev server root to the parent so statusboard.json
 * is reachable at the root URL.
 */
export function useStatusboard(intervalMs = 5000): UseStatusboardResult {
  const [data, setData] = useState<Statusboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const url = `./statusboard.json?ts=${Date.now()}`;

    fetch(url, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json: Statusboard) => {
        if (cancelled) return;
        setData(json);
        setError(null);
        setLastUpdated(new Date());
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [tick]);

  useEffect(() => {
    if (intervalMs <= 0) return;
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return {
    data,
    loading,
    error,
    reload: () => setTick((t) => t + 1),
    lastUpdated,
  };
}