import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

export function useApi(path, dependencies = []) {
  const [state, setState] = useState({
    path: null,
    data: null,
    loading: Boolean(path),
    refreshing: false,
    error: null,
    updatedAt: null,
  });
  const request = useRef({ id: 0, controller: null });

  const reload = useCallback(async () => {
    request.current.controller?.abort();
    const controller = new AbortController();
    const id = request.current.id + 1;
    request.current = { id, controller };

    if (!path) {
      setState({ path: null, data: null, loading: false, refreshing: false, error: null, updatedAt: null });
      return null;
    }

    setState((current) => {
      const hasCurrentData = current.path === path && current.data != null;
      return {
        ...current,
        path,
        data: hasCurrentData ? current.data : null,
        loading: !hasCurrentData,
        refreshing: hasCurrentData,
        error: null,
      };
    });

    try {
      const data = await api(path, { signal: controller.signal });
      if (request.current.id !== id || controller.signal.aborted) return data;
      setState({ path, data, loading: false, refreshing: false, error: null, updatedAt: Date.now() });
      return data;
    } catch (error) {
      if (controller.signal.aborted || error?.name === "AbortError" || request.current.id !== id) return null;
      setState((current) => ({
        ...current,
        loading: false,
        refreshing: false,
        error,
      }));
      return null;
    }
  }, [path]);

  useEffect(() => {
    reload();
    return () => request.current.controller?.abort();
    // Callers use the dependency list to invalidate a request without changing its path.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, ...dependencies]);

  const currentPath = state.path === path;
  const visibleState = currentPath
    ? state
    : {
      path,
      data: null,
      loading: Boolean(path),
      refreshing: false,
      error: null,
      updatedAt: null,
    };

  return {
    ...visibleState,
    forbidden: visibleState.error?.status === 403,
    stale: visibleState.data != null && (visibleState.refreshing || Boolean(visibleState.error)),
    reload,
  };
}
