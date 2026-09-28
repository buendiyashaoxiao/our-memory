import { useCallback, useEffect, useRef, useState } from "react";
import type { Page } from "./types";

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  setData: (fn: (prev: T | null) => T | null) => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => alive && setDataState(d))
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((f: (prev: T | null) => T | null) => setDataState((p) => f(p)), []);
  return { data, error, loading, reload, setData };
}

/** Cursor pagination + an IntersectionObserver sentinel for infinite scroll. */
export function useInfinite<T>(fetchPage: (cursor: string | null) => Promise<Page<T>>, deps: unknown[]) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const gen = useRef(0);
  const busy = useRef(false);

  const load = useCallback(
    async (reset = false) => {
      if (busy.current && !reset) return;
      const myGen = reset ? ++gen.current : gen.current;
      busy.current = true;
      setLoading(true);
      setError(null);
      try {
        const page = await fetchPage(reset ? null : cursor);
        if (myGen !== gen.current) return;
        setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
        setCursor(page.next_cursor);
        setDone(!page.next_cursor);
      } catch (e) {
        if (myGen === gen.current) setError(e as Error);
      } finally {
        if (myGen === gen.current) {
          busy.current = false;
          setLoading(false);
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cursor, ...deps],
  );

  useEffect(() => {
    setItems([]);
    setCursor(null);
    setDone(false);
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const sentinel = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || done || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting) && !busy.current && !done) load();
      },
      { rootMargin: "800px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [load, done, items.length]);

  return { items, setItems, loading, done, error, loadMore: () => load(), reload: () => load(true), sentinel };
}

export function useIdle(minutes: number, onIdle: () => void) {
  const cb = useRef(onIdle);
  cb.current = onIdle;
  useEffect(() => {
    if (!minutes || minutes <= 0) return;
    let timer = window.setTimeout(() => cb.current(), minutes * 60_000);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => cb.current(), minutes * 60_000);
    };
    const events = ["pointerdown", "keydown", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      window.clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [minutes]);
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}
