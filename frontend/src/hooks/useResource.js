import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Load data from the backend, optionally polling. `fetcher(signal)` must return a promise.
 * Returns { data, error, loading, reload }. Requests are aborted on unmount.
 */
export function useResource(fetcher, { intervalMs = 0, enabled = true, deps = [] } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const depsKey = JSON.stringify(deps);
  const lastDepsKey = useRef(depsKey);

  useEffect(() => {
    if (!enabled) return undefined;
    if (lastDepsKey.current !== depsKey) {
      lastDepsKey.current = depsKey; // a different target (e.g. another design): drop stale data
      setState({ data: null, error: null, loading: true });
    }
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
  }, [enabled, intervalMs, nonce, depsKey]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
