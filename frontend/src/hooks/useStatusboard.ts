import { useEffect, useRef, useState } from "react";
import type { Statusboard } from "../types";

interface UseStatusboardResult {
  data: Statusboard | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  lastUpdated: Date | null;
}

/**
 * Polls ./statusboard.json (served fresh by both the Python server and the
 * Vite dev plugin — neither ever serves a stale copy).
 *
 * Each fetch is tagged with the current `tick`; if a slower older response
 * arrives after a newer one (e.g. during heavy regen), we ignore it so the UI
 * doesn't flicker back to a stale snapshot.  Responses whose `generatedAt`
 * matches the one already rendered are dropped, so a poll that finds no new
 * data costs one fetch instead of a full re-render.
 */
export function useStatusboard(intervalMs = 5000): UseStatusboardResult {
  const [data, setData] = useState<Statusboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);
  const tickRef = useRef(tick);
  tickRef.current = tick;
  const generatedAtRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const epoch = tickRef.current;
    const url = `./statusboard.json?ts=${Date.now()}`;

    fetch(url, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json: Statusboard) => {
        if (cancelled) return;
        // Only accept this response if it's still the current tick.
        if (epoch !== tickRef.current) return;
        // Skip unchanged payloads (backend stamps every build with generatedAt).
        if (json.generatedAt && json.generatedAt === generatedAtRef.current) return;
        generatedAtRef.current = json.generatedAt;
        setData(json);
        setError(null);
        setLastUpdated(new Date());
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (epoch !== tickRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled && epoch === tickRef.current) setLoading(false);
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