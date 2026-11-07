import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router";
import {
  api,
  clearReturnTo,
  consumeReturnTo,
  currentReturnTo,
  rememberReturnTo,
  safeReturnTo,
} from "../lib/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const location = useLocation();

  const refresh = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const nextUser = await api("/api/auth/me", { signal, redirectOnUnauthorized: false });
      setUser(nextUser);
      setLoading(false);
      return nextUser;
    } catch (cause) {
      if (cause?.name === "AbortError") return null;
      if (cause?.status === 401) {
        setUser(null);
        setError(null);
      } else {
        setError(cause);
      }
      setLoading(false);
      return null;
    }
  }, []);

  const login = useCallback((returnTo = "/dashboard") => {
    rememberReturnTo(safeReturnTo(returnTo));
    window.location.assign("/api/auth/discord");
  }, []);

  const logout = useCallback(async () => {
    await api("/api/auth/logout", { method: "POST", redirectOnUnauthorized: false });
    clearReturnTo();
    setUser(null);
    setError(null);
    window.location.assign("/");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (loading || error || user === undefined) return;
    const params = new URLSearchParams(location.search);
    if (!user && params.get("signin") === "1") {
      login(safeReturnTo(params.get("returnTo")));
      return;
    }
    if (user) {
      const returnTo = consumeReturnTo();
      const current = currentReturnTo();
      if (returnTo && returnTo !== current) window.location.replace(returnTo);
    }
  }, [error, loading, location.search, login, user]);

  const value = useMemo(() => ({
    user,
    loading,
    error,
    login,
    logout,
    refresh,
  }), [error, loading, login, logout, refresh, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
