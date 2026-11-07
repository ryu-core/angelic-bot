import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { io } from "socket.io-client";
import { api } from "../lib/api.js";

const StatusContext = createContext(null);

export function StatusProvider({ children }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [transportState, setTransportState] = useState("checking");
  const [browserOnline, setBrowserOnline] = useState(() => navigator.onLine);
  const request = useRef(null);

  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const data = await api("/api/status", { signal: controller.signal, redirectOnUnauthorized: false });
      if (controller.signal.aborted) return null;
      setStatus(data);
      setError(null);
      return data;
    } catch (cause) {
      if (cause?.name === "AbortError") return null;
      setError(cause.message);
      setTransportState(navigator.onLine ? "reconnecting" : "offline");
      return null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    refresh();
    const socketFactory = globalThis.__XIEL_SOCKET_FACTORY__ || io;
    const socket = socketFactory({ withCredentials: true });
    socket.on("connect", () => {
      if (!active) return;
      setTransportState("online");
      setError(null);
    });
    socket.on("status:update", (data) => {
      if (!active) return;
      setStatus(data);
      setError(null);
      setTransportState("online");
    });
    socket.on("disconnect", () => {
      if (active) setTransportState(navigator.onLine ? "reconnecting" : "offline");
    });
    socket.on("connect_error", () => {
      if (!active) return;
      setTransportState(navigator.onLine ? "reconnecting" : "offline");
      setError((current) => current || "Live updates are reconnecting.");
    });

    const handleOffline = () => {
      setBrowserOnline(false);
      setTransportState("offline");
    };
    const handleOnline = () => {
      setBrowserOnline(true);
      setTransportState("reconnecting");
      socket.connect();
      refresh();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible" && navigator.onLine) {
        socket.connect();
        refresh();
      }
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      active = false;
      request.current?.abort();
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      document.removeEventListener("visibilitychange", handleVisibility);
      socket.disconnect();
    };
  }, [refresh]);

  const connectionState = !browserOnline
    ? "offline"
    : !status && transportState === "reconnecting"
      ? "reconnecting"
      : !status
      ? "checking"
      : transportState === "reconnecting"
        ? "reconnecting"
        : status?.online
          ? "online"
          : "offline";

  const value = useMemo(() => ({
    status,
    error,
    connectionState,
    checking: connectionState === "checking",
    refresh,
  }), [connectionState, error, refresh, status]);

  return <StatusContext.Provider value={value}>{children}</StatusContext.Provider>;
}

export function useStatus() {
  const context = useContext(StatusContext);
  if (!context) throw new Error("useStatus must be used inside StatusProvider.");
  return context;
}
