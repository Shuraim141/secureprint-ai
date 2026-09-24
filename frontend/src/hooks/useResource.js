import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Load data from the backend, optionally polling. `fetcher(signal)` must return a promise.
 * Returns { data, error, loading, reload }. Requests are aborted on unmount.
 */
export function useResource(fetcher, { intervalMs = 0, enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const controller = new AbortController();

    async function load() {
      try {
        const data = await fetcherRef.current(controller.signal);
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (error) {
        if (cancelled || error?.name === "AbortError") return;
        setState((previous) => ({ data: previous.data, error, loading: false }));
      }
    }

    load();
    const timer = intervalMs > 0 ? setInterval(load, intervalMs) : null;
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearInterval(timer);
    };
  }, [enabled, intervalMs, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
